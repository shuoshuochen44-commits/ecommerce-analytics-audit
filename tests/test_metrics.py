from decimal import Decimal
from pathlib import Path

import duckdb


FIXTURE_DIR = Path("tests/fixtures/olist_mini").resolve()


def _load_views(connection: duckdb.DuckDBPyConnection) -> None:
    orders = str(FIXTURE_DIR / "olist_orders_dataset.csv").replace("'", "''")
    items = str(FIXTURE_DIR / "olist_order_items_dataset.csv").replace("'", "''")
    connection.execute(
        f"CREATE VIEW orders AS SELECT * FROM "
        f"read_csv('{orders}', header=true, all_varchar=true)"
    )
    connection.execute(
        f"CREATE VIEW order_items AS SELECT * FROM "
        f"read_csv('{items}', header=true, all_varchar=true)"
    )


def _run_metric(filename: str):
    connection = duckdb.connect(":memory:")
    try:
        _load_views(connection)
        sql = Path("sql/metrics", filename).read_text(encoding="utf-8")
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


def test_completed_order_count_is_two() -> None:
    assert _run_metric("completed_order_count.sql") == 2


def test_completed_product_amount_is_230() -> None:
    assert _run_metric("completed_product_amount.sql") == Decimal("230.00")


def test_naive_order_payment_join_would_multiply_item_amount() -> None:
    connection = duckdb.connect(":memory:")
    try:
        _load_views(connection)
        payments = str(
            FIXTURE_DIR / "olist_order_payments_dataset.csv"
        ).replace("'", "''")
        connection.execute(
            f"CREATE VIEW payments AS SELECT * FROM "
            f"read_csv('{payments}', header=true, all_varchar=true)"
        )
        naive = connection.execute(
            "SELECT sum(CAST(i.price AS DECIMAL(18, 2))) FROM order_items i "
            "JOIN orders o USING(order_id) JOIN payments p USING(order_id) "
            "WHERE o.order_status = 'delivered'"
        ).fetchone()[0]
        assert naive == Decimal("380.00")
        assert naive != Decimal("230.00")
    finally:
        connection.close()
