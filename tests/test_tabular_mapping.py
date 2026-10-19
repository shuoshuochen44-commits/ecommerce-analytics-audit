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


def test_full_table_validation_collects_bounded_safe_diagnostics_in_original_order():
    from zhishu_inspection.tabular_mapping import validate_order_table
    table = order_table()
    table.rows = [tuple(['secret-z', 'bad-date', 'GD', 'secret-buyer', '食品饮料', '-2', '0', '1.001', 'unknown'])] * 30
    result = validate_order_table(table, dict(zip(COLUMNS, ALIASES)))
    assert result['valid'] is False
    assert result['error_count'] == 30 * 5 + 29
    assert len(result['issues']) == 50 and result['truncated'] is True
    assert result['issues'][0] == {'row_number': 2, 'source_column': 'order_date', 'target_field': '下单日期', 'reason': '日期格式错误', 'suggestion': '请填写 YYYY-MM-DD，例如 2026-01-01'}
    assert 'secret-' not in str(result)
    assert all(set(issue) == {'row_number','source_column','target_field','reason','suggestion'} for issue in result['issues'])
    assert result['issues'][5]['row_number'] == 3


def test_validation_matches_canonical_constraints_and_reports_dates():
    from zhishu_inspection.tabular_mapping import validate_order_table, MappingValidationError
    mapping = dict(zip(COLUMNS, ALIASES))
    good = validate_order_table(order_table(), mapping)
    assert good['valid'] and good['row_count'] == 1
    assert good['date_min'] == good['date_max'] == '2026-01-01'
    bad = order_table(buyer_id='bad\nvalue', amount='1000000000', order_date='2026-1-1')
    result = validate_order_table(bad, mapping)
    assert result['error_count'] == 3
    with pytest.raises(MappingValidationError) as error:
        map_order_table(bad, mapping)
    assert error.value.diagnostics == result


def test_validation_rejects_empty_without_explicit_allow_empty():
    from zhishu_inspection.tabular_mapping import validate_order_table
    table = order_table(); table.rows = []
    assert not validate_order_table(table, dict(zip(COLUMNS, ALIASES)))['valid']
    assert validate_order_table(table, dict(zip(COLUMNS, ALIASES)), allow_empty=True)['valid']


def test_validation_counts_other_bad_cells_when_a_cell_has_unsupported_type():
    from zhishu_inspection.tabular_mapping import validate_order_table
    result=validate_order_table(order_table(buyer_id=b'private-id',amount='-2',order_date='bad'),dict(zip(COLUMNS,ALIASES)))
    assert result['row_count']==1
    assert result['error_count']==3
    assert {issue['target_field'] for issue in result['issues']}=={'买家编号','商品金额','下单日期'}
    assert 'private-id' not in str(result)


def test_validation_enforces_canonical_row_limit_even_for_mutated_tables():
    from zhishu_inspection.tabular_mapping import validate_order_table
    table=order_table()
    table.rows=[(str(i),'2026-01-01','广东省','U','食品','1','0','1','已完成') for i in range(20001)]
    result=validate_order_table(table,dict(zip(COLUMNS,ALIASES)))
    assert not result['valid']
    assert result['error_count']==1
    assert result['issues'][0]['reason']=='订单数量超过 20,000 笔'
