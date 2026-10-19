"""Exercise the built Windows app against external data in a fresh test workspace."""

import argparse
import csv
import io
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('executable',type=Path)
    parser.add_argument('samples',type=Path)
    parser.add_argument('workspace',type=Path)
    parser.add_argument('--port',type=int,default=8782)
    args=parser.parse_args()
    root=args.workspace.resolve()
    if root.exists():raise SystemExit('Use a fresh workspace for verification')
    base=f'http://127.0.0.1:{args.port}'
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,data=None,headers=None):
        if data is not None and not isinstance(data,bytes):data=json.dumps(data).encode()
        req=urllib.request.Request(base+path,data=data,headers={'X-Zhishu-Local':'1',**(headers or {})})
        with opener.open(req,timeout=45) as response:
            body=response.read()
            return json.loads(body) if 'application/json' in response.headers.get('Content-Type','') else body
    process=subprocess.Popen([str(args.executable.resolve()),'--no-browser','--port',str(args.port),'--data-dir',str(root)],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    results=[]
    started=False
    try:
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Desktop app exited before startup')
            try:
                request('/api/health');started=True;break
            except (OSError,ValueError):time.sleep(.2)
        if not started:raise RuntimeError('Desktop startup timed out')
        listing=request('/api/sources')
        assert not listing['sources'] and not listing['workspace_available'] and not listing['customer_available']
        assert b'initializeWorkspace' in request('/')
        assert b'EventSource' in request('/connections.js')
        for file in sorted(args.samples.glob('*')):
            if file.suffix not in ('.csv','.xlsx','.json','.parquet','.sqlite'):continue
            source=request('/api/sources/upload',file.read_bytes(),{'X-Zhishu-Filename':urllib.parse.quote(file.name)})['source']
            sid=source['id']
            preview=request('/api/sources/preview',{'source_id':sid})
            assert preview['preview']['row_count']==12000
            if results:
                assert preview['preview']['mapping_origin']=='history',preview['preview']['mapping_origin']
            validation=request('/api/sources/validate',{'source_id':sid,'mapping':preview['suggested_mapping']})['validation']
            assert validation['valid'] and validation['row_count']==12000
            request('/api/sources/configure',{'source_id':sid,'mapping':preview['suggested_mapping']})
            request('/api/sources/refresh',{'source_id':sid})
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                status=next(s for s in request('/api/sources')['sources'] if s['id']==sid)
                if status['available']:break
                if status['state']=='error':raise RuntimeError(status['error'])
                time.sleep(.2)
            assert status['available'],status
            data=request('/api/data?source='+sid)
            results.append({'format':file.suffix,'rows':preview['preview']['row_count'],'metrics':data['metrics']})
        assert len(results)==5
        assert all(item['metrics']==results[0]['metrics'] for item in results)
        assert len(request('/api/analysis/questions')['questions'])==30
        answer=request('/api/analysis/ask',{'source':sid,'snapshot_run_id':data['run_id'],'question':'A01'})['run']
        assert answer['verification_status']=='verified',answer
        assert answer['result']==[{'value':data['metrics']['completed_product_amount']}]
        assert answer['sql'] and answer['verification']['matched']
        trend=request('/api/analysis/ask',{'source':sid,'snapshot_run_id':data['run_id'],'question':'T01'})['run']
        assert trend['verification_status']=='verified' and trend['chart_spec']['mark']=='line',trend
        assert len(trend['result'])==9
        repeated=request('/api/analysis/replay',{'source':sid,'run_id':answer['run_id']})['run']
        assert repeated['replay_matches'] and repeated['snapshot_run_id']==answer['snapshot_run_id']
        downloaded=request('/api/analysis/download?'+urllib.parse.urlencode({'source':sid,'run_id':answer['run_id']}))
        assert downloaded==answer
        refused=request('/api/analysis/ask',{'source':sid,'snapshot_run_id':data['run_id'],'question':'D05'})['run']
        assert refused['verification_status']=='blocked' and not refused['result']
        sample=next(args.samples.glob('*.csv'))
        sample_rows=list(csv.reader(io.StringIO(sample.read_text(encoding='utf-8-sig'))))
        sample_rows[1][5]='-1'
        invalid=io.StringIO(newline='');writer=csv.writer(invalid)
        writer.writerow(sample_rows[0]);writer.writerow([]);writer.writerow(sample_rows[1])
        bad_source=request('/api/sources/upload',invalid.getvalue().encode('utf-8-sig'),{'X-Zhishu-Filename':'invalid-orders.csv'})['source']
        bad_preview=request('/api/sources/preview',{'source_id':bad_source['id']})
        diagnostics=request('/api/sources/validate',{'source_id':bad_source['id'],'mapping':bad_preview['suggested_mapping']})['validation']
        assert not diagnostics['valid'] and diagnostics['issues'][0]['row_number']==3,diagnostics
        assert request('/api/data?source='+sid)['run_id']==data['run_id']
        print(json.dumps({'empty_start':True,'formats':results,'drivers':listing['database_capabilities'],
                          'analysis':{'amount':answer['result'],'trend_months':len(trend['result']),
                                      'sql':answer['sql'],'replay_matches':True,'record_download':True,'missing_product_refused':True},
                          'import_validation':{'five_formats':True,'mapping_reused':True,'blank_row_error_position':3}},ensure_ascii=False,indent=2))
    finally:
        if started:
            request('/api/application/exit',{})
            process.wait(timeout=20)
        elif process.poll() is None:
            process.terminate();process.wait(timeout=5)


if __name__=='__main__':main()
