import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .database import build_database


from .resources import resource_path
PROJECT_ROOT = resource_path('')

METRICS = {
    "completed_product_amount": {
        "filename": "completed_product_amount.sql",
        "label": "完成订单商品金额",
    },
    "completed_order_count": {
        "filename": "completed_order_count.sql",
        "label": "完成订单数",
    },
    "completed_average_order_value": {
        "filename": "completed_average_order_value.sql",
        "label": "完成订单商品金额客单价",
    },
    "completed_unique_customer_count": {
        "filename": "completed_unique_customer_count.sql",
        "label": "完成订单唯一购买客户数",
    },
}

TABLE_METADATA = {
    "raw_orders": ("一个订单", "order_id"),
    "raw_order_items": ("一个订单中的一条商品明细", "order_id + order_item_id"),
    "raw_customers": ("一个订单客户映射", "customer_id"),
    "raw_products": ("一个商品", "product_id"),
    "raw_payments": ("一个订单的一次支付记录", "order_id + payment_sequential"),
}


def _json_value(value: Any) -> Any:
    return format(value, "f") if isinstance(value, Decimal) else value


def _read_sql(relative_path: str) -> str:
    return (PROJECT_ROOT / "sql" / relative_path).read_text(encoding="utf-8")


def build_week2_evidence(
    raw_dir: Path, database_path: Path, output_dir: Path
) -> dict[str, Any]:
    counts = build_database(raw_dir, database_path)
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        metrics = {}
        for name, definition in METRICS.items():
            sql = _read_sql(f"metrics/{definition['filename']}")
            metrics[name] = _json_value(connection.execute(sql).fetchone()[0])
        reconciliation_sql = _read_sql("quality/payment_reconciliation.sql")
        reconciliation_query = reconciliation_sql.rstrip().rstrip(";")
        reconciliation = dict(
            connection.execute(
                "SELECT reconciliation_status, count(*) FROM ("
                + reconciliation_query
                + ") GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )
        mismatch_sum, mismatch_max = connection.execute(
            "SELECT "
            "CAST(coalesce(sum(abs(difference)), 0) AS DECIMAL(18, 2)), "
            "CAST(coalesce(max(abs(difference)), 0) AS DECIMAL(18, 2)) "
            "FROM ("
            + reconciliation_query
            + ") WHERE reconciliation_status = 'mismatch'"
        ).fetchone()
        missing_items_by_status = dict(
            connection.execute(
                "SELECT coalesce(o.order_status, 'not_in_orders'), count(*) "
                "FROM ("
                + reconciliation_query
                + ") AS r LEFT JOIN raw_orders AS o USING (order_id) "
                "WHERE r.reconciliation_status = 'missing_items' "
                "GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )
        missing_payment_orders = [
            {
                "order_id": order_id,
                "item_and_freight_total": _json_value(total),
            }
            for order_id, total in connection.execute(
                "SELECT order_id, item_and_freight_total FROM ("
                + reconciliation_query
                + ") WHERE reconciliation_status = 'missing_payment' "
                "ORDER BY order_id"
            ).fetchall()
        ]
    finally:
        connection.close()

    reconciliation_details = {
        "mismatch_absolute_difference_sum": _json_value(mismatch_sum),
        "mismatch_max_absolute_difference": _json_value(mismatch_max),
        "missing_items_by_order_status": missing_items_by_status,
        "missing_payment_orders": missing_payment_orders,
    }
    result = {
        "table_counts": counts,
        "metrics": metrics,
        "reconciliation": reconciliation,
        "reconciliation_details": reconciliation_details,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metric_lines = [
        f"| {METRICS[name]['label']} | `{name}` | {value} |"
        for name, value in metrics.items()
    ]
    reconciliation_lines = [
        f"| {status} | {count} |" for status, count in reconciliation.items()
    ]
    table_lines = [
        f"| {table} | {count} | {TABLE_METADATA[table][0]} | "
        f"`{TABLE_METADATA[table][1]}` |"
        for table, count in counts.items()
    ]
    missing_items_lines = [
        f"| {status} | {count} |"
        for status, count in missing_items_by_status.items()
    ] or ["| 无 | 0 |"]
    missing_payment_lines = [
        f"| `{row['order_id']}` | {row['item_and_freight_total']} |"
        for row in missing_payment_orders
    ] or ["| 无 | 0.00 |"]
    markdown = "\n".join(
        [
            "# 第二周数据库与指标结果",
            "",
            "## 数据库表",
            "",
            "| 表 | 行数 | 粒度 | 业务键 |",
            "|---|---:|---|---|",
            *table_lines,
            "",
            "## 四项指标",
            "",
            "| 指标 | 字段名 | 结果 |",
            "|---|---|---:|",
            *metric_lines,
            "",
            "## 支付对账",
            "",
            "| 状态 | 订单数 |",
            "|---|---:|",
            *reconciliation_lines,
            "",
            "### 异常明细",
            "",
            f"- mismatch 绝对差额合计：{reconciliation_details['mismatch_absolute_difference_sum']}",
            f"- mismatch 最大绝对差额：{reconciliation_details['mismatch_max_absolute_difference']}",
            "",
            "缺商品明细订单的状态分布：",
            "",
            "| 订单状态 | 订单数 |",
            "|---|---:|",
            *missing_items_lines,
            "",
            "缺支付订单：",
            "",
            "| 订单号 | 商品与运费合计 |",
            "|---|---:|",
            *missing_payment_lines,
            "",
            "## 口径与限制",
            "",
            "- 商品金额只包含已交付订单的商品 `price`，不含运费。",
            "- 客单价为已交付订单商品金额除以已交付订单去重数。",
            "- 购买客户数使用 `customer_unique_id` 去重。",
            "- 支付对账先把商品加运费和支付分别聚合到订单粒度，容差为 0.01。",
            "- 这些分析指标不等同于企业财务收入或利润。",
            "",
            "## 复现命令",
            "",
            "~~~powershell",
            ".\\.venv\\Scripts\\zhishu-week2.exe data/raw/olist data/zhishu.duckdb artifacts/week-02/real",
            "~~~",
            "",
            "## 第三周入口",
            "",
            "把订单、商品明细、客户映射和支付汇总整理成粒度明确的明细层表。",
            "",
        ]
    )
    (output_dir / "summary.md").write_text(markdown, encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build database and week-two report")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = build_week2_evidence(
        args.raw_dir, args.database_path, args.output_dir
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
