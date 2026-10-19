"""Loopback management routes and bounded SSE clients for connected sources."""

import json
from urllib.parse import unquote

from .csv_import import COLUMNS
from .database_sources import database_capabilities
from .source_types import MAX_BYTES
from .tabular_mapping import MappingValidationError, suggest_mapping


def source_post(handler,manager):
    path=handler.path
    if not path.startswith('/api/sources/'):
        return False
    try:
        maximum=MAX_BYTES if path=='/api/sources/upload' else 65536
        size=int(handler.headers.get('Content-Length','0'))
        if not 0<size<=maximum:
            handler.close_connection=True
            handler.send_json(413,{'error':'上传文件须在 20 MB 内，连接设置须在 64 KB 内'})
            return True
        handler.connection.settimeout(30)
        content=handler.rfile.read(size)
        if len(content)!=size:
            raise ValueError('请求未完整传输，请重试')
        if path=='/api/sources/upload':
            source=manager.register_upload(unquote(handler.headers.get('X-Zhishu-Filename','')),content)
            result={'source':source}
        else:
            data=json.loads(content.decode('utf-8'),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('无效 JSON 数值')))
            if not isinstance(data,dict):
                raise ValueError('连接设置必须是 JSON 对象')
            source_id=data.get('source_id')
            if path=='/api/sources/register':
                if set(data)-{'kind','path','name','config'}:
                    raise ValueError('不支持的来源参数')
                if data.get('kind')=='file':
                    if not isinstance(data.get('path'),str):
                        raise ValueError('请填写本机文件的绝对路径')
                    result={'source':manager.register_file(data['path'],name=data.get('name'))}
                elif data.get('kind')=='database':
                    result={'source':manager.register_database(data.get('config'),name=data.get('name'))}
                else:
                    raise ValueError('请选择文件或数据库入口')
            elif path=='/api/sources/preview':
                if set(data)-{'source_id','table','schema'}:
                    raise ValueError('不支持的预览参数')
                preview=manager.preview(source_id,table=data.get('table'),schema=data.get('schema'))
                result={'preview':preview,'suggested_mapping':suggest_mapping(preview['columns']),
                        'remembered_mapping':preview['remembered_mapping'],'mapping_origin':preview['mapping_origin']}
            elif path=='/api/sources/validate':
                if set(data)-{'source_id','table','schema','mapping'}:
                    raise ValueError('不支持的数据检查参数')
                result={'validation':manager.validate(source_id,**{k:v for k,v in data.items() if k!='source_id'})}
            elif path=='/api/sources/configure':
                if set(data)-{'source_id','table','schema','mapping','refresh'}:
                    raise ValueError('不支持的字段映射或刷新设置')
                result={'source':manager.configure(source_id,**{k:v for k,v in data.items() if k!='source_id'})}
            elif path=='/api/sources/refresh':
                if set(data)!={'source_id'}:
                    raise ValueError('请提供要刷新的数据源')
                result={'source':manager.refresh(source_id)}
            elif path=='/api/sources/credentials':
                if set(data)!={'source_id','password'}:
                    raise ValueError('请提供数据源及连接密码')
                result={'source':manager.set_credentials(source_id,data['password'])}
            elif path=='/api/sources/remove':
                if set(data)!={'source_id'}:
                    raise ValueError('请提供要移除的配置')
                manager.remove(source_id)
                result={'removed':True,'message':'连接配置已移除，历史快照文件仍保留'}
            else:
                handler.send_json(404,{'error':'接口不存在'})
                return True
        handler.send_json(200,result)
    except MappingValidationError as error:
        handler.send_json(400,{'error':'映射后数据校验未通过，请按行列提示修改来源数据。','diagnostics':error.diagnostics})
    except ValueError as error:
        handler.send_json(400,{'error':str(error)[:300] or '接入设置或文件校验未通过'})
    except (TypeError,UnicodeError):
        handler.send_json(400,{'error':'接入设置格式不正确，请检查来源表、字段映射和连接参数。'})
    except Exception:
        handler.send_json(503,{'error':'来源暂时无法读取；请检查文件、驱动和连接。密码及底层错误不会返回页面。'})
    return True


def source_get(handler,manager,parsed):
    if parsed.path=='/api/sources':
        if parsed.query:
            raise ValueError('不支持的数据源列表参数')
        handler.send_json(200,{'sources':manager.list_sources(),'database_capabilities':database_capabilities(),
                               'workspace_available':(manager.root/'latest.json').is_file(),
                               'customer_available':(manager.root/'customer-data'/'latest.json').is_file(),
                               'fields':list(COLUMNS),'limits':{'rows':20000,'file_bytes':MAX_BYTES}})
        return True
    if parsed.path!='/api/sources/events':
        return False
    host=handler.headers.get('Host','')
    if (parsed.query or handler.headers.get('Origin','http://'+host)!='http://'+host
            or 'text/event-stream' not in handler.headers.get('Accept','')):
        handler.send_json(403,{'error':'事件推送仅限本机同源页面'})
        return True
    try:
        cursor=int(handler.headers.get('Last-Event-ID','0'))
        if cursor<0:raise ValueError()
    except ValueError:
        handler.send_json(400,{'error':'无效事件游标'})
        return True
    slots=handler.server.event_slots
    if not slots.acquire(blocking=False):
        handler.send_json(429,{'error':'打开的实时页面过多，请关闭不用的页面'})
        return True
    try:
        handler.send_response(200)
        handler.send_header('Content-Type','text/event-stream; charset=utf-8')
        handler.send_header('Cache-Control','no-store')
        handler.send_header('X-Content-Type-Options','nosniff')
        handler.send_header('Connection','close')
        handler.end_headers()
        handler.connection.settimeout(15)
        while not manager.stopped:
            events=manager.events_after(cursor,timeout=5)
            if not events:
                handler.wfile.write(b': keepalive\n\n')
            for event in events:
                cursor=event['id']
                encoded=json.dumps(event,ensure_ascii=False,allow_nan=False)
                handler.wfile.write(f'id: {cursor}\nevent: source\ndata: {encoded}\n\n'.encode('utf-8'))
            handler.wfile.flush()
    except (BrokenPipeError,ConnectionError,OSError):
        pass
    finally:
        slots.release()
        handler.close_connection=True
    return True
