from pathlib import Path

import duckdb

from zhishu_inspection.database import build_database


def test_fixture_payments_match_item_and_freight_totals(tmp_path: Path) -> None:
    database_path = tmp_path / "zhishu.duckdb"
    build_database(Path("tests/fixtures/olist_mini"), database_path)
    sql = Path("sql/quality/payment_reconciliation.sql").read_text(
        encoding="utf-8"
    )
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(sql).fetchall()
    finally:
        connection.close()

    assert len(rows) == 3
    assert {row[4] for row in rows} == {"matched"}
    assert {row[3] for row in rows} == {0}
