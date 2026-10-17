"""Independent order-grain computation from raw text tables, without model SQL."""

from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

import duckdb

from .quality import evaluate_quality


def money(value):
    return format(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f') if value is not None else None


def raw_orders(snapshot, *, max_rows=1000000):
    connection = duckdb.connect(str(snapshot['directory']/'data.duckdb'), read_only=True)
    remaining = max_rows
    def read(sql):
        nonlocal remaining
        records = connection.execute(sql).fetchmany(remaining + 1)
        remaining -= len(records)
        if remaining < 0:
            raise ValueError('原始层核验超过行数预算')
        return records
    try:
        customers = {cid: (uid.strip() if uid and uid.strip() else None, state)
                     for cid, uid, state in read('SELECT customer_id, customer_unique_id, customer_state FROM raw_customers')}
        products = {pid: cat.strip() if cat and cat.strip() else None
                    for pid, cat in read('SELECT product_id, product_category_name FROM raw_products')}
        items = defaultdict(list)
        for oid, pid, price, freight in read('SELECT order_id, product_id, price, freight_value FROM raw_order_items'):
            items[oid].append({'product':pid, 'category':products.get(pid), 'price':Decimal(price), 'freight':Decimal(freight)})
        payments = defaultdict(list)
        for oid, value in read('SELECT order_id, payment_value FROM raw_payments'):
            payments[oid].append(Decimal(value))
        orders = []
        # Only primitive date parsing is shared with the storage engine; business
        # grouping, sums, distinct counts and reconciliation are independent Python.
        for oid, cid, status, purchased in read('SELECT order_id, customer_id, order_status, CAST(order_purchase_timestamp AS DATE) FROM raw_orders'):
            uid, state = customers.get(cid, (None,None))
            rows, paid = items[oid], payments[oid]
            amount = sum((i['price'] for i in rows), Decimal(0)) if rows else None
            freight = sum((i['freight'] for i in rows), Decimal(0)) if rows else None
            reconciliation = ('missing_both' if not rows and not paid else 'missing_items' if not rows else
                              'missing_payment' if not paid else 'matched' if abs(sum(paid)-amount-freight)<=Decimal('.01') else 'mismatch')
            orders.append({'id':oid, 'uid':uid, 'state':state, 'status':status,
                           'date':str(purchased)[:10], 'items':rows, 'amount':amount,
                           'paid':paid, 'reconciliation':reconciliation})
        return orders
    finally:
        connection.close()


def metric_value(orders, metric):
    amounts = [o['amount'] for o in orders if o['amount'] is not None]
    amount = sum(amounts, Decimal(0)) if amounts else None
    buyers = Counter(o['uid'] for o in orders if o['uid'] is not None)
    if metric == 'amount': return money(amount)
    if metric == 'orders': return len(orders)
    if metric == 'aov': return money(amount/len(orders)) if amount is not None and orders else None
    if metric == 'customers': return len(buyers)
    if metric == 'repeat_buyers': return sum(n>=2 for n in buyers.values())
    if metric == 'repeat_rate': return money(Decimal(sum(n>=2 for n in buyers.values()))*100/len(buyers)) if buyers else None
    if metric == 'canceled': return sum(o['status']=='canceled' for o in orders)
    if metric == 'missing_items': return sum(not o['items'] for o in orders)
    if metric == 'missing_payments': return sum(not o['paid'] for o in orders)
    raise ValueError('不支持的独立核验指标')


def expected_result(snapshot, question, start=None, end=None, state=None):
    if question.metric == 'failed_rules':
        with duckdb.connect(str(snapshot['directory']/'data.duckdb'), read_only=True) as con:
            return [{'value':sum(r['failed_count']>0 for r in evaluate_quality(con))}]
    orders = raw_orders(snapshot)
    all_status = question.kind == 'quality' or question.dimension == 'status' or question.metric == 'canceled'
    orders = [o for o in orders if (all_status or o['status']=='delivered')
              and (not start or o['date']>=start) and (not end or o['date']<=end)
              and (state is None or (o['state'] is None if state=='__unknown__' else o['state']==state))]
    dimension = question.dimension
    if not dimension:
        return [{'value':metric_value(orders, question.metric)}]
    groups = defaultdict(list)
    if dimension in ('category','product'):
        for o in orders:
            for item in o['items']:
                groups[item[dimension] or ('未知品类' if dimension=='category' else '未知商品')].append((o['id'], item['price']))
        result = [{'dimension':label, 'value':money(sum((p for _,p in rows),Decimal(0))) if question.metric=='amount' else len({oid for oid,_ in rows})}
                  for label, rows in groups.items()]
    else:
        for o in orders:
            label = {'month':o['date'][:7], 'region':o['state'] or '未知地区',
                     'status':o['status'], 'reconciliation':o['reconciliation']}[dimension]
            groups[label].append(o)
        key = 'month' if dimension=='month' else 'dimension'
        result = [{key:label, 'value':metric_value(rows,question.metric)} for label, rows in groups.items()]
    if dimension == 'month':
        return sorted(result, key=lambda r:r['month'])
    return sorted(result, key=lambda r:(r['value'] is None, -Decimal(r['value']) if r['value'] is not None else Decimal(0), r['dimension']))[:10]
