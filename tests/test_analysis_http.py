"""Exercise the desktop question API against real, isolated snapshots."""

import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest
import duckdb

from zhishu_inspection.csv_import import COLUMNS, import_csv
from zhishu_inspection.server import create_server
from zhishu_inspection.pipeline import load_snapshot
from test_source_manager import csv_bytes


@pytest.fixture
def analysis_server(tmp_path):
    root = tmp_path / 'workspace'
    initial = import_csv(csv_bytes(), root)
    server = create_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}', server, root, initial['run_id']
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def request(base, path, data=None, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base + path, data=body,
        headers={'Content-Type': 'application/json', 'X-Zhishu-Local': '1', **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def ask(base, snapshot, **changes):
    return request(base, '/api/analysis/ask',
        {'source': 'demo', 'snapshot_run_id': snapshot, 'question': 'A01', **changes})


def test_catalog_and_pinned_filtered_answer_with_download_and_replay(analysis_server):
    base, _, root, snapshot = analysis_server
    catalog = request(base, '/api/analysis/questions')['questions']
    assert len(catalog) == 30
    assert {q['kind'] for q in catalog} == {'data', 'quality', 'knowledge', 'refusal'}
    import_csv(csv_bytes('200.00'), root)
    result = ask(base, snapshot, start='2026-01-01', end='2026-01-31', state='广东省')
    run = result['run']
    assert result['source'] == 'demo'
    assert run['snapshot_run_id'] == snapshot
    assert run['result'] == [{'value': '100.00'}]
    assert run['verification_status'] in ('verified', 'needs_review')
    assert run['sql'] and run['citations'] and run['record_sha256']
    query = urllib.parse.urlencode({'source': 'demo', 'run_id': run['run_id']})
    assert request(base, '/api/analysis/run?' + query)['run'] == run
    with urllib.request.urlopen(base + '/api/analysis/download?' + query) as response:
        assert 'attachment' in response.headers['Content-Disposition']
        assert json.load(response) == run
    replayed = request(base, '/api/analysis/replay', {'source': 'demo', 'run_id': run['run_id']})['run']
    assert replayed['replay_matches'] is True
    assert replayed['replay_of'] == run['run_id']
    assert replayed['snapshot_run_id'] == snapshot


def test_source_run_isolation_and_explicit_refusal(analysis_server):
    base, server, _, snapshot = analysis_server
    manager = server.source_manager
    sid = manager.register_upload('orders.csv', csv_bytes('325.00'))['id']
    manager.configure(sid, mapping={c: c for c in COLUMNS})
    source_snapshot = manager.refresh(sid, wait=True)['snapshot_run_id']
    run = ask(base, source_snapshot, source=sid)['run']
    assert run['result'] == [{'value': '325.00'}]
    for path in ('run', 'download'):
        with pytest.raises(urllib.error.HTTPError) as error:
            request(base, '/api/analysis/' + path + '?' + urllib.parse.urlencode({'source': 'demo', 'run_id': run['run_id']}))
        assert error.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as error:
        ask(base, snapshot, source=sid)
    assert error.value.code == 404
    for question in ('R01', 'DROP TABLE orders', '<script>alert(1)</script>'):
        refused = ask(base, snapshot, question=question)['run']
        assert refused['verification_status'] == 'blocked'
        assert refused['result'] == [] and refused['chart_spec'] is None
        assert refused['sql'] is None


def test_order_only_import_does_not_claim_real_product_ranking(analysis_server):
    base, _, _, snapshot = analysis_server
    result = ask(base, snapshot, question='D05')['run']
    assert result['verification_status'] == 'blocked'
    assert result['result'] == [] and result['sql'] is None
    assert '商品编号' in result['answer']


def test_failed_verification_has_no_business_figures_in_response_or_download(analysis_server):
    base, _, root, snapshot = analysis_server
    with duckdb.connect(str(load_snapshot(root)['directory'] / 'data.duckdb')) as con:
        con.execute('UPDATE dwd_orders SET product_amount=987654.32')
    run = ask(base, snapshot)['run']
    assert run['verification_status'] == 'blocked'
    assert run['verification']['matched'] is False
    assert run['result'] == [] and run['chart_spec'] is None
    query = urllib.parse.urlencode({'source': 'demo', 'run_id': run['run_id']})
    downloaded = request(base, '/api/analysis/download?' + query)
    assert downloaded['result'] == []
    assert '987654.32' not in json.dumps(downloaded)


def test_invalid_region_cannot_replay_as_all_regions(analysis_server):
    base, _, _, snapshot = analysis_server
    run = ask(base, snapshot, state='不存在的地区')['run']
    assert run['verification_status'] == 'blocked'
    with pytest.raises(urllib.error.HTTPError) as error:
        request(base, '/api/analysis/replay', {'source': 'demo', 'run_id': run['run_id']})
    assert error.value.code == 400


@pytest.mark.parametrize('changes', [
    {'snapshot_run_id': None}, {'snapshot_run_id': '../latest'}, {'source': '../../'},
    {'source': []}, {'question': []}, {'question': 'x' * 501}, {'sql': 'SELECT 1'},
    {'start': 123}, {'end': '2026-13-01'}, {'state': []},
])
def test_analysis_rejects_malformed_inputs(analysis_server, changes):
    base, _, _, snapshot = analysis_server
    with pytest.raises(urllib.error.HTTPError) as error:
        ask(base, snapshot, **changes)
    assert error.value.code == 400


def test_analysis_origin_size_and_concurrency_are_bounded(analysis_server):
    base, server, _, snapshot = analysis_server
    with pytest.raises(urllib.error.HTTPError) as error:
        request(base, '/api/analysis/ask', {'source': 'demo', 'snapshot_run_id': snapshot, 'question': 'A01'}, {'Origin': 'https://foreign.example'})
    assert error.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as error:
        ask(base, snapshot, question='a' * 5000)
    assert error.value.code == 413
    server.analysis_slot.acquire()
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            ask(base, snapshot)
        assert error.value.code == 409
    finally:
        server.analysis_slot.release()


def test_empty_workspace_has_catalog_without_fabricated_answer(tmp_path):
    server = create_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        assert len(request(base, '/api/analysis/questions')['questions']) == 30
        with pytest.raises(urllib.error.HTTPError) as error:
            ask(base, '20261019T000000Z_123456789abc')
        assert error.value.code == 404
        assert not (tmp_path / 'latest.json').exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
