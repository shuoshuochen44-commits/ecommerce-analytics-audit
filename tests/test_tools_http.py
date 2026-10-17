import json
import threading
import urllib.request
import urllib.error
from pathlib import Path

import pytest

from zhishu_inspection.pipeline import run_pipeline
from zhishu_inspection.server import create_server


@pytest.fixture
def server_url(tmp_path):
    run_pipeline(Path('tests/fixtures/olist_mini'), tmp_path)
    server = create_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()
    thread.join()


def post(url, body, header=True, origin=None):
    headers = {'Content-Type':'text/csv'}
    if header:
        headers['X-Zhishu-Local'] = '1'
    if origin:
        headers['Origin'] = origin
    return urllib.request.urlopen(urllib.request.Request(url,data=body,headers=headers))


def test_preview_confirm_source_switch_search_and_export(server_url):
    body = ('订单号,下单日期,省份,买家编号,商品分类,商品金额,运费,支付金额,订单状态\n'
            '真实格式测试,2026-01-01,广东省,U1,家居日用,100.00,0.00,100.00,已完成\n').encode('utf-8-sig')
    with post(server_url+'/api/import/preview',body) as response:
        assert json.load(response)['order_count'] == 1
    with urllib.request.urlopen(server_url+'/api/data') as response:
        assert not json.load(response)['customer_available']
    with post(server_url+'/api/import/confirm',body) as response:
        imported = json.load(response)
    with urllib.request.urlopen(server_url+'/api/data?source=customer') as response:
        data = json.load(response)
        assert data['dataset']['id'] == 'customer_csv'
        assert data['metrics']['completed_product_amount'] == '100.00'
        assert data['run_id'] == imported['run_id']
    with urllib.request.urlopen(server_url+'/api/data') as response:
        assert json.load(response)['dataset']['id'] == 'olist'
    with urllib.request.urlopen(server_url+'/api/orders?source=customer&search=U1') as response:
        assert json.load(response)['total'] == 1
    with urllib.request.urlopen(server_url+'/orders.csv?source=customer') as response:
        assert '真实格式测试' in response.read().decode('utf-8-sig')
    with urllib.request.urlopen(server_url+'/template.csv') as response:
        assert '订单号' in response.read().decode('utf-8-sig')


@pytest.mark.parametrize('path', ['/api/orders?page=0','/api/orders?status=BAD','/api/orders?source=../x'])
def test_query_rejects_invalid_parameters(server_url,path):
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(server_url+path)
    assert error.value.code == 400


@pytest.mark.parametrize('header,origin',[(False,None),(True,'https://other.example')])
def test_import_rejects_cross_origin_or_missing_local_header(server_url,header,origin):
    with pytest.raises(urllib.error.HTTPError) as error:
        post(server_url+'/api/import/confirm',b'invalid',header,origin)
    assert error.value.code == 403


def test_import_size_limit(server_url):
    with pytest.raises(urllib.error.HTTPError) as error:
        post(server_url+'/api/import/preview',b'x'*(5*1024*1024+1))
    assert error.value.code == 413
