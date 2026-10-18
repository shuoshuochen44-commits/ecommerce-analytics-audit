import importlib.util
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

import pytest

from zhishu_inspection.china_demo import CATEGORIES, PROVINCES
from zhishu_inspection.csv_import import COLUMNS, parse_csv
from zhishu_inspection.file_sources import read_file_tables
from zhishu_inspection.tabular_mapping import map_order_table, suggest_mapping


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/export_import_samples.py'
spec = importlib.util.spec_from_file_location('export_import_samples', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
export_samples = module.export_samples


def records_for(path):
    table, = read_file_tables(path)
    assert table.columns == COLUMNS
    assert suggest_mapping(table.columns) == dict(zip(COLUMNS, COLUMNS))
    assert path.stat().st_size < 20 * 1024 * 1024
    return parse_csv(map_order_table(table, suggest_mapping(table.columns)))


def summary(records):
    return {
        'count': len(records),
        'statuses': Counter(row['订单状态'] for row in records),
        'provinces': Counter(row['省份'] for row in records),
        'completed_amount': sum((Decimal(row['商品金额']) for row in records if row['订单状态'] == '已完成'), Decimal(0)),
        'freight': sum((Decimal(row['运费']) for row in records), Decimal(0)),
        'payment': sum((Decimal(row['支付金额']) for row in records), Decimal(0)),
    }


def test_five_formats_export_identical_canonical_orders_and_aggregates(tmp_path):
    result = export_samples(tmp_path / 'samples', order_count=62)
    assert result['order_count'] == 62
    assert result['currency'] == 'CNY'
    assert result['date_min'] == '2026-01-01'
    assert result['date_max'] == '2026-09-30'
    assert set(result['files']) == {'csv', 'xlsx', 'json', 'parquet', 'sqlite'}
    expected = records_for(Path(result['files']['csv']))
    for kind, value in result['files'].items():
        path = Path(value)
        assert path.is_absolute()
        assert path.name == '订单数据.' + kind
        actual = records_for(path)
        assert actual == expected
        assert summary(actual) == summary(expected)
    assert len({row['订单号'] for row in expected}) == 62
    assert len({row['买家编号'] for row in expected}) < 62
    assert {row['省份'] for row in expected} == set(PROVINCES)
    assert {row['商品分类'] for row in expected} == set(CATEGORIES)
    assert {row['下单日期'][:7] for row in expected} == {f'2026-{month:02d}' for month in range(1, 10)}
    assert {row['订单状态'] for row in expected} == {'已完成', '已发货', '已取消'}
    assert sum(row['订单状态'] == '已完成' for row in expected) > 62 * 0.8
    assert all(Decimal(row['商品金额']) + Decimal(row['运费']) == Decimal(row['支付金额']) for row in expected)
    assert Path(result['files']['csv']).read_bytes().startswith(b'\xef\xbb\xbf')
    json_rows = json.loads(Path(result['files']['json']).read_text(encoding='utf-8'))
    assert all(isinstance(row[column], str) for row in json_rows for column in ('商品金额', '运费', '支付金额'))


def test_sample_generation_is_deterministic_and_preserves_buyer_province(tmp_path):
    first = export_samples(tmp_path / 'first', order_count=62)
    second = export_samples(tmp_path / 'second', order_count=62)
    assert Path(first['files']['csv']).read_bytes() == Path(second['files']['csv']).read_bytes()
    records = records_for(Path(first['files']['csv']))
    buyer_provinces = {}
    for row in records:
        assert buyer_provinces.setdefault(row['买家编号'], row['省份']) == row['省份']


def test_staging_directory_uses_ordinary_inherited_permissions_and_is_removed(tmp_path, monkeypatch):
    observed_modes = []
    original_mkdir = module.os.mkdir
    def observe_mkdir(path, mode=0o777, *args, **kwargs):
        if Path(path).name.startswith('.order-export-'):
            observed_modes.append(mode)
        return original_mkdir(path, mode, *args, **kwargs)
    monkeypatch.setattr(module.os, 'mkdir', observe_mkdir)
    result = export_samples(tmp_path, order_count=62)
    # Windows maps mkdir(mode=0700) to a protected owner-only ACL. Ordinary
    # mkdir inherits the delivery directory ACL; no machine-specific SID needed.
    assert observed_modes == [0o777]
    assert set(tmp_path.iterdir()) == {Path(path) for path in result['files'].values()}


def test_export_failure_removes_only_known_staged_files(tmp_path, monkeypatch):
    def fail_after_two_files(paths, rows):
        paths['csv'].write_text('partial', encoding='utf-8')
        paths['json'].write_text('partial', encoding='utf-8')
        raise OSError('test export interruption')
    monkeypatch.setattr(module, '_write_files', fail_after_two_files)
    with pytest.raises(OSError, match='test export interruption'):
        export_samples(tmp_path, order_count=62)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('kind', ['csv', 'xlsx', 'json', 'parquet', 'sqlite'])
def test_existing_target_is_refused_before_any_export(tmp_path, kind):
    path = tmp_path / ('订单数据.' + kind)
    path.write_bytes(b'keep existing data')
    with pytest.raises(FileExistsError):
        export_samples(tmp_path, order_count=62)
    assert path.read_bytes() == b'keep existing data'
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('count', [0, 30, 20001, True, 62.5])
def test_invalid_order_count_creates_no_output(tmp_path, count):
    destination = tmp_path / 'samples'
    with pytest.raises(ValueError):
        export_samples(destination, order_count=count)
    assert not destination.exists()


def test_cli_returns_short_json_and_default_is_12000(tmp_path):
    result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(tmp_path / 'samples')],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    metadata = json.loads(result.stdout)
    assert metadata['order_count'] == 12000
    assert len(parse_csv(Path(metadata['files']['csv']).read_bytes())) == 12000
    assert result.stderr == ''
    assert len(result.stdout) < 2000
