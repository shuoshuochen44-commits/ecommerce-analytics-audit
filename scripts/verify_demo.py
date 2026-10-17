"""Rebuild twice and produce independent real-data acceptance evidence."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

import duckdb

from zhishu_inspection.analytics import dashboard_data
from zhishu_inspection.pipeline import load_snapshot, run_pipeline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("delivery_dir", type=Path)
    args = parser.parse_args()
    first = run_pipeline(args.raw_dir, args.output_root)
    second = run_pipeline(args.raw_dir, args.output_root)
    assert first["metrics"] == second["metrics"]
    assert first["table_counts"] == second["table_counts"]
    assert first["input_fingerprint"] == second["input_fingerprint"]
    clean_rules = lambda result: [{k: v for k, v in row.items() if k != "run_id"} for row in result["quality"]]
    assert clean_rules(first) == clean_rules(second)
    assert first["reconciliation"] == second["reconciliation"]
    data = dashboard_data(args.output_root)
    amount = Decimal(data["metrics"]["completed_product_amount"] or "0")
    for groups in (data["monthly"], data["regions"], data["categories"]):
        assert sum(Decimal(r["product_amount"] or "0") for r in groups) == amount
    assert sum(r["order_count"] for r in data["monthly"]) == data["metrics"]["completed_order_count"]
    assert sum(r["order_count"] for r in data["regions"]) == data["metrics"]["completed_order_count"]
    snapshot = load_snapshot(args.output_root)
    con = duckdb.connect(str(snapshot["directory"] / "data.duckdb"), read_only=True)
    try:
        raw_filtered = con.execute(
            "SELECT CAST(sum(CAST(i.price AS DECIMAL(18,2))) AS DECIMAL(18,2)) "
            "FROM raw_order_items i JOIN raw_orders o USING(order_id) JOIN raw_customers c USING(customer_id) "
            "WHERE o.order_status='delivered' AND c.customer_state='SP' "
            "AND CAST(o.order_purchase_timestamp AS DATE) BETWEEN DATE '2018-01-01' AND DATE '2018-01-31'"
        ).fetchone()[0]
        filtered = dashboard_data(args.output_root, start="2018-01-01", end="2018-01-31", state="SP")
        assert Decimal(filtered["metrics"]["completed_product_amount"] or "0") == (raw_filtered or Decimal(0))
        naive = con.execute(
            "SELECT CAST(sum(CAST(i.price AS DECIMAL(18,2))) AS DECIMAL(18,2)) "
            "FROM raw_order_items i JOIN raw_orders o USING(order_id) "
            "JOIN raw_payments p USING(order_id) WHERE o.order_status='delivered'"
        ).fetchone()[0]
        missing_items = con.execute("SELECT coalesce(order_status,'未知'), count(*) FROM dwd_orders WHERE item_count=0 GROUP BY 1 ORDER BY 2 DESC").fetchall()
    finally:
        con.close()
    peak = max(data["monthly"], key=lambda row: Decimal(row["product_amount"] or "0"), default=None)
    evidence = {"runs": [first["run_id"], second["run_id"]], "repeat_semantics_equal": True,
                "input_fingerprint": second["input_fingerprint"], "metrics": second["metrics"],
                "grouped_amounts_reconcile": True, "filtered_raw_sql_matches": True,
                "SP_2018_01": filtered["metrics"], "naive_join_amount": str(naive),
                "quality": [{k: row[k] for k in ("rule_id", "label", "failed_count")} for row in second["quality"]],
                "reconciliation": second["reconciliation"], "top_month": peak}
    args.delivery_dir.mkdir(parents=True, exist_ok=True)
    (args.delivery_dir / "验收证据.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    region = data["regions"][0] if data["regions"] else None
    categories = data["categories"][:5]
    lines = ["# 经营分析简报", "", f"核对批次：`{second['run_id']}`", "",
             "## 数据与口径", "", "Olist 巴西电商历史快照。金额单位 BRL，只含已交付订单商品价格，不含运费，按购买日期归属。",
             f"源订单覆盖 {data['date_bounds']['min']} 至 {data['date_bounds']['max']}。", "",
             "## 可核对的发现", "",
             f"- 完成订单商品金额为 {amount:,.2f}，完成订单 {data['metrics']['completed_order_count']:,} 笔。",
             f"- 商品金额客单价 {data['metrics']['completed_average_order_value']}，唯一购买客户 {data['metrics']['completed_unique_customer_count']:,}。"]
    if region and amount:
        share = Decimal(region["product_amount"]) / amount * 100
        lines.append(f"- {region['state']} 州商品金额 {Decimal(region['product_amount']):,.2f}，占整体 {share:.1f}%。这是地域集中度描述，不能据此判断该州客户价值或投放效果。")
    if peak:
        lines.append(f"- 按最终已交付状态回看的最高商品金额月份为 {peak['month']}，金额 {Decimal(peak['product_amount']):,.2f}。这不构成活动促销或其他因素的因果证据。")
    lines += ["", "金额最高的五个源品类：", "", "| 品类 | 商品金额 |", "|---|---:|"]
    for row in categories:
        lines.append(f"| {row['category']} | {Decimal(row['product_amount']):,.2f} |")
    lines += ["", "## 数据问题如何影响结论", "",
              f"- 直接把订单商品与支付明细关联后求商品金额，会得到 {Decimal(naive or 0):,.2f}；正确基线为 {amount:,.2f}。该差异来自关联粒度与匹配范围，不代表新增销售。",
              "- 系统先分别聚合到订单粒度，再关联；金额在原始层和明细层独立计算后逐项核对。",
              f"- 支付对账结果：{json.dumps(second['reconciliation'], ensure_ascii=False)}。差异仅标记待核查，不能直接解释为损失。",
              "- 缺商品明细订单状态分布：" + "、".join(f"{state} {count} 笔" for state, count in missing_items) + "。",
              "", "## 限制与后续核查", "",
              "边界月份可能不完整；按最终订单状态回看会影响近期月份。月份和地区的客户数不能简单相加，跨品类订单数也不具可加性。",
              "可继续核查对账差异、缺明细订单和缺交付日期；评价、营销、成本与退款明细尚未接入，因此不计算转化率、ROI、利润或退款损失。",
              "", "## 复现", "", "在项目目录执行：", "",
              "```powershell", ".\\.venv\\Scripts\\python.exe scripts/verify_demo.py data/raw/olist artifacts/analytics outputs", "```", "",
              "此命令重建两次、核对分组金额和筛选结果，并更新本简报及验收证据。"]
    (args.delivery_dir / "经营分析简报.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    (args.delivery_dir / "数据质量与运行报告.md").write_text((snapshot["directory"] / "report.md").read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
