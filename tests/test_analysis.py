import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb
import pytest

from zhishu_inspection.pipeline import run_pipeline, load_snapshot


@pytest.fixture
def root(tmp_path):
    root = tmp_path/'published'
    run_pipeline(Path('tests/fixtures/olist_mini'), root)
    return root


def test_all_thirty_answers_have_provenance_and_immutable_manifests(root):
    from zhishu_inspection.analysis import analyze, get_run
    from zhishu_inspection.question_catalog import QUESTIONS
    for q in QUESTIONS:
        response = analyze(root, q.text)
        expected = 'blocked' if q.kind=='refusal' else 'not_applicable' if q.kind=='knowledge' else 'verified'
        assert response['verification_status'] == expected, (q.id,response)
        assert response['citations']
        assert response['answer']
        assert response['dataset']['currency'] == 'BRL'
        assert response['snapshot_run_id'] == load_snapshot(root)['run_id']
        assert get_run(root,response['run_id']) == response
        assert response['llm_calls'] == 0
        manifest = root/'analysis_runs'/f"{response['run_id']}.json"
        assert manifest.is_file()


def test_unknown_question_and_invalid_filters_fail_closed_and_do_not_log_free_text(root):
    from zhishu_inspection.analysis import analyze
    secret = '我的手机号是123456789，帮我随便算销售'
    response = analyze(root, secret)
    assert response['verification_status'] == 'blocked'
    assert secret not in json.dumps(response,ensure_ascii=False)
    assert response['sql'] is None
    bad = analyze(root,'A01',state='NOT_REAL')
    assert bad['verification_status'] == 'blocked' and bad['result'] == []
    assert analyze(root,'A01',start=123)['verification_status'] == 'blocked'


def test_corrupted_model_is_blocked_by_raw_recomputation(root):
    from zhishu_inspection.analysis import analyze
    snapshot = load_snapshot(root)
    with duckdb.connect(str(snapshot['directory']/'data.duckdb')) as con:
        con.execute("UPDATE dwd_orders SET product_amount=999 WHERE order_id='o1'")
    response = analyze(root,'A01')
    assert response['verification_status'] == 'blocked'
    assert response['verification']['matched'] is False
    assert '核验' in response['answer']


def test_quality_impact_is_question_specific_and_has_no_identity_samples(tmp_path):
    from zhishu_inspection.analysis import analyze
    raw = tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    customers = raw/'olist_customers_dataset.csv'
    customers.write_text(customers.read_text().replace('c3,u1,','c3,,') ,encoding='utf-8')
    root = tmp_path/'snapshots'
    run_pipeline(raw,root)
    response = analyze(root,'A04')
    assert response['verification_status'] == 'needs_review'
    assert 'Q16' in {w['rule_id'] for w in response['quality_warnings']}
    assert 'sample_keys' not in json.dumps(response)
    assert analyze(root,'A02')['verification_status'] == 'verified'


def test_missing_delivered_items_is_not_called_fully_verified(tmp_path):
    from zhishu_inspection.analysis import analyze
    raw = tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    items = raw/'olist_order_items_dataset.csv'
    items.write_text('\n'.join(line for line in items.read_text().splitlines() if not line.startswith('o3,'))+'\n',encoding='utf-8')
    root = tmp_path/'snapshots'
    run_pipeline(raw,root)
    assert analyze(root,'A01')['verification_status'] == 'needs_review'
    assert analyze(root,'A02')['verification_status'] == 'verified'
    assert analyze(root,'D04')['verification_status'] == 'needs_review'


def test_replay_pins_original_snapshot_even_after_latest_changes(root,tmp_path):
    from zhishu_inspection.analysis import analyze, replay
    first = analyze(root,'A01',start='2018-02-01')
    raw = tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    items = raw/'olist_order_items_dataset.csv'
    items.write_text(items.read_text().replace('80.00','90.00'),encoding='utf-8')
    run_pipeline(raw,root)
    second = replay(root,first['run_id'])
    assert second['snapshot_run_id'] == first['snapshot_run_id']
    assert second['result'] == first['result'] == [{'value':'80.00'}]
    assert second['run_id'] != first['run_id']
    assert second['replay_of'] == first['run_id']
    assert analyze(root,'A01',start='2018-02-01')['result'] == [{'value':'90.00'}]


