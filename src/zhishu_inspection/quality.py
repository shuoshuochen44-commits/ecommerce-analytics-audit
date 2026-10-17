"""Deterministic checks on immutable raw input, before any joins."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    rule_id: str
    label: str
    table: str
    keys: str
    predicate: str
    blocking: bool = True
    affected_metrics: str = "金额、订单数、客单价、客户数"


def blank(column):
    return f"({column} IS NULL OR trim({column}) = '')"


def invalid_money(column):
    cents = f"try_cast({column} AS DECIMAL(18,2))"
    valid_decimal = f"regexp_full_match(trim({column}), '[+]?[0-9]+([.][0-9]{{1,2}})?')"
    return f"({cents} IS NULL OR NOT coalesce({valid_decimal}, false))"


RULES = (
    Rule("Q01", "订单主键非空", "raw_orders", "order_id", blank("order_id")),
    Rule("Q02", "订单主键唯一", "raw_orders", "order_id", "order_id IN (SELECT order_id FROM raw_orders GROUP BY 1 HAVING count(*) > 1)"),
    Rule("Q03", "订单商品业务键唯一", "raw_order_items", "order_id, order_item_id", "(order_id, order_item_id) IN (SELECT order_id, order_item_id FROM raw_order_items GROUP BY 1,2 HAVING count(*) > 1)"),
    Rule("Q04", "商品明细关联订单存在", "raw_order_items", "order_id, order_item_id", "NOT EXISTS (SELECT 1 FROM raw_orders o WHERE o.order_id=raw_order_items.order_id)", False),
    Rule("Q05", "商品明细关联商品存在", "raw_order_items", "order_id, product_id", "NOT EXISTS (SELECT 1 FROM raw_products p WHERE p.product_id=raw_order_items.product_id)", False, "品类金额、品类订单数"),
    Rule("Q06", "订单关联客户存在", "raw_orders", "order_id, customer_id", "NOT EXISTS (SELECT 1 FROM raw_customers c WHERE c.customer_id=raw_orders.customer_id)", False, "客户数、地区分析"),
    Rule("Q07", "商品金额非空可解析且非负", "raw_order_items", "order_id, order_item_id", invalid_money("price"), True, "金额、客单价"),
    Rule("Q08", "运费非空可解析且非负", "raw_order_items", "order_id, order_item_id", invalid_money("freight_value"), True, "支付对账"),
    Rule("Q09", "订单状态合法", "raw_orders", "order_id", "order_status IS NULL OR order_status NOT IN ('created','approved','invoiced','processing','shipped','delivered','canceled','unavailable')"),
    Rule("Q10", "购买日期非空且可解析", "raw_orders", "order_id", "try_cast(order_purchase_timestamp AS TIMESTAMP) IS NULL"),
    Rule("Q11", "客户映射键非空且唯一", "raw_customers", "customer_id", blank("customer_id") + " OR customer_id IN (SELECT customer_id FROM raw_customers GROUP BY 1 HAVING count(*)>1)"),
    Rule("Q12", "商品键非空且唯一", "raw_products", "product_id", blank("product_id") + " OR product_id IN (SELECT product_id FROM raw_products GROUP BY 1 HAVING count(*)>1)"),
    Rule("Q13", "商品明细键非空且序号有效", "raw_order_items", "order_id, order_item_id", blank("order_id") + " OR try_cast(order_item_id AS INTEGER) IS NULL OR try_cast(order_item_id AS INTEGER)<=0 OR order_item_id != cast(try_cast(order_item_id AS INTEGER) AS VARCHAR)"),
    Rule("Q14", "支付金额有效", "raw_payments", "order_id, payment_sequential", invalid_money("payment_value"), True, "支付对账"),
    Rule("Q15", "支付业务键非空且唯一", "raw_payments", "order_id, payment_sequential", blank("order_id") + " OR try_cast(payment_sequential AS INTEGER) IS NULL OR try_cast(payment_sequential AS INTEGER)<=0 OR payment_sequential!=cast(try_cast(payment_sequential AS INTEGER) AS VARCHAR) OR (order_id, payment_sequential) IN (SELECT order_id, payment_sequential FROM raw_payments GROUP BY 1,2 HAVING count(*)>1)", True, "支付对账"),
    Rule("Q16", "稳定客户标识非空", "raw_customers", "customer_id", blank("customer_unique_id"), False, "客户数"),
    Rule("Q17", "已交付日期完整且不早于购买", "raw_orders", "order_id", "order_status='delivered' AND (try_cast(order_delivered_customer_date AS TIMESTAMP) IS NULL OR try_cast(order_delivered_customer_date AS TIMESTAMP)<try_cast(order_purchase_timestamp AS TIMESTAMP))", False, "交付分析"),
    Rule("Q18", "支付关联订单存在", "raw_payments", "order_id, payment_sequential", "NOT EXISTS (SELECT 1 FROM raw_orders o WHERE o.order_id=raw_payments.order_id)", False, "支付对账"),
)


def evaluate_quality(connection):
    results = []
    for rule in RULES:
        failed = f"SELECT {rule.keys} FROM {rule.table} WHERE {rule.predicate}"
        total = connection.execute(f"SELECT count(*) FROM {rule.table}").fetchone()[0]
        count = connection.execute(f"SELECT count(*) FROM ({failed})").fetchone()[0]
        cursor = connection.execute(f"{failed} ORDER BY ALL LIMIT 5")
        names = [col[0] for col in cursor.description]
        samples = [dict(zip(names, row)) for row in cursor.fetchall()]
        results.append({
            "rule_id": rule.rule_id, "version": "1.0", "label": rule.label,
            "table": rule.table, "total_count": total, "failed_count": count,
            "failed_ratio": count / total if total else 0,
            "severity": "error" if rule.blocking else "warning",
            "blocking": rule.blocking, "status": "passed" if count == 0 else "failed",
            "sample_keys": samples, "affected_metrics": rule.affected_metrics,
        })
    return results
