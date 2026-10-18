import csv
import io
from datetime import date, datetime
from decimal import Decimal

import pytest

from zhishu_inspection.csv_import import COLUMNS, parse_csv
from zhishu_inspection.source_types import TableData
from zhishu_inspection.tabular_mapping import map_order_table, preview_table, suggest_mapping


ALIASES = ('order_id', 'order_date', 'province', 'buyer_id', 'category', 'amount', 'freight', 'payment', 'status')


def order_table(**overrides):
    record = dict(zip(ALIASES, ('00012', date(2026, 1, 1), '广东省', '00002', '食品饮料', Decimal('100.00'), Decimal('5.00'), '105.00', 'delivered')))
    record.update(overrides)
    return TableData('orders', ALIASES, [tuple(record.values())], {'format': 'test'})


def test_mapping_keeps_identifiers_exact_money_and_formats_dates():
    content = map_order_table(order_table(), dict(zip(COLUMNS, ALIASES)))
    rows = list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))
    assert rows[1] == ['00012', '2026-01-01', '广东省', '00002', '食品饮料', '100.00', '5.00', '105.00', '已完成']
    assert parse_csv(content)[0]['订单号'] == '00012'


@pytest.mark.parametrize('value', [datetime(2026, 2, 3, 9, 10), '2026-02-03'])
def test_mapping_accepts_dates_and_english_statuses(value):
    result = parse_csv(map_order_table(order_table(order_date=value, status='canceled'), dict(zip(COLUMNS, ALIASES))))
    assert result[0]['下单日期'] == '2026-02-03'
    assert result[0]['订单状态'] == '已取消'


@pytest.mark.parametrize('mapping', [{}, {**dict(zip(COLUMNS, ALIASES)), '订单号': 'missing'}, {**dict(zip(COLUMNS, ALIASES)), 'extra': 'order_id'}, {**dict(zip(COLUMNS, ALIASES)), '买家编号': 'order_id'}])
def test_mapping_requires_all_roles_and_exact_unambiguous_columns(mapping):
    with pytest.raises(ValueError):
        map_order_table(order_table(), mapping)


@pytest.mark.parametrize('changes', [{'province': 'GD'}, {'amount': '1.001'}, {'amount': None}, {'status': 'unknown'}])
def test_mapping_uses_canonical_business_validation(changes):
    with pytest.raises(ValueError):
        map_order_table(order_table(**changes), dict(zip(COLUMNS, ALIASES)))


def test_mapping_rejects_duplicate_order_grain():
    table = order_table()
    table.rows *= 2
    with pytest.raises(ValueError, match='重复'):
        map_order_table(table, dict(zip(COLUMNS, ALIASES)))


def test_suggestions_are_conservative_and_resolve_no_ambiguous_alias():
    assert suggest_mapping(ALIASES) == dict(zip(COLUMNS, ALIASES))
    assert suggest_mapping(['order_id', '订单号', 'province', 'address']) == {'省份': 'province'}
    assert suggest_mapping(['my_order_id', 'order-id']) == {}


def test_preview_bounds_samples_and_converts_decimal_and_dates():
    table = order_table()
    table.rows *= 10
    preview = preview_table(table)
    assert preview['row_count'] == 10
    assert preview['columns'] == list(ALIASES)
    assert len(preview['samples']) == 5
    assert preview['samples'][0]['amount'] == '100.00'
    assert preview['samples'][0]['order_date'] == '2026-01-01'


def test_empty_order_table_requires_explicit_refresh_mode():
    table = order_table()
    table.rows = []
    mapping = dict(zip(COLUMNS, ALIASES))
    with pytest.raises(ValueError):
        map_order_table(table, mapping)
    assert list(csv.reader(io.StringIO(map_order_table(table, mapping, allow_empty=True).decode('utf-8-sig')))) == [list(COLUMNS)]
    with pytest.raises(ValueError):
        map_order_table(table, {}, allow_empty=True)
