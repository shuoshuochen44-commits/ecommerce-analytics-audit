"""Bounded acquisition, immutable publication and coordinated refresh of sources."""

import copy
import hashlib
import json
import re
import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, perf_counter

from .csv_import import COLUMNS, import_csv
from .database_sources import inspect_database, read_database_table
from .file_sources import read_file_tables
from .source_types import MAX_BYTES, TableData
from .tabular_mapping import MappingValidationError, map_order_table, preview_table, validate_order_table


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha(value):
    return hashlib.sha256(value).hexdigest()


class SourceManager:
    def __init__(self, output_root):
        self.root=Path(output_root).resolve()
        self.directory=self.root/'connections'
        self.registry=self.directory/'registry.json'
        self.directory.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        self._condition=threading.Condition(self._lock)
        self._records={}
        self._secrets={}
        self._futures={}
        self._events=deque(maxlen=256)
        self._event_id=0
        self._stop=threading.Event()
        self._thread=None
        self._executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='zhishu-source')
        if self.registry.is_file():
            data=json.loads(self.registry.read_text(encoding='utf-8'))
            for record in data['sources']:
                self._validate_id(record['id'])
                record['config'].pop('password',None)
                record['state']='ready' if record.get('snapshot_run_id') else 'configured'
                if record.get('password_required'):
                    record['state']='credentials_required'
                if record.get('mapping') and 'mapping_columns' not in record:
                    selected=next((t for t in record['tables'] if t['name']==record['table'] and t.get('schema')==record['schema']),None)
                    if selected:
                        record['mapping_columns']=list(selected['columns'])
                record['next_interval']=record['next_watch']=0
                self._records[record['id']]=record

    @staticmethod
    def _validate_id(source_id):
        if not isinstance(source_id,str) or not re.fullmatch(r'src_[0-9a-f]{32}',source_id):
            raise ValueError('无效数据源 ID')

    def _record(self,source_id):
        self._validate_id(source_id)
        if source_id not in self._records:
            raise ValueError('数据源不存在')
        return self._records[source_id]

    def _persist(self):
        temporary=self.directory/('registry-'+uuid.uuid4().hex+'.tmp')
        records=copy.deepcopy(list(self._records.values()))
        for record in records:
            record.pop('next_interval',None)
            record.pop('next_watch',None)
            record['config'].pop('password',None)
        temporary.write_text(json.dumps({'version':1,'sources':records},ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        temporary.replace(self.registry)

    def _emit(self,source_id,event_type):
        self._event_id+=1
        record=self._records[source_id]
        self._events.append({'id':self._event_id,'source_id':source_id,'type':event_type,
                             'snapshot_run_id':record.get('snapshot_run_id'),'at':now_iso()})
        self._condition.notify_all()

    def _public(self,record):
        keys=('id','name','kind','tables','table','schema','mapping','refresh','state','watchable',
              'last_check_at','last_success_at','last_attempt_ms','last_acquired_at','snapshot_run_id','error','diagnostics')
        result={key:copy.deepcopy(record.get(key)) for key in keys}
        result['credentials_required']=bool(record.get('password_required') and record['id'] not in self._secrets)
        result['available']=bool(record.get('snapshot_run_id'))
        result['refresh_method']='polling_then_sse'
        return result

    def list_sources(self):
        with self._lock:
            return [self._public(r) for r in self._records.values()]

    def get(self,source_id):
        with self._lock:
            return self._public(self._record(source_id))

    def output_for(self,source_id):
        with self._lock:
            self._record(source_id)
        return self.directory/source_id/'snapshots'

    def _register(self,kind,config,tables,name,watchable,password=None):
        if not tables:
            raise ValueError('没有可读取的用户表')
        name=name or ('本机文件' if kind=='file' else f"{config['kind']} 数据库")
        if not isinstance(name,str) or not name.strip() or len(name)>80:
            raise ValueError('数据源名称必须为 1–80 个字符')
        source_id='src_'+uuid.uuid4().hex
        config=copy.deepcopy(config)
        config.pop('password',None)
        with self._lock:
            if len(self._records)>=16:
                raise ValueError('最多配置 16 个数据源，请先移除不用的配置')
            record={'id':source_id,'kind':kind,'name':name,'config':config,
                    'tables':tables,'table':tables[0]['name'],'schema':tables[0].get('schema'),
                    'mapping':{},'refresh':{'interval_seconds':None,'watch_seconds':None},
                    'watchable':watchable,'state':'configured','snapshot_run_id':None,'error':None,
                    'password_required':kind=='database' and config.get('kind') not in ('sqlite','duckdb'),
                    'next_interval':0,'next_watch':0}
            self._records[source_id]=record
            if password is not None:
                self._secrets[source_id]=password
            self._persist()
            self._emit(source_id,'configured')
            return self._public(record)

    def register_file(self,path,*,name=None,_uploaded=False):
        path=Path(path).resolve()
        if not path.is_file() or path.stat().st_size>MAX_BYTES:
            raise ValueError('请选择存在且不超过 20 MB 的文件')
        tables=read_file_tables(path)
        metadata=[{'name':t.name,'schema':None,'columns':list(t.columns)} for t in tables]
        return self._register('file',{'path':str(path)},metadata,name or path.name,not _uploaded)

    def register_upload(self,filename,content):
        if (not isinstance(filename,str) or not filename or len(filename)>160
                or Path(filename).name!=filename or any(c in filename for c in ('/','\\',':','\0'))
                or not content or len(content)>MAX_BYTES):
            raise ValueError('无效文件名或上传文件超过 20 MB')
        directory=self.directory/'uploads'/uuid.uuid4().hex
        directory.mkdir(parents=True,exist_ok=False)
        path=directory/filename
        path.write_bytes(content)
        try:
            return self.register_file(path,_uploaded=True)
        except Exception:
            path.unlink(missing_ok=True)
            directory.rmdir()
            raise

    def register_database(self,config,*,name=None):
        if not isinstance(config,dict):
            raise ValueError('数据库参数格式错误')
        metadata=inspect_database(config)
        return self._register('database',config,metadata['tables'],name,True,config.get('password'))

    def _configuration(self,record):
        config=copy.deepcopy(record['config'])
        if record.get('password_required'):
            if record['id'] not in self._secrets:
                raise ValueError('请重新填写连接密码并测试连接；密码不保存在配置文件中')
            config['password']=self._secrets[record['id']]
        return config

    def set_credentials(self,source_id,password):
        if not isinstance(password,str) or len(password)>1024:
            raise ValueError('无效连接密码')
        with self._lock:
            record=self._record(source_id)
            config=copy.deepcopy(record['config'])
        config['password']=password
        inspect_database(config)
        with self._lock:
            self._secrets[source_id]=password
            record['state']='ready' if record.get('snapshot_run_id') else 'configured'
            self._persist()
            return self._public(record)

    def preview(self,source_id,*,table=None,schema=None):
        with self._lock:
            record=copy.deepcopy(self._record(source_id))
        if record['kind']=='database':
            metadata=inspect_database(self._configuration(record))['tables']
            record['tables']=metadata
            with self._lock:
                self._record(source_id)['tables']=copy.deepcopy(metadata)
                self._persist()
        elif record['kind']=='file':
            metadata=[{'name':t.name,'schema':None,'columns':list(t.columns)} for t in read_file_tables(Path(record['config']['path']))]
            record['tables']=metadata
            with self._lock:
                self._record(source_id)['tables']=copy.deepcopy(metadata)
                self._persist()
        with self._lock:
            if table is not None:
                self._select_table(record,table,schema)
        data,_=self._read_table(record)
        preview=preview_table(data)
        preview.update(self._remembered_mapping(record,data.columns))
        return preview

    def _remembered_mapping(self,record,columns):
        def valid(mapping):
            return (isinstance(mapping,dict) and set(mapping)==set(COLUMNS)
                    and all(isinstance(value,str) and value in columns for value in mapping.values())
                    and len(set(mapping.values()))==len(COLUMNS))
        with self._lock:
            current=self._record(record['id'])
            if (record['table']==current['table'] and record['schema']==current['schema']
                    and valid(current.get('mapping'))):
                return {'remembered_mapping':copy.deepcopy(current['mapping']),'mapping_origin':'current'}
            candidates={}
            for previous in self._records.values():
                mapping=previous.get('mapping')
                if not valid(mapping):
                    continue
                if set(previous.get('mapping_columns',[]))==set(columns):
                    candidates[tuple(mapping[field] for field in COLUMNS)]=mapping
            if len(candidates)==1:
                return {'remembered_mapping':copy.deepcopy(next(iter(candidates.values()))),'mapping_origin':'history'}
            return {'remembered_mapping':{},'mapping_origin':'conflict' if candidates else 'aliases'}

    def validate(self,source_id,*,table=None,schema=None,mapping=None):
        """Validate a proposed mapping without changing source settings or snapshots."""
        with self._lock:
            record=copy.deepcopy(self._record(source_id))
            if table is not None:
                self._select_table(record,table,schema)
            if mapping is not None:
                record['mapping']=copy.deepcopy(mapping)
        data,_=self._read_table(record)
        return validate_order_table(data,record['mapping'],allow_empty=True)

    @staticmethod
    def _select_table(record,table,schema):
        matches=[t for t in record['tables'] if t['name']==table and (schema is None or t.get('schema')==schema)]
        if len(matches)!=1:
            raise ValueError('请选择已列出的来源表')
        record.update(table=table,schema=matches[0].get('schema'))

    def configure(self,source_id,*,table=None,schema=None,mapping=None,refresh=None):
        with self._lock:
            record=self._record(source_id)
            future=self._futures.get(source_id)
            if future and not future.done():
                raise ValueError('正在同步，请完成后再修改配置')
            proposed=copy.deepcopy(record)
            before=copy.deepcopy(record)
            if table is not None:
                self._select_table(proposed,table,schema)
                if proposed['table']!=record['table'] or proposed['schema']!=record['schema']:
                    proposed['mapping']={}
                    proposed.pop('mapping_columns',None)
            if mapping is not None:
                if (not isinstance(mapping,dict) or set(mapping)!=set(COLUMNS)
                        or any(not isinstance(v,str) for v in mapping.values())
                        or len(set(mapping.values()))!=len(COLUMNS)):
                    raise ValueError('请为九个业务字段各选择一个不同的来源列')
                columns=next(t['columns'] for t in proposed['tables'] if t['name']==proposed['table'] and t.get('schema')==proposed['schema'])
                if any(not isinstance(v,str) or v not in columns for v in mapping.values()):
                    raise ValueError('字段映射包含不存在的来源列')
                proposed['mapping']=copy.deepcopy(mapping)
            if refresh is not None:
                if not isinstance(refresh,dict) or set(refresh)-{'interval_seconds','watch_seconds'}:
                    raise ValueError('刷新设置无效')
                settings=copy.deepcopy(record['refresh'])
                for key,low,high in (('interval_seconds',10,3600),('watch_seconds',1,30)):
                    if key in refresh:
                        value=refresh[key]
                        if value is not None and (type(value) is not int or not low<=value<=high):
                            raise ValueError('定时刷新须为 10–3600 秒，变更监测须为 1–30 秒')
                        settings[key]=value
                if settings['watch_seconds'] is not None and not record['watchable']:
                    raise ValueError('上传的是静态副本；监测原文件请使用本机文件路径入口')
                proposed['refresh']=settings
        # File/database reads may be slow: keep source status and events available.
        if mapping is not None:
            data,_=self._read_table(proposed)
            validation=validate_order_table(data,mapping,allow_empty=True)
            if not validation['valid']:
                raise MappingValidationError(validation)
            proposed['mapping_columns']=list(data.columns)
        with self._lock:
            current=self._record(source_id)
            if current is not record or current!=before:
                raise ValueError('检查期间配置或采集状态发生变化，请重新检查后保存')
            future=self._futures.get(source_id)
            if future and not future.done():
                raise ValueError('正在同步，请完成后再修改配置')
            proposed['next_interval']=proposed['next_watch']=0
            self._records[source_id]=proposed
            self._persist()
            self._emit(source_id,'configured')
            return self._public(proposed)

    def _read_table(self,record):
        if record['kind']=='file':
            path=Path(record['config']['path'])
            if not path.is_file() or path.stat().st_size>MAX_BYTES:
                raise ValueError('来源文件不存在或超过 20 MB')
            original=path.read_bytes()
            if len(original)>MAX_BYTES:
                raise ValueError('来源文件超过 20 MB')
            tables=read_file_tables(path)
            if sha(path.read_bytes())!=sha(original):
                raise ValueError('读取期间文件发生变化，下次检查将重新采集')
            table=next((t for t in tables if t.name==record['table']),None)
            if table is None:
                raise ValueError('来源表结构发生变化，请重新选择字段映射')
            return table,sha(original)
        config=self._configuration(record)
        return read_database_table(config,record['table'],schema=record['schema']),None

    def _acquire(self,record):
        table,file_hash=self._read_table(record)
        if not record['mapping']:
            raise ValueError('请先确认订单字段映射')
        # Report source row numbers before canonical sorting for deterministic hashes.
        content=map_order_table(table,record['mapping'],allow_empty=True)
        if table.rows:
            position=table.columns.index(record['mapping']['订单号'])
            table=TableData(table.name,table.columns,sorted(table.rows,key=lambda r:str(r[position])),table.origin)
            content=map_order_table(table,record['mapping'],allow_empty=True)
        provenance={'source_id':record['id'],'kind':record['kind'],'source_kind':record['config'].get('kind','file'),
                    'table':record['table'],'schema':record['schema'],'mapping':record['mapping'],
                    'file_sha256':file_hash,'origin':table.origin,'currency':'CNY','grain':'one_complete_order_per_row'}
        canonical=json.dumps(provenance,ensure_ascii=False,sort_keys=True).encode('utf-8')
        return content,provenance,sha(content+canonical)

    def refresh(self,source_id,*,wait=False):
        with self._lock:
            record=self._record(source_id)
            future=self._futures.get(source_id)
            if not future or future.done():
                if self._stop.is_set():
                    raise ValueError('同步服务已经停止')
                if not record['mapping']:
                    raise ValueError('请先确认字段映射再刷新')
                record['state']='syncing'
                record['error']=None
                record['diagnostics']=None
                self._emit(source_id,'started')
                future=self._executor.submit(self._sync,source_id)
                self._futures[source_id]=future
        if wait:
            future.result(timeout=90)
        return self.get(source_id)

    def _sync(self,source_id):
        started=perf_counter()
        with self._lock:
            record=copy.deepcopy(self._record(source_id))
        try:
            content,provenance,fingerprint=self._acquire(record)
            acquired=now_iso()
            unchanged=fingerprint==record.get('content_fingerprint') and bool(record.get('snapshot_run_id'))
            result=None
            if not unchanged:
                provenance['acquired_at']=acquired
                result=import_csv(content,self.output_for(source_id),allow_empty=True,provenance=provenance)
            with self._lock:
                current=self._record(source_id)
                current.update(state='ready',error=None,diagnostics=None,last_check_at=now_iso(),last_acquired_at=acquired,
                               last_attempt_ms=round((perf_counter()-started)*1000,3))
                if result:
                    current.update(snapshot_run_id=result['run_id'],content_fingerprint=fingerprint,last_success_at=now_iso())
                self._persist()
                self._emit(source_id,'unchanged' if unchanged else 'updated')
        except Exception as error:
            with self._lock:
                current=self._record(source_id)
                message='读取或核验未完成，请检查连接、来源表和字段映射；上次成功数据仍保留。'
                if isinstance(error,ValueError) and record['kind']=='file':
                    message='文件读取或字段校验失败，请检查表头、金额、日期和订单粒度；上次成功数据仍保留。'
                diagnostics=error.diagnostics if isinstance(error,MappingValidationError) else None
                current.update(state='error',error=message,diagnostics=diagnostics,last_check_at=now_iso(),
                               last_attempt_ms=round((perf_counter()-started)*1000,3))
                self._persist()
                self._emit(source_id,'failed')

    def wait_for_idle(self,source_id,timeout=30):
        with self._lock:
            future=self._futures.get(source_id)
        if future:
            future.result(timeout=timeout)
        return self.get(source_id)

    def tick(self,now=None):
        now=monotonic() if now is None else now
        with self._lock:
            ids=[]
            for sid,record in self._records.items():
                if not record['mapping'] or (record.get('password_required') and sid not in self._secrets):
                    continue
                due=False
                for key,next_key in (('interval_seconds','next_interval'),('watch_seconds','next_watch')):
                    interval=record['refresh'][key]
                    if interval is not None and now>=record.get(next_key,0):
                        record[next_key]=now+interval
                        due=True
                if due:
                    ids.append(sid)
        for sid in ids:
            self.refresh(sid)

    def start(self):
        if self._thread is None:
            def run():
                while not self._stop.wait(.25):
                    try:
                        self.tick()
                    except (ValueError,RuntimeError):
                        continue
            self._thread=threading.Thread(target=run,name='zhishu-refresh',daemon=True)
            self._thread.start()

    def events_after(self,cursor,timeout=10):
        with self._condition:
            if not self._stop.is_set() and self._event_id<=cursor:
                self._condition.wait(timeout)
            if self._events and (cursor>self._event_id or cursor<self._events[0]['id']-1):
                return [{'id':self._event_id,'type':'reset','source_id':None,'at':now_iso()}]
            return [copy.deepcopy(e) for e in self._events if e['id']>cursor]

    @property
    def stopped(self):
        return self._stop.is_set()

    def remove(self,source_id):
        with self._lock:
            record=self._record(source_id)
            future=self._futures.get(source_id)
            if future and not future.done():
                raise ValueError('同步进行中，请稍后移除配置')
            del self._records[source_id]
            self._secrets.pop(source_id,None)
            self._persist()

    def close(self):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread:
            self._thread.join(timeout=2)
        self._executor.shutdown(wait=True,cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
