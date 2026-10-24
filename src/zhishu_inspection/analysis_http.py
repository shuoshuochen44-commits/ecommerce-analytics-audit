"""Bounded desktop routes for the fixed-question, pinned-snapshot analysis engine."""

import json
import re
from decimal import Decimal
from urllib.parse import urlencode, urlsplit

from .analysis import analyze, get_run, replay
from .analytics import validate_dates
from .pipeline import load_snapshot
from .question_catalog import QUESTIONS


MAX_REQUEST_BYTES = 4096
SNAPSHOT_ID = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')


def _source_root(handler, source):
    if not isinstance(source, str) or len(source) > 80:
        raise ValueError('请选择有效的数据来源')
    root, _ = handler.read_query(urlsplit('/?' + urlencode({'source': source})), set())
    return root


def _read_body(handler, *, decimal_numbers=False):
    size = int(handler.headers.get('Content-Length', '0'))
    if not 0 < size <= MAX_REQUEST_BYTES:
        handler.close_connection = True
        handler.send_json(413, {'error': '分析请求不能为空或超过 4 KB'})
        return None
    handler.connection.settimeout(15)
    content = handler.rfile.read(size)
    if len(content) != size:
        raise ValueError('分析请求未完整传输，请重试')
    options = {'parse_float': Decimal, 'parse_constant': lambda _: (_ for _ in ()).throw(ValueError('无效数值'))} if decimal_numbers else {}
    data = json.loads(content.decode('utf-8'), **options)
    if not isinstance(data, dict):
        raise ValueError('分析请求必须为 JSON 对象')
    return data


def analysis_post(handler):
    if not handler.path.startswith('/api/analysis/'):
        return False
    if handler.path not in ('/api/analysis/ask', '/api/analysis/replay'):
        handler.send_json(404, {'error': '分析接口不存在'})
        return True
    try:
        data = _read_body(handler)
        if data is None:
            return True
        root = _source_root(handler, data.get('source'))
        asking = handler.path.endswith('/ask')
        if asking:
            if set(data) - {'source', 'snapshot_run_id', 'question', 'start', 'end', 'state'}:
                raise ValueError('分析请求包含不支持的选项')
            snapshot_id = data.get('snapshot_run_id')
            if not isinstance(snapshot_id, str) or not SNAPSHOT_ID.fullmatch(snapshot_id):
                raise ValueError('请先加载一个成功的数据版本后再分析')
            question = data.get('question')
            if not isinstance(question, str) or not question.strip() or len(question) > 500:
                raise ValueError('请选择目录问题，或输入不超过 500 字的问题文本')
            filters = {k: data.get(k) for k in ('start', 'end', 'state')}
            for key, value in filters.items():
                if value is not None and (not isinstance(value, str) or not value or len(value) > 50):
                    raise ValueError('日期与地区筛选格式不正确')
            validate_dates(filters['start'], filters['end'])
        elif set(data) != {'source', 'run_id'}:
            raise ValueError('重放需要数据来源和分析运行编号')
        slot = handler.server.analysis_slot
        if not slot.acquire(blocking=False):
            handler.send_json(409, {'error': '正在分析其他问题，请稍后再试'})
            return True
        try:
            if asking:
                # Fail before saving a run if the selected source does not own this snapshot.
                load_snapshot(root, snapshot_id)
                result = analyze(root, question, snapshot_run_id=snapshot_id, **filters)
            else:
                result = replay(root, data.get('run_id'))
        finally:
            slot.release()
        handler.send_json(200, {'source': handler.selected_source, 'run': result})
    except FileNotFoundError:
        handler.send_json(404, {'error': '当前来源中找不到该数据版本或分析记录，请重新加载来源'})
    except (ValueError, TypeError, UnicodeError):
        handler.send_json(400, {'error': '分析参数无效，请检查问题、数据来源、日期与运行编号'})
    except Exception:
        handler.send_json(503, {'error': '分析暂时无法完成，请保留当前数据并稍后重试'})
    return True


def analysis_get(handler, parsed):
    if not parsed.path.startswith('/api/analysis/'):
        return False
    try:
        if parsed.path == '/api/analysis/questions':
            if parsed.query:
                raise ValueError('问题目录不接受筛选参数')
            handler.send_json(200, {'mode': 'offline_templates', 'questions': [
                {'id': q.id, 'text': q.text, 'kind': q.kind, 'metric': q.metric,
                 'dimension': q.dimension, 'definition': q.definition} for q in QUESTIONS]})
        elif parsed.path in ('/api/analysis/run', '/api/analysis/download'):
            root, values = handler.read_query(parsed, {'run_id'})
            result = get_run(root, values.get('run_id'))
            if parsed.path.endswith('/download'):
                handler.send_content(200, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'),
                                     'application/json; charset=utf-8', result['run_id'] + '.json')
            else:
                handler.send_json(200, {'source': handler.selected_source, 'run': result})
        else:
            handler.send_json(404, {'error': '分析接口不存在'})
    except FileNotFoundError:
        handler.send_json(404, {'error': '当前来源中找不到该分析记录'})
    except (ValueError, TypeError):
        handler.send_json(400, {'error': '分析记录参数无效或完整性校验失败'})
    return True
