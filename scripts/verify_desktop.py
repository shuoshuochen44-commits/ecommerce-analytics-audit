"""Exercise the built Windows app against external data in a fresh test workspace."""

import argparse
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
        print(json.dumps({'empty_start':True,'formats':results,'drivers':listing['database_capabilities']},ensure_ascii=False,indent=2))
    finally:
        if started:
            request('/api/application/exit',{})
            process.wait(timeout=20)
        elif process.poll() is None:
            process.terminate();process.wait(timeout=5)


if __name__=='__main__':main()
