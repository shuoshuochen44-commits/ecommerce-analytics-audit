"""Fixed, parameterized read-only queries for one published snapshot."""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar

import duckdb

from .modeling import json_value
from .dataset import OLIST_DATASET
from .pipeline import load_snapshot


def rows(connection, sql, parameters=()):
    cursor = connection.execute(sql, parameters)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, map(json_value, row))) for row in cursor.fetchall()]


def validate_dates(start, end):
    for label, value in (("开始日期", start), ("结束日期", end)):
        if value:
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(f"{label}必须为 YYYY-MM-DD") from None
    if start and end and start > end:
        raise ValueError("开始日期不能晚于结束日期")


METRIC_SQL = (
    "SELECT CAST(sum(o.product_amount) AS DECIMAL(18,2)) AS completed_product_amount, "
    "count(*) AS completed_order_count, "
    "CAST(sum(o.product_amount)/nullif(count(*),0) AS DECIMAL(18,2)) AS completed_average_order_value, "
    "count(DISTINCT o.customer_unique_id) AS completed_unique_customer_count FROM dwd_orders o"
)


def month_comparison(connection, metrics, bounds, start, end, state):
    unavailable = {"available": False, "reason": "选择一个完整月份，即可与上月比较"}
    if not start or not end:
        return unavailable
    beginning, ending = date.fromisoformat(start), date.fromisoformat(end)
    last = date(beginning.year, beginning.month, calendar.monthrange(beginning.year, beginning.month)[1])
    if beginning.day != 1 or ending != last:
        return unavailable
    previous_end = beginning - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    if bounds[0] is None or bounds[0] > previous_start or bounds[1] < ending:
        return {"available": False, "reason": "数据日期未覆盖本月和上月的完整范围，暂不计算环比"}
    where, params = " WHERE o.order_status='delivered' AND o.purchase_date BETWEEN ? AND ?", [previous_start, previous_end]
    if state == "__unknown__":
        where += " AND o.customer_state IS NULL"
    elif state:
        where += " AND o.customer_state=?"
        params.append(state)
    previous = rows(connection, METRIC_SQL + where, params)[0]
    changes = {}
    for name, value in metrics.items():
        old = previous[name]
        difference = None if value is None or old is None else Decimal(str(value))-Decimal(str(old))
        percent = None if difference is None or not old or Decimal(str(old)) == 0 else str((difference/Decimal(str(old))*100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        changes[name] = {"previous": old, "difference": json_value(difference), "percent": percent}
    return {"available": True, "previous_start": previous_start.isoformat(), "previous_end": previous_end.isoformat(),
            "changes": changes, "note": "两期均按当前地区重新统计；日期覆盖不保证源交易完整"}


def dashboard_data(output_root, start=None, end=None, state=None, run_id=None, *, allow_absent_state=False):
    validate_dates(start, end)
    snapshot = load_snapshot(output_root, run_id=run_id)
    connection = duckdb.connect(str(snapshot["directory"] / "data.duckdb"), read_only=True)
    try:
        bounds = connection.execute("SELECT min(purchase_date), max(purchase_date) FROM dwd_orders").fetchone()
        states = [r[0] for r in connection.execute("SELECT DISTINCT customer_state FROM dwd_orders WHERE customer_state IS NOT NULL ORDER BY 1").fetchall()]
        months = [r[0] for r in connection.execute("SELECT DISTINCT strftime(purchase_date, '%Y-%m') FROM dwd_orders ORDER BY 1").fetchall()]
        if state and (len(state)>80 or any(ord(c)<32 for c in state)):
            raise ValueError("地区筛选格式不正确")
        if state and state != "__unknown__" and state not in states and not allow_absent_state:
            raise ValueError("请选择数据中存在的地区")
        conditions, parameters = ["o.order_status='delivered'"], []
        if start:
            conditions.append("o.purchase_date>=CAST(? AS DATE)")
            parameters.append(start)
        if end:
            conditions.append("o.purchase_date<=CAST(? AS DATE)")
            parameters.append(end)
        if state == "__unknown__":
            conditions.append("o.customer_state IS NULL")
        elif state:
            conditions.append("o.customer_state=?")
            parameters.append(state)
        where = " WHERE " + " AND ".join(conditions)
        metrics = rows(connection, METRIC_SQL + where, parameters)[0]
        comparison = month_comparison(connection, metrics, bounds, start, end, state)
        monthly = rows(connection,
            "SELECT strftime(o.purchase_date, '%Y-%m') AS month, "
            "CAST(sum(o.product_amount) AS DECIMAL(18,2)) AS product_amount, "
            "count(*) AS order_count, count(DISTINCT o.customer_unique_id) AS customer_count "
            "FROM dwd_orders o" + where + " GROUP BY 1 ORDER BY 1", parameters)
        regions = rows(connection,
            "SELECT coalesce(o.customer_state, '未知地区') AS state, "
            "CAST(sum(o.product_amount) AS DECIMAL(18,2)) AS product_amount, count(*) AS order_count "
            "FROM dwd_orders o" + where + " GROUP BY 1 ORDER BY product_amount DESC NULLS LAST, state", parameters)
        categories = rows(connection,
            "SELECT coalesce(i.product_category_name, '未知品类') AS category, "
            "CAST(sum(i.price) AS DECIMAL(18,2)) AS product_amount, count(DISTINCT i.order_id) AS order_count "
            "FROM dwd_order_items i JOIN dwd_orders o USING(order_id)" + where +
            " GROUP BY 1 ORDER BY product_amount DESC NULLS LAST, category", parameters)
        coverage = rows(connection,
            "SELECT count(*) FILTER (WHERE item_count=0) AS missing_item_orders, "
            "count(*) FILTER (WHERE customer_unique_id IS NULL) AS missing_customer_orders "
            "FROM dwd_orders o" + where, parameters)[0]
    finally:
        connection.close()
    return {
        "dataset": snapshot["manifest"].get("dataset", dict(OLIST_DATASET)),
        "comparison": comparison,
        "available_months": months,
        "run_id": snapshot["run_id"], "built_at": snapshot["manifest"]["finished_at"],
        "input_fingerprint": snapshot["summary"]["input_fingerprint"],
        "filters": {"start": start, "end": end, "state": state},
        "date_bounds": {"min": bounds[0].isoformat() if bounds[0] else None,
                        "max": bounds[1].isoformat() if bounds[1] else None},
        "states": states, "metrics": metrics, "monthly": monthly, "regions": regions,
        "categories": categories, "coverage": coverage,
        "quality": snapshot["quality"],
        "reconciliation": snapshot["summary"]["reconciliation"],
        "reconciliation_samples": snapshot["summary"]["reconciliation_samples"],
        "table_counts": snapshot["summary"]["table_counts"],
        "inputs": snapshot["manifest"]["inputs"],
    }
