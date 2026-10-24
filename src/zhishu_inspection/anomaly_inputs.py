"""Bounded, keyset-paginated order input for the full anomaly ruleset."""

from datetime import date

from .anomaly_models import AnomalyConfig
from .query_gateway import execute_readonly


MAX_ORDER_INPUTS = 20000


def read_scoped_orders(database, config: AnomalyConfig, start=None, end=None,
                       state=None, category=None) -> list[dict]:
    conditions, parameters = ["o.order_status='delivered'"], []
    if start:
        lower = date.fromordinal(max(1, date.fromisoformat(start).toordinal() - config.window_days))
        conditions.append('o.purchase_date>=CAST(? AS DATE)')
        parameters.append(lower.isoformat())
    if end:
        conditions.append('o.purchase_date<=CAST(? AS DATE)')
        parameters.append(end)
    if state == '__unknown__':
        conditions.append('o.customer_state IS NULL')
    elif state is not None:
        conditions.append('o.customer_state=?')
        parameters.append(state)
    source, amount, grouping = 'dwd_orders o', 'o.product_amount', ''
    if category is not None:
        source += ' JOIN dwd_order_items i ON o.order_id=i.order_id'
        conditions.append("coalesce(i.product_category_name, '未知品类')=?")
        parameters.append(category)
        amount, grouping = 'CAST(sum(i.price) AS DECIMAL(18,2))', ' GROUP BY 1,2'
    records, cursor = [], None
    while True:
        scoped, bound = list(conditions), list(parameters)
        if cursor:
            scoped.append('(o.purchase_date>CAST(? AS DATE) OR (o.purchase_date=CAST(? AS DATE) AND o.order_id>?))')
            bound.extend([cursor['day'], cursor['day'], cursor['order_id']])
        page = execute_readonly(database,
            f"SELECT o.order_id, o.purchase_date AS day, {amount} AS amount FROM {source} "
            + ' WHERE ' + ' AND '.join(scoped) + grouping + ' ORDER BY 2,1 LIMIT 10000', bound, max_rows=10000)
        for row in page:
            row['day'] = row['day'].isoformat()
        records.extend(page)
        if len(records) > MAX_ORDER_INPUTS:
            raise ValueError('单笔金额检测输入超过 20,000 条，请缩小日期范围，未返回截断后的结论')
        if len(page) < 10000:
            return records
        cursor = page[-1]
