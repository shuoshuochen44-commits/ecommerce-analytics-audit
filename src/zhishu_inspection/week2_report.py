import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .database import build_database


METRIC_FILES = {
    "completed_product_amount": "completed_product_amount.sql",
    "completed_order_count": "completed_order_count.sql",
    "completed_average_order_value": "completed_average_order_value.sql",
    "completed_unique_customer_count": "completed_unique_customer_count.sql",
}

METRIC_LABELS = {
    "completed_product_amount": "完成订单商品金额",
    "completed_order_count": "完成订单数",
    "completed_average_order_value": "完成订单商品金额客单价",
    "completed_unique_customer_count": "完成订单唯一购买客户数",
}


def _json_value(value: Any) -> Any:
    return format(value, "f") if isinstance(value, Decimal) else value


def build_week2_evidence(
    raw_dir: Path, database_path: Path, output_dir: Path
) -> dict[str, Any]:
    counts = build_database(raw_dir, database_path)
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        metrics = {}
        for name, filename in METRIC_FILES.items():
            sql = Path("sql/metrics", filename).read_text(encoding="utf-8")
            metrics[name] = _json_value(connection.execute(sql).fetchone()[0])
        reconciliation_sql = Path(
            "sql/quality/payment_reconciliation.sql"
        ).read_text(encoding="utf-8")
        reconciliation = dict(
            connection.execute(
                "SELECT reconciliation_status, count(*) FROM ("
                + reconciliation_sql.rstrip().rstrip(";")
                + ") GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )
    finally:
        connection.close()

    result = {
        "table_counts": counts,
        "metrics": metrics,
        "reconciliation": reconciliation,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metric_lines = [
        f"| {METRIC_LABELS[name]} | `{name}` | {value} |"
        for name, value in metrics.items()
    ]
    reconciliation_lines = [
        f"| {status} | {count} |" for status, count in reconciliation.items()
    ]
    table_lines = [f"| {table} | {count} |" for table, count in counts.items()]
    markdown = "\n".join(
        [
            "# 第二周数据库与指标结果",
            "",
            "## 数据库表",
            "",
            "| 表 | 行数 |",
            "|---|---:|",
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
