"""Explicit, auditable conversion from source columns to the order CSV contract."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from .csv_import import COLUMNS, STATUSES, parse_csv


_ALIASES = {
    '订单号': ('订单号', 'order_id', 'order_number'),
    '下单日期': ('下单日期', 'order_date', 'purchase_date', 'order_purchase_timestamp'),
    '省份': ('省份', 'province', 'customer_state'),
    '买家编号': ('买家编号', 'buyer_id', 'customer_unique_id'),
    '商品分类': ('商品分类', 'category', 'product_category_name'),
    '商品金额': ('商品金额', 'amount', 'goods_amount', 'price'),
    '运费': ('运费', 'freight', 'freight_value', 'shipping_fee'),
    '支付金额': ('支付金额', 'payment', 'payment_value', 'paid_amount'),
    '订单状态': ('订单状态', 'status', 'order_status'),
}


def suggest_mapping(columns):
    """Suggest exact known aliases only; callers must request explicit confirmation."""
    result = {}
    for target, aliases in _ALIASES.items():
        matches = [column for column in columns if column.casefold() in aliases]
        if len(matches) == 1:
            result[target] = matches[0]
    return result


def _text(value):
    if value is None:
        return ''
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    raise ValueError('单元格不是可映射的文本或数字，请先整理为平面表格')


def preview_table(table):
    """Return at most five source rows, with JSON-safe exact scalar text."""
    return {'name': table.name, 'columns': list(table.columns), 'row_count': len(table.rows),
            'samples': [dict(zip(table.columns, (_text(value)[:500] for value in row)))
                        for row in table.rows[:5]], 'origin': table.origin}


def map_order_table(table, mapping, *, allow_empty=False):
    """Return UTF-8 BOM CSV only after canonical order validation succeeds."""
    if not isinstance(mapping, dict) or set(mapping) != set(COLUMNS):
        raise ValueError('请明确映射全部九个订单字段，不能遗漏或增加字段')
    if any(not isinstance(value, str) or value not in table.columns for value in mapping.values()):
        raise ValueError('映射必须精确指向现有源表列名')
    if len(set(mapping.values())) != len(COLUMNS):
        raise ValueError('每个订单字段必须映射到独立的源表列')
    positions = [table.columns.index(mapping[column]) for column in COLUMNS]
    target = io.StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(COLUMNS)
    statuses = {english: chinese for chinese, english in STATUSES.items()}
    for row in table.rows:
        values = []
        for column, index in zip(COLUMNS, positions):
            value = row[index]
            if column == '下单日期' and isinstance(value, (datetime, date)):
                value = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
            text = _text(value)
            if column == '订单状态':
                text = statuses.get(text, text)
            values.append(text)
        writer.writerow(values)
    content = target.getvalue().encode('utf-8-sig')
    parse_csv(content, allow_empty=allow_empty)
    return content
