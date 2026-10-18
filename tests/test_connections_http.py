import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

from zhishu_inspection.pipeline import run_pipeline
from zhishu_inspection.server import create_server
from test_source_manager import csv_bytes
from zhishu_inspection.csv_import import COLUMNS


@pytest.fixture
def connection_server(tmp_path):
    root=tmp_path/'output'
    run_pipeline(Path('tests/fixtures/olist_mini'),root)
    server=create_server(root,port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}',server
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def post(base,path,data,**headers):
    body=data if isinstance(data,bytes) else json.dumps(data).encode('utf-8')
    request=urllib.request.Request(base+path,data=body,headers={'X-Zhishu-Local':'1','Content-Type':'application/json',**headers})
    with urllib.request.urlopen(request,timeout=15) as response:
        return json.load(response)


def test_upload_map_refresh_and_query_selected_source(connection_server):
    base,server=connection_server
    result=post(base,'/api/sources/upload',csv_bytes(),**{'X-Zhishu-Filename':'orders.csv'})
    source=result['source']
    preview=post(base,'/api/sources/preview',{'source_id':source['id']})
    assert preview['preview']['row_count']==1
    assert preview['suggested_mapping']['订单号']=='订单号'
    post(base,'/api/sources/configure',{'source_id':source['id'],'mapping':{c:c for c in COLUMNS}})
    post(base,'/api/sources/refresh',{'source_id':source['id']})
    server.source_manager.wait_for_idle(source['id'])
    with urllib.request.urlopen(base+'/api/data?source='+source['id']) as response:
        data=json.load(response)
    assert data['metrics']['completed_product_amount']=='100.00'
    assert data['active_source']==source['id']
    assert data['source_status']['snapshot_run_id']==data['run_id']
    with urllib.request.urlopen(base+'/orders.csv?'+urllib.parse.urlencode({'source':source['id'],'run_id':data['run_id']})) as response:
        assert '001' in response.read().decode('utf-8-sig')


def test_file_watch_emits_sse_after_publication(connection_server,tmp_path):
    base,server=connection_server
    file=tmp_path/'orders.csv'
    file.write_bytes(csv_bytes())
    source=post(base,'/api/sources/register',{'kind':'file','path':str(file)})['source']
    sid=source['id']
    post(base,'/api/sources/configure',{'source_id':sid,'mapping':{c:c for c in COLUMNS},'refresh':{'watch_seconds':1,'interval_seconds':30}})
    post(base,'/api/sources/refresh',{'source_id':sid})
    server.source_manager.wait_for_idle(sid)
    first=server.source_manager.get(sid)['snapshot_run_id']
    file.write_bytes(csv_bytes('125.00'))
    server.source_manager.tick(now=10**15)
    server.source_manager.wait_for_idle(sid)
    assert server.source_manager.get(sid)['snapshot_run_id']!=first
    request=urllib.request.Request(base+'/api/sources/events',headers={'Accept':'text/event-stream'})
    with urllib.request.urlopen(request,timeout=5) as response:
        assert response.headers['Content-Type'].startswith('text/event-stream')
        event=''.join(response.readline().decode('utf-8') for _ in range(4))
        assert 'data:' in event and 'source_id' in event


def test_source_refresh_keeps_filters_when_selected_region_disappears(connection_server,tmp_path):
    base,server=connection_server
    file=tmp_path/'orders.csv'
    file.write_bytes(csv_bytes())
    sid=post(base,'/api/sources/register',{'kind':'file','path':str(file)})['source']['id']
    post(base,'/api/sources/configure',{'source_id':sid,'mapping':{c:c for c in COLUMNS}})
    server.source_manager.refresh(sid,wait=True)
    first=server.source_manager.get(sid)['snapshot_run_id']
    file.write_bytes(csv_bytes().replace('广东省'.encode(),'北京市'.encode()))
    server.source_manager.refresh(sid,wait=True)
    query=urllib.parse.urlencode({'source':sid,'state':'广东省','start':'2026-01-01','end':'2026-01-31'})
    with urllib.request.urlopen(base+'/api/data?'+query) as response:
        data=json.load(response)
    assert data['run_id']!=first
    assert data['filters']['state']=='广东省'
    assert '广东省' not in data['states']
    assert data['metrics']['completed_order_count']==0


def test_source_api_blocks_cross_origin_and_malformed_parameters(connection_server):
    base,_=connection_server
    for path,data,headers in (
        ('/api/sources/register',{'kind':'file','path':'bad'},{'Origin':'https://untrusted.example'}),
        ('/api/sources/upload',csv_bytes(),{'X-Zhishu-Filename':'..%2Forders.csv'}),
        ('/api/sources/preview',{'source_id':'../x'},{}),
        ('/api/sources/register',b'[]',{}),
    ):
        with pytest.raises(urllib.error.HTTPError) as error:
            post(base,path,data,**headers)
        assert error.value.code in (400,403)
    with urllib.request.urlopen(base+'/api/sources') as response:
        result=json.load(response)
        assert result['sources']==[]
        assert result['database_capabilities']
    with urllib.request.urlopen(base+'/connections.js') as response:
        assert 'EventSource' in response.read().decode('utf-8')
