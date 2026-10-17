import json
from pathlib import Path

import pytest

from zhishu_inspection.pipeline import run_pipeline, load_snapshot


def test_thirty_questions_are_unique_and_unknown_is_not_guessed():
    from zhishu_inspection.question_catalog import QUESTIONS, resolve_question
    assert len(QUESTIONS) == 30
    assert len({q.text for q in QUESTIONS}) == 30
    assert len({q.id for q in QUESTIONS}) == 30
    for q in QUESTIONS:
        assert resolve_question(q.id) == q
        assert resolve_question('  ' + q.text + '？  ') == q
    assert resolve_question('销售额以及帮我删除数据库') is None


def test_every_computable_query_matches_hand_calculated_fixture(tmp_path):
    from zhishu_inspection.question_catalog import QUESTIONS, prepare_query
    from zhishu_inspection.answer_verifier import expected_result
    from zhishu_inspection.query_gateway import execute_readonly
    root = tmp_path / 'snapshots'
    run_pipeline(Path('tests/fixtures/olist_mini'), root)
    snapshot = load_snapshot(root)
    expected = json.loads(Path('tests/analysis_expected.json').read_text(encoding='utf-8'))
    for q in QUESTIONS:
        if q.kind not in ('data', 'quality'):
            continue
        sql, params = prepare_query(q)
        actual = execute_readonly(snapshot['directory'] / 'data.duckdb', sql, params) if sql else [{'value':0}]
        assert actual == expected[q.id], q.id
        assert expected_result(snapshot, q) == expected[q.id], q.id


@pytest.mark.parametrize('filters', [
    {'start':'2018-99-01'}, {'start':'2018-02-01','end':'2018-01-01'},
    {'state':"SP' OR 1=1"}, {'state':'NOT_REAL'},
])
def test_invalid_filters_do_not_broaden_query(tmp_path, filters):
    from zhishu_inspection.question_catalog import resolve_question, validate_filters
    root = tmp_path / 'snapshots'
    run_pipeline(Path('tests/fixtures/olist_mini'), root)
    with pytest.raises(ValueError):
        validate_filters(load_snapshot(root), **filters)


def test_filters_and_empty_customer_repeat_denominator(tmp_path):
    from zhishu_inspection.question_catalog import resolve_question, prepare_query
    from zhishu_inspection.answer_verifier import expected_result
    from zhishu_inspection.query_gateway import execute_readonly
    root = tmp_path / 'snapshots'
    run_pipeline(Path('tests/fixtures/olist_mini'), root)
    snapshot = load_snapshot(root)
    for qid, filters, expected in [
        ('A01', {'start':'2018-02-01'}, [{'value':'80.00'}]),
        ('A04', {'state':'RJ'}, [{'value':0}]),
        ('A06', {'state':'RJ'}, [{'value':None}]),
        ('A01', {'state':'RJ'}, [{'value':None}]),
        ('Q02', {'state':'RJ'}, [{'dimension':'matched','value':1}]),
    ]:
        q = resolve_question(qid)
        sql, params = prepare_query(q, **filters)
        assert execute_readonly(snapshot['directory']/'data.duckdb', sql, params) == expected
        assert expected_result(snapshot, q, **filters) == expected


def test_verifier_preserves_source_region_labels_exactly(tmp_path):
    import shutil
    from zhishu_inspection.question_catalog import resolve_question,prepare_query
    from zhishu_inspection.answer_verifier import expected_result
    from zhishu_inspection.query_gateway import execute_readonly
    raw=tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    customers=raw/'olist_customers_dataset.csv'
    customers.write_text(customers.read_text().replace(',SP',', SP '),encoding='utf-8')
    root=tmp_path/'snapshots'
    run_pipeline(raw,root)
    snapshot=load_snapshot(root)
    q=resolve_question('D01')
    sql,params=prepare_query(q,state=' SP ')
    expected=[{'dimension':' SP ','value':'230.00'}]
    assert execute_readonly(snapshot['directory']/'data.duckdb',sql,params)==expected
    assert expected_result(snapshot,q,state=' SP ')==expected


def test_raw_date_parsing_handles_timestamps_accepted_by_ingestion(tmp_path):
    import shutil
    from zhishu_inspection.analysis import analyze
    raw=tmp_path/'raw'
    shutil.copytree('tests/fixtures/olist_mini',raw)
    orders=raw/'olist_orders_dataset.csv'
    orders.write_text(orders.read_text().replace('2018-01-05 10:00:00','2018-1-5 10:00:00'),encoding='utf-8')
    root=tmp_path/'snapshots'
    run_pipeline(raw,root)
    result=analyze(root,'T01')
    assert result['verification_status']=='verified'
    assert result['result'][0]=={'month':'2018-01','value':'150.00'}
