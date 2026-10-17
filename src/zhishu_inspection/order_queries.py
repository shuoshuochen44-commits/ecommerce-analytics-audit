"""Fixed order-level search and formula-safe CSV exports."""

import csv
import io

import duckdb

from .analytics import rows, validate_dates
from .pipeline import load_snapshot

STATUS_NAMES = {"delivered": "已完成", "shipped": "已发货", "processing": "处理中", "canceled": "已取消",
                "created": "已创建", "approved": "已确认", "invoiced": "已开票", "unavailable": "不可用"}
RECON_NAMES = {"matched": "金额一致", "mismatch": "待核对", "missing_items": "缺商品", "missing_payment": "缺支付", "missing_both": "缺商品与支付"}


def order_data(output_root, start=None, end=None, state=None, search="", status="", page=1, run_id=None, export=False):
    validate_dates(start, end)
    try:
        page = int(page)
    except (ValueError, TypeError):
        raise ValueError("页码必须是正整数") from None
    if page < 1 or page > 100000 or status not in ("", *STATUS_NAMES) or not isinstance(search, str) or len(search) > 80:
        raise ValueError("查询条件无效，请检查页码、状态或关键词长度")
    snapshot = load_snapshot(output_root, run_id)
    con = duckdb.connect(str(snapshot["directory"] / "data.duckdb"), read_only=True)
    try:
        conditions, params = ["TRUE"], []
        for value, condition in ((start, "purchase_date>=CAST(? AS DATE)"), (end, "purchase_date<=CAST(? AS DATE)"),
                                 (status, "order_status=?")):
            if value:
                conditions.append(condition)
                params.append(value)
        if state == "__unknown__":
            conditions.append("customer_state IS NULL")
        elif state:
            conditions.append("customer_state=?")
            params.append(state)
        if search.strip():
            conditions.append("(contains(order_id, ?) OR contains(coalesce(customer_unique_id,''), ?))")
            params.extend((search.strip(), search.strip()))
        where = " WHERE " + " AND ".join(conditions)
        total = con.execute("SELECT count(*) FROM dwd_orders" + where, params).fetchone()[0]
        if export and total > 20000:
            raise ValueError("结果超过 20,000 笔，请先缩小月份、地区或关键词范围再导出")
        records = rows(con, "SELECT order_id, customer_unique_id, strftime(purchase_date, '%Y-%m-%d') AS purchase_date, customer_state, order_status, "
                       "product_amount, freight_amount, payment_amount, reconciliation_status FROM dwd_orders" +
                       where + " ORDER BY purchase_date DESC, order_id LIMIT ? OFFSET ?",
                       params + [20000 if export else 20, 0 if export else (page-1)*20])
    finally:
        con.close()
    return {"run_id": snapshot["run_id"], "total": total, "page": page, "page_size": 20, "orders": records}


def export_orders(output_root, **filters):
    data = order_data(output_root, **filters, export=True)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(("订单号", "买家编号", "下单日期", "地区", "订单状态", "商品金额", "运费", "支付金额", "核对状态"))
    for row in data["orders"]:
        row["order_status"] = STATUS_NAMES.get(row["order_status"], row["order_status"])
        row["reconciliation_status"] = RECON_NAMES.get(row["reconciliation_status"], row["reconciliation_status"])
        values = []
        for value in row.values():
            text = "" if value is None else str(value)
            values.append("'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text)
        writer.writerow(values)
    return stream.getvalue().encode("utf-8-sig")
