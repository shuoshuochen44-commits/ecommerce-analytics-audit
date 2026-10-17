from pathlib import Path

import duckdb
import pytest

from zhishu_inspection.pipeline import run_pipeline, load_snapshot


@pytest.fixture
def database(tmp_path):
    root = tmp_path / 'snapshots'
    run_pipeline(Path('tests/fixtures/olist_mini'), root)
    return load_snapshot(root)['directory'] / 'data.duckdb'


def execute(database, sql, parameters=(), **limits):
    from zhishu_inspection.query_gateway import execute_readonly
    return execute_readonly(database, sql, parameters, **limits)


def test_select_and_cte_use_parameters_and_decimal(database):
    result = execute(database, "WITH t AS (SELECT product_amount FROM dwd_orders WHERE order_status=?) SELECT sum(product_amount) AS value FROM t", ('delivered',))
    assert result == [{'value': '230.00'}]


@pytest.mark.parametrize('sql', [
    'DELETE FROM dwd_orders',
    'CREATE TABLE stolen AS SELECT * FROM dwd_orders',
    'SELECT count(*) FROM dwd_orders; SELECT 1',
    'SELECT * FROM raw_customers',
    'SELECT customer_city FROM dwd_orders',
    'SELECT absent FROM dwd_orders',
    'SELECT * FROM dwd_orders',
    "SELECT * FROM read_csv('/etc/passwd')",
    "SELECT read_blob('/etc/passwd')",
    "SELECT current_setting('home_directory')",
    'SELECT * FROM information_schema.tables',
    'SELECT * FROM duckdb_settings()',
    'SELECT count(*) FROM range(100000000)',
    'SELECT count(*) FROM dwd_orders a CROSS JOIN dwd_orders b',
    'SELECT count(*) FROM dwd_orders a, dwd_orders b',
    'SELECT count(*) FROM dwd_orders a JOIN dwd_orders b ON TRUE',
    'SELECT count(*) FROM dwd_orders a JOIN dwd_order_items b ON a.order_id=b.order_id OR 1=1',
    'SELECT count(*) FROM dwd_orders a JOIN dwd_order_items b ON a.order_id=a.order_id',
    'WITH t AS (SELECT 1 AS order_id FROM dwd_orders) SELECT count(*) FROM t a JOIN t b ON a.order_id=b.order_id',
    "WITH dwd_orders AS (SELECT 'x' AS order_id FROM dwd_orders), dwd_order_items AS (SELECT 'x' AS order_id FROM dwd_order_items) SELECT count(*) FROM dwd_orders o JOIN dwd_order_items i ON o.order_id=i.order_id",
    "WITH dwd_orders AS (SELECT 'x' AS order_id FROM dwd_orders), dwd_order_items AS (SELECT 'x' AS order_id FROM dwd_order_items) SELECT count(*) FROM dwd_orders JOIN dwd_order_items USING(order_id)",
    'WITH RECURSIVE t AS (SELECT 1 UNION ALL SELECT 1 FROM t) SELECT count(*) FROM t',
    'WITH t AS (SELECT customer_city FROM dwd_orders) SELECT count(*) FROM t',
    'SELECT count(*) FROM main.dwd_orders',
    'SELECT count(*) FROM dwd_orders TABLESAMPLE (10 PERCENT)',
])
def test_rejects_untrusted_sql_without_mutating_database(database, sql):
    with pytest.raises(ValueError):
        execute(database, sql)
    with duckdb.connect(str(database), read_only=True) as con:
        assert con.execute('SELECT count(*) FROM dwd_orders').fetchone()[0] == 3


def test_limits_are_fail_closed(database):
    with pytest.raises(ValueError, match='预算'):
        execute(database, 'SELECT count(*) AS value FROM dwd_orders', max_source_rows=2)
    with pytest.raises(ValueError, match='行数'):
        execute(database, 'SELECT order_status FROM dwd_orders', max_rows=1)
    with pytest.raises(ValueError, match='超时'):
        execute(database, 'SELECT count(*) FROM dwd_orders', timeout_seconds=0.000001)
    with pytest.raises(ValueError):
        execute(database, 'SELECT count(*) FROM dwd_orders', max_rows=0)
