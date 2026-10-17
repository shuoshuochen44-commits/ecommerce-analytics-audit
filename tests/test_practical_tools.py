import csv
import io
from pathlib import Path

import pytest

from zhishu_inspection.analytics import dashboard_data
from zhishu_inspection.pipeline import run_pipeline, load_snapshot


HEADER = '订单号,下单日期,省份,买家编号,商品分类,商品金额,运费,支付金额,订单状态\n'
SAMPLE = HEADER + 'A001,2026-01-01,广东省,U1,食品饮料,100.00,5.00,105.00,已完成\nA002,2026-02-28,广东省,U1,家居日用,150.00,0.00,150.00,已完成\nA003,2026-02-15,浙江省,U2,家居日用,25.00,0.00,25.00,已取消\n'


def test_preview_is_read_only_and_import_is_separate_and_repeatable(tmp_path):
    from zhishu_inspection.csv_import import preview_csv, import_csv
    preview = preview_csv(SAMPLE.encode('utf-8-sig'))
    assert preview['order_count'] == 3
    assert preview['completed_amount'] == '250.00'
    assert list(tmp_path.iterdir()) == []
    root = tmp_path / 'customer'
    first = import_csv(SAMPLE.encode('gb18030'), root)
    data = dashboard_data(root)
    assert data['dataset']['id'] == 'customer_csv'
    assert data['dataset']['currency'] == 'CNY'
    assert data['metrics']['completed_product_amount'] == '250.00'
    assert data['metrics']['completed_unique_customer_count'] == 1
    assert any(r['filename'] == 'source.csv' for r in data['inputs'])
    second = import_csv(SAMPLE.encode('gb18030'), root)
    assert second['run_id'] != first['run_id']
    assert second['metrics'] == first['metrics']
    with pytest.raises(ValueError):
        import_csv(SAMPLE.replace('150.00','-1').encode(), root)
    assert load_snapshot(root)['run_id'] == second['run_id']


@pytest.mark.parametrize('text,match', [
    (SAMPLE.replace('A002','A001'), '重复'),
    (SAMPLE.replace('100.00','0.001'), '商品金额'),
    (SAMPLE.replace('100.00','NaN'), '商品金额'),
    (SAMPLE.replace('2026-01-01','2026/1/1'), '日期'),
    (SAMPLE.replace('广东省','不存在省'), '省份'),
    (SAMPLE.replace('已完成','已退款'), '订单状态'),
    (SAMPLE.replace('订单号,','错误列,'), '表头'),
    (HEADER, '没有'),
])
def test_import_rejects_bad_rows_with_helpful_messages(text, match):
    from zhishu_inspection.csv_import import preview_csv
    with pytest.raises(ValueError, match=match):
        preview_csv(text.encode())


def test_month_comparison_uses_same_region_and_handles_zero_missing_coverage(tmp_path):
    from zhishu_inspection.csv_import import import_csv
    import_csv(SAMPLE.encode(), tmp_path)
    data = dashboard_data(tmp_path, start='2026-02-01',end='2026-02-28',state='广东省')
    comparison = data['comparison']
    assert comparison['available']
    amount = comparison['changes']['completed_product_amount']
    assert amount == {'previous':'100.00','difference':'50.00','percent':'50.00'}
    assert comparison['changes']['completed_unique_customer_count']['percent'] == '0.00'
    assert not dashboard_data(tmp_path)['comparison']['available']
    assert not dashboard_data(tmp_path,start='2026-01-01',end='2026-01-31')['comparison']['available']
    assert not dashboard_data(tmp_path,start='2026-02-01',end='2026-02-15')['comparison']['available']
    zero = dashboard_data(tmp_path,start='2026-02-01',end='2026-02-28',state='浙江省')
    assert zero['comparison']['changes']['completed_product_amount']['percent'] is None


def test_orders_search_status_paging_and_csv_formula_protection(tmp_path):
    from zhishu_inspection.csv_import import import_csv
    from zhishu_inspection.order_queries import order_data, export_orders
    import_csv(SAMPLE.replace('A001','=A001').encode(), tmp_path)
    data = order_data(tmp_path,search='U1',status='delivered',page=1)
    assert data['total'] == 2 and len(data['orders']) == 2
    assert order_data(tmp_path,search="' OR 1=1 --")['total'] == 0
    assert order_data(tmp_path,status='canceled')['orders'][0]['order_id'] == 'A003'
    assert order_data(tmp_path,page=2)['orders'] == []
    content = export_orders(tmp_path,search='=A001').decode('utf-8-sig')
    rows = list(csv.reader(io.StringIO(content)))
    assert rows[1][0] == "'=A001"
    assert '已完成' in rows[1]
    with pytest.raises(ValueError):
        order_data(tmp_path,status='DROP')
    with pytest.raises(ValueError):
        order_data(tmp_path,page=0)