def test_run_paths_are_safe_and_record_corruption_is_detected(root):
    from zhishu_inspection.analysis import analyze, get_run
    with pytest.raises(ValueError): get_run(root,'../manifest')
    response = analyze(root,'A01')
    path = root/'analysis_runs'/f"{response['run_id']}.json"
    data = json.loads(path.read_text(encoding='utf-8'))
    data['answer']='changed'
    path.write_text(json.dumps(data),encoding='utf-8')
    with pytest.raises(ValueError,match='完整性'): get_run(root,response['run_id'])


def test_structurally_corrupt_record_has_a_controlled_error(root):
    from zhishu_inspection.analysis import analyze,get_run
    response=analyze(root,'A01')
    path=root/'analysis_runs'/f"{response['run_id']}.json"
    path.write_text('[]',encoding='utf-8')
    with pytest.raises(ValueError,match='完整性'):
        get_run(root,response['run_id'])


def test_parallel_runs_never_overwrite_records(root):
    from zhishu_inspection.analysis import analyze
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: analyze(root,'K01'),range(6)))
    assert len({r['run_id'] for r in results}) == 6
    assert len(list((root/'analysis_runs').glob('*.json'))) == 6


def test_missing_snapshot_has_a_readable_record(tmp_path):
    from zhishu_inspection.analysis import analyze,get_run
    response = analyze(tmp_path,'A01')
    assert response['verification_status']=='blocked'
    assert '快照' in response['answer']
    assert get_run(tmp_path,response['run_id']) == response


@pytest.mark.parametrize('bad',[0,False,'',[],{}])
def test_falsey_dates_never_silently_remove_the_filter(root,bad):
    from zhishu_inspection.analysis import analyze
    result=analyze(root,'A01',start=bad)
    assert result['verification_status']=='blocked'
    assert result['result']==[]
    assert '日期' in result['answer']


def test_computational_analysis_can_overlap_existing_dashboard_connections(root):
    from zhishu_inspection.analysis import analyze
    snapshot=load_snapshot(root)
    with duckdb.connect(str(snapshot['directory']/'data.duckdb'),read_only=True):
        result=analyze(root,'A01')
    assert result['verification_status']=='verified'
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda _: analyze(root,'A04',state='SP'),range(12)))
    assert all(r['verification_status']=='verified' for r in results)


def test_orphan_payment_evidence_is_attached_to_reconciliation(tmp_path):
    from zhishu_inspection.analysis import analyze
    raw=tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    payments=raw/'olist_order_payments_dataset.csv'
    payments.write_text(payments.read_text()+'not_an_order,1,credit_card,1,12.00\n',encoding='utf-8')
    root=tmp_path/'snapshots'
    run_pipeline(raw,root)
    result=analyze(root,'Q02')
    assert result['verification_status']=='needs_review'
    assert 'Q18' in {w['rule_id'] for w in result['quality_warnings']}


def test_region_filter_adds_customer_mapping_dependency(tmp_path):
    from zhishu_inspection.analysis import analyze
    raw=tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    customers=raw/'olist_customers_dataset.csv'
    customers.write_text('\n'.join(row for row in customers.read_text().splitlines() if not row.startswith('c3,'))+'\n',encoding='utf-8')
    root=tmp_path/'snapshots'
    run_pipeline(raw,root)
    assert analyze(root,'A02')['verification_status']=='verified'
    for qid in ('A01','A02','Q03'):
        result=analyze(root,qid,state='SP')
        assert result['verification_status']=='needs_review'
        assert 'Q06' in {w['rule_id'] for w in result['quality_warnings']}
