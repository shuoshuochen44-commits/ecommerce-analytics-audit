from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from zhishu_inspection.database import build_database


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "zhishu.duckdb"
    build_database(Path("tests/fixtures/olist_mini"), path)
    return path


def _metric(database_path: Path, filename: str):
    sql = Path("sql/metrics", filename).read_text(encoding="utf-8")
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


def test_completed_product_amount(database_path: Path) -> None:
    assert _metric(database_path, "completed_product_amount.sql") == Decimal(
        "230.00"
    )


def test_completed_order_count(database_path: Path) -> None:
    assert _metric(database_path, "completed_order_count.sql") == 2


def test_completed_average_order_value(database_path: Path) -> None:
    assert _metric(database_path, "completed_average_order_value.sql") == Decimal(
        "115.00"
    )


def test_average_order_value_counts_delivered_orders_without_items(
    database_path: Path,
) -> None:
    connection = duckdb.connect(str(database_path))
    try:
        connection.execute(
            """
            INSERT INTO raw_orders (
                order_id,
                customer_id,
                order_status,
                order_purchase_timestamp,
                order_delivered_customer_date,
                order_estimated_delivery_date
            )
            VALUES (
                'o4',
                'c2',
                'delivered',
                '2018-02-02 09:00:00',
                '2018-02-09 13:00:00',
                '2018-02-08 00:00:00'
            )
            """
        )
    finally:
        connection.close()

    assert _metric(database_path, "completed_average_order_value.sql") == Decimal(
        "76.67"
    )


def test_completed_unique_customer_count(database_path: Path) -> None:
    assert _metric(database_path, "completed_unique_customer_count.sql") == 1
