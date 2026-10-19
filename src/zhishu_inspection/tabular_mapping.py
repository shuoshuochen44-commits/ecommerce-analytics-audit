"""Explicit, auditable conversion from source columns to the order CSV contract."""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal

from .csv_import import COLUMNS, STATUSES, MAX_BYTES, MAX_ROWS, parse_csv
from .china_demo import PROVINCES


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


class MappingValidationError(ValueError):
    """Safe structured diagnostics, without source cell values."""
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        first = diagnostics['issues'][0]
        location = f"第 {first['row_number']} 行" if first['row_number'] else ''
        super().__init__(location + first['target_field'] + '：' + first['reason'])


def _mapping_positions(table, mapping):
    if not isinstance(mapping, dict) or set(mapping) != set(COLUMNS):
        raise ValueError('请明确映射全部九个订单字段，不能遗漏或增加字段')
    if any(not isinstance(value, str) or value not in table.columns for value in mapping.values()):
        raise ValueError('映射必须精确指向现有源表列名')
    if len(set(mapping.values())) != len(COLUMNS):
        raise ValueError('每个订单字段必须映射到独立的源表列')
    return [table.columns.index(mapping[column]) for column in COLUMNS]


def _mapped_values(row, positions):
    return [_mapped_value(column, row[index]) for column, index in zip(COLUMNS, positions)]


def _mapped_value(column, value):
    if column == '下单日期' and isinstance(value, (datetime, date)):
        value = value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = _text(value)
    if column == '订单状态':
        return {english: chinese for chinese, english in STATUSES.items()}.get(text, text)
    return text


def _serialize_rows(rows):
    target = io.StringIO(newline='')
    writer = csv.writer(target)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return target.getvalue().encode('utf-8-sig')


def validate_order_table(table, mapping, *, allow_empty=False):
    """Check the whole selected table, retaining only 50 safe cell diagnostics."""
    positions = _mapping_positions(table, mapping)
    result = {'valid': True, 'row_count': 0, 'date_min': None, 'date_max': None,
              'error_count': 0, 'truncated': False, 'issues': []}
    def issue(line, field, reason, suggestion):
        result['error_count'] += 1
        if len(result['issues']) < 50:
            result['issues'].append({'row_number': line, 'source_column': mapping.get(field),
                                     'target_field': field, 'reason': reason, 'suggestion': suggestion})
    seen, dates, mapped = set(), [], []
    for ordinal, source_row in enumerate(table.rows, 2):
        line=table.row_numbers[ordinal-2] if table.row_numbers is not None else ordinal
        values, unsupported = [], set()
        for field, index in zip(COLUMNS, positions):
            try:
                values.append(_mapped_value(field, source_row[index]))
            except ValueError:
                values.append('')
                unsupported.add(field)
                issue(line, field, '单元格类型不支持', '请整理为单个文本、日期或数字')
        mapped.append(values)
        if not unsupported and all(not value.strip() for value in values):
            continue
        result['row_count'] += 1
        row = dict(zip(COLUMNS, (value.strip() for value in values)))
        for field, value in row.items():
            if field in unsupported:
                continue
            if not value or len(value) > 80 or any(ord(char) < 32 for char in value):
                issue(line, field, '字段为空、超过 80 字符或含控制字符', '请填写不含换行或控制字符的 1–80 字符内容')
                continue
            if field == '订单号':
                if value in seen:
                    issue(line, field, '订单号重复', '每行应为一笔完整订单，请先合并商品明细')
                seen.add(value)
            elif field == '下单日期':
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError()
                    dates.append(value)
                except ValueError:
                    issue(line, field, '日期格式错误', '请填写 YYYY-MM-DD，例如 2026-01-01')
            elif field == '省份' and value not in PROVINCES:
                issue(line, field, '省份名称不支持', '请填写完整省份名称，例如广东省、北京市')
            elif field == '订单状态' and value not in STATUSES:
                issue(line, field, '订单状态不支持', '请填写已完成、已发货、处理中或已取消')
            elif field in ('商品金额', '运费', '支付金额'):
                if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?', value) or Decimal(value) > Decimal('999999999.99'):
                    issue(line, field, '金额格式或范围错误', '请填写 0–999999999.99 的数字，最多两位小数，不带货币符号')
    if not result['row_count'] and not allow_empty:
        issue(None, '', '文件没有订单', '请填写数据后再导入')
    if result['row_count'] > MAX_ROWS:
        issue(None, '', '订单数量超过 20,000 笔', '请缩小数据范围后导入，未截断分析数据')
    if len(_serialize_rows(mapped)) > MAX_BYTES:
        issue(None, '', '映射后订单 CSV 超过 5 MB', '请缩小数据范围后导入')
    result['valid'] = result['error_count'] == 0
    result['truncated'] = result['error_count'] > len(result['issues'])
    if result['valid'] and dates:
        result['date_min'], result['date_max'] = min(dates), max(dates)
    return result


def map_order_table(table, mapping, *, allow_empty=False):
    """Return UTF-8 BOM CSV only after canonical order validation succeeds."""
    validation = validate_order_table(table, mapping, allow_empty=allow_empty)
    if not validation['valid']:
        raise MappingValidationError(validation)
    positions = _mapping_positions(table, mapping)
    content = _serialize_rows(_mapped_values(row, positions) for row in table.rows)
    parse_csv(content, allow_empty=allow_empty)
    return content
