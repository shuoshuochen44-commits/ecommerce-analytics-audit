"""Pinned, loopback-only full anomaly detection and saved report downloads."""

import json

from .analysis_http import SNAPSHOT_ID, _read_body, _source_root
from .anomalies import detect_anomalies, get_anomaly_run
from .anomaly_models import AnomalySuiteConfig
from .anomaly_reports import render_anomaly_html
from .pipeline import load_snapshot


def anomaly_post(handler) -> bool:
    if not handler.path.startswith('/api/anomalies/'):
        return False
    if handler.path != '/api/anomalies/detect':
        handler.send_json(404, {'error': '异常检测接口不存在'})
        return True
    try:
        data = _read_body(handler, decimal_numbers=True)
        if data is None:
            return True
        if set(data) - {'source', 'snapshot_run_id', 'start', 'end', 'state', 'category', 'config'}:
            raise ValueError('不支持的参数')
        root = _source_root(handler, data.get('source'))
        snapshot = data.get('snapshot_run_id')
        if not isinstance(snapshot, str) or not SNAPSHOT_ID.fullmatch(snapshot):
            raise ValueError('需要有效快照')
        config = AnomalySuiteConfig.from_mapping(data.get('config', {}))
        slot = handler.server.analysis_slot
        if not slot.acquire(blocking=False):
            handler.send_json(409, {'error': '当前有分析或检测任务正在运行，请稍后重试'})
            return True
        try:
            load_snapshot(root, snapshot)
            report = detect_anomalies(root, snapshot_run_id=snapshot, rules='all', config=config,
                                      **{key: data.get(key) for key in ('start', 'end', 'state', 'category')})
        finally:
            slot.release()
        handler.send_json(200, {'source': handler.selected_source, 'run': report})
    except FileNotFoundError:
        handler.send_json(404, {'error': '当前来源中找不到该成功快照，请重新加载来源'})
    except (ValueError, TypeError, UnicodeError):
        handler.send_json(400, {'error': '检测参数、筛选或预算无效，请核对来源、日期、品类和配置；未保存部分结论'})
    except Exception:
        handler.send_json(503, {'error': '检测未完成，上次结果仍保留，请检查成功快照后重试'})
    return True


def anomaly_get(handler, parsed) -> bool:
    if not parsed.path.startswith('/api/anomalies/'):
        return False
    if parsed.path not in ('/api/anomalies/run', '/api/anomalies/download', '/api/anomalies/snapshot'):
        handler.send_json(404, {'error': '异常检测接口不存在'})
        return True
    try:
        downloading = parsed.path.endswith('/download')
        root, values = handler.read_query(parsed, {'run_id', 'format'} if downloading else {'run_id'})
        kind = values.get('format', 'json')
        if kind not in ('json', 'html'):
            raise ValueError('格式不支持')
        report = get_anomaly_run(root, values.get('run_id'))
        if parsed.path.endswith('/snapshot'):
            snapshot = load_snapshot(root, report['snapshot_id'])
            manifest = snapshot['manifest']
            if manifest['input_fingerprint'] != report['source_fingerprint']:
                raise ValueError('来源指纹不一致')
            evidence = {'snapshot_id': snapshot['run_id'], 'source_fingerprint': manifest['input_fingerprint'],
                        'model_version': manifest['model_version'], 'created_at': manifest['finished_at'],
                        'currency': manifest['dataset']['currency'],
                        'inputs': [{key: item[key] for key in ('filename','size_bytes','sha256')}
                                   for item in manifest['inputs']]}
            handler.send_content(200, json.dumps(evidence, ensure_ascii=False, indent=2).encode('utf-8'),
                                 'application/json; charset=utf-8', report['run_id'] + '-snapshot.json')
        elif not downloading:
            handler.send_json(200, {'source': handler.selected_source, 'run': report})
        else:
            content = (render_anomaly_html(report) if kind == 'html' else
                       json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
            handler.send_content(200, content.encode('utf-8'),
                                 'text/html; charset=utf-8' if kind == 'html' else 'application/json; charset=utf-8',
                                 report['run_id'] + '.' + kind)
    except FileNotFoundError:
        handler.send_json(404, {'error': '当前来源中找不到该检测记录'})
    except (ValueError, TypeError):
        handler.send_json(400, {'error': '检测记录参数或完整性校验无效'})
    except Exception:
        handler.send_json(503, {'error': '暂时无法读取检测记录，请保留当前数据'})
    return True
