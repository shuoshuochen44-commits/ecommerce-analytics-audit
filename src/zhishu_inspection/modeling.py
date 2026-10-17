"""Build typed models without multiplying order-level amounts."""

from decimal import Decimal
from pathlib import Path

from .quality import evaluate_quality


SQL_ROOT = Path(__file__).resolve().parents[2] / "sql"
MODEL_TABLES = ("dim_customer_mapping", "dim_products", "dwd_order_items",
                "dwd_order_payments", "dwd_orders", "dws_daily_state")
METRICS = ("completed_product_amount", "completed_order_count",
           "completed_average_order_value", "completed_unique_customer_count")


def json_value(value):
    return format(value, "f") if isinstance(value, Decimal) else value


def model_metrics(connection):
    values = connection.execute("SELECT * FROM ads_overview").fetchone()
    return dict(zip(METRICS, map(json_value, values)))


def build_models(connection):
    rules = evaluate_quality(connection)
    blocked = [r["rule_id"] for r in rules if r["blocking"] and r["failed_count"]]
    if blocked:
        raise ValueError("Blocking quality rules: " + ", ".join(blocked))
    connection.execute("BEGIN TRANSACTION")
    try:
        for filename in ("dimensions", "items", "payments", "orders", "summaries"):
            connection.execute((SQL_ROOT / "model" / f"{filename}.sql").read_text(encoding="utf-8"))
        metrics = model_metrics(connection)
        for name, value in metrics.items():
            baseline_sql = (SQL_ROOT / "metrics" / f"{name}.sql").read_text(encoding="utf-8")
            expected = json_value(connection.execute(baseline_sql).fetchone()[0])
            if expected != value:
                raise ValueError(f"Metric mismatch: {name}: {value} != {expected}")
        counts = {table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in MODEL_TABLES}
        for raw, model in (("raw_orders", "dwd_orders"), ("raw_order_items", "dwd_order_items")):
            if connection.execute(f"SELECT count(*) FROM {raw}").fetchone()[0] != counts[model]:
                raise ValueError(f"Grain violation: {model}")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return {"table_counts": counts, "metrics": metrics, "quality": rules}
