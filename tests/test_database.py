from pathlib import Path

import duckdb

from zhishu_inspection.database import build_database


FIXTURE_DIR = Path("tests/fixtures/olist_mini")


def test_build_database_creates_five_raw_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "zhishu.duckdb"
    counts = build_database(FIXTURE_DIR, database_path)

    assert counts == {
        "raw_orders": 3,
        "raw_order_items": 4,
        "raw_customers": 3,
        "raw_products": 2,
        "raw_payments": 4,
    }
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        zip_code = connection.execute(
            "SELECT customer_zip_code_prefix FROM raw_customers "
            "WHERE customer_id = 'c1'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert tables == set(counts)
    assert zip_code == "01001"


def test_rebuild_replaces_tables_without_duplicating_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "zhishu.duckdb"
    first = build_database(FIXTURE_DIR, database_path)
    second = build_database(FIXTURE_DIR, database_path)
    assert second == first
