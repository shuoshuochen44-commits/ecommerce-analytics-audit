from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from zhishu_inspection.database import build_database
from zhishu_inspection.modeling import build_models
from zhishu_inspection.quality import evaluate_quality


@pytest.fixture
def con(tmp_path):
    db = tmp_path / "model.duckdb"
    build_database(Path("tests/fixtures/olist_mini"), db)
    connection = duckdb.connect(str(db))
    yield connection
    connection.close()


def test_model_grain_money_and_customer_identity(con):
    result = build_models(con)
    assert result["metrics"] == {
        "completed_product_amount": "230.00",
        "completed_order_count": 2,
        "completed_average_order_value": "115.00",
        "completed_unique_customer_count": 1,
    }
    assert con.execute(
        "SELECT product_amount, payment_amount, item_count, payment_count "
        "FROM dwd_orders WHERE order_id='o1'"
    ).fetchone() == (Decimal("150.00"), Decimal("165.00"), 2, 2)
    assert result["table_counts"]["dwd_order_items"] == 4
    assert con.execute("SELECT sum(product_amount) FROM dws_daily_state").fetchone()[0] == Decimal("230.00")


def test_missing_details_and_orphans_are_retained(con):
    con.execute("INSERT INTO raw_orders SELECT 'o4', 'unknown', 'delivered', "
                "'2018-02-02 09:00:00', NULL, '2018-02-08 00:00:00'")
    con.execute("UPDATE raw_order_items SET product_id='unknown' WHERE order_id='o3'")
    result = build_models(con)
    assert result["metrics"]["completed_order_count"] == 3
    assert result["metrics"]["completed_average_order_value"] == "76.67"
    assert con.execute("SELECT missing_customer, reconciliation_status FROM dwd_orders WHERE order_id='o4'").fetchone() == (True, "missing_both")
    assert con.execute("SELECT count(*) FROM dwd_order_items WHERE missing_product").fetchone()[0] == 1


def test_invalid_input_preserves_existing_models(con):
    build_models(con)
    con.execute("UPDATE raw_order_items SET price='bad' WHERE order_id='o1'")
    with pytest.raises(ValueError, match="Q07"):
        build_models(con)
    assert con.execute("SELECT product_amount FROM dwd_orders WHERE order_id='o1'").fetchone()[0] == Decimal("150.00")


def test_no_delivered_orders_has_null_average(con):
    con.execute("UPDATE raw_orders SET order_status='canceled'")
    result = build_models(con)
    assert result["metrics"]["completed_order_count"] == 0
    assert result["metrics"]["completed_average_order_value"] is None


@pytest.mark.parametrize("rule_id,mutation", [
    ("Q01", "UPDATE raw_orders SET order_id=NULL WHERE order_id='o1'"),
    ("Q02", "INSERT INTO raw_orders SELECT * FROM raw_orders WHERE order_id='o1'"),
    ("Q03", "INSERT INTO raw_order_items SELECT * FROM raw_order_items WHERE order_id='o3'"),
    ("Q04", "UPDATE raw_order_items SET order_id='absent' WHERE order_id='o3'"),
    ("Q05", "UPDATE raw_order_items SET product_id='absent' WHERE order_id='o3'"),
    ("Q06", "UPDATE raw_orders SET customer_id='absent' WHERE order_id='o3'"),
    ("Q07", "UPDATE raw_order_items SET price='-1' WHERE order_id='o3'"),
    ("Q10", "UPDATE raw_orders SET order_purchase_timestamp='bad' WHERE order_id='o3'"),
])
def test_required_quality_rules_detect_injected_failures(con, rule_id, mutation):
    passing = {row["rule_id"]: row for row in evaluate_quality(con)}
    assert passing[rule_id]["failed_count"] == 0
    con.execute(mutation)
    failing = {row["rule_id"]: row for row in evaluate_quality(con)}[rule_id]
    assert failing["failed_count"] > 0
    assert failing["sample_keys"]
    assert failing["affected_metrics"]


def test_duplicate_dimension_key_blocks_join_amplification(con):
    con.execute("INSERT INTO raw_customers SELECT * FROM raw_customers WHERE customer_id='c1'")
    with pytest.raises(ValueError, match="Q11"):
        build_models(con)


@pytest.mark.parametrize("price", ["-0.001", "1.234", "0.00000000001", "NaN", "Infinity"])
def test_money_validation_never_silently_rounds_invalid_source(con, price):
    con.execute("UPDATE raw_order_items SET price=? WHERE order_id='o3'", [price])
    rule = next(row for row in evaluate_quality(con) if row["rule_id"] == "Q07")
    assert rule["failed_count"] == 1


def test_blank_customer_identity_is_warned_and_excluded_without_blocking(con):
    con.execute("UPDATE raw_customers SET customer_unique_id='   '")
    result = build_models(con)
    assert result["metrics"]["completed_unique_customer_count"] == 0
    assert next(r for r in result["quality"] if r["rule_id"]=='Q16')["failed_count"] == 3


@pytest.mark.parametrize("sequence", ["01", "1.5", "0", None])
def test_payment_sequence_cannot_bypass_business_key_validation(con, sequence):
    con.execute("INSERT INTO raw_payments SELECT order_id, ?, payment_type, payment_installments, payment_value FROM raw_payments WHERE order_id='o3'", [sequence])
    with pytest.raises(ValueError, match="Q15"):
        build_models(con)
