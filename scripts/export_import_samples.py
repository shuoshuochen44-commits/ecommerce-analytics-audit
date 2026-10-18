"""Export deterministic, entirely fabricated CNY orders as external import files."""

import argparse
import csv
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

import duckdb
from openpyxl import Workbook

from zhishu_inspection.china_demo import CATEGORIES, PROVINCES, money
from zhishu_inspection.csv_import import COLUMNS, parse_csv


_FORMATS = ('csv', 'xlsx', 'json', 'parquet', 'sqlite')
_MONEY_COLUMNS = {'商品金额', '运费', '支付金额'}


def _orders(count):
    rows = []
    buyer_count = max(len(PROVINCES), count * 3 // 5)
    for index in range(count):
        buyer = index % buyer_count
        purchased = date(2026, 1, 1) + timedelta(days=index * 272 // (count - 1))
        amount = 990 + index * 7919 % 69901
        freight = (0, 0, 500, 800, 1200)[index % 5]
        status = '已取消' if index % 25 == 24 else '已发货' if index % 17 == 16 else '已完成'
        rows.append((f'DD2026{index + 1:06d}', purchased.isoformat(),
                     PROVINCES[buyer % len(PROVINCES)], f'BUY{buyer + 1:06d}',
                     CATEGORIES[index % len(CATEGORIES)], money(amount), money(freight),
                     money(amount + freight), status))
    return rows


def _write_files(paths, rows):
    with paths['csv'].open('x', encoding='utf-8-sig', newline='') as target:
        writer = csv.writer(target)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    # Validate the actual artifact through the same contract used by import.
    parse_csv(paths['csv'].read_bytes())

    workbook = Workbook(write_only=True)
    workbook.properties.created = datetime(2026, 1, 1)
    workbook.properties.modified = datetime(2026, 1, 1)
    sheet = workbook.create_sheet('orders')
    sheet.append(COLUMNS)
    for row in rows:
        sheet.append(row)
    workbook.save(paths['xlsx'])
    workbook.close()

    with paths['json'].open('x', encoding='utf-8') as target:
        json.dump([dict(zip(COLUMNS, row)) for row in rows], target, ensure_ascii=False,
                  separators=(',', ':'))

    projections = ','.join('CAST("' + column + '" AS DECIMAL(18,2)) AS "' + column + '"'
                           if column in _MONEY_COLUMNS else '"' + column + '"'
                           for column in COLUMNS)
    with duckdb.connect(':memory:', config={'threads': '1', 'memory_limit': '128MB'}) as connection:
        connection.execute('CREATE TABLE orders AS SELECT ' + projections +
                           ' FROM read_csv(?, header=true, all_varchar=true)', [str(paths['csv'])])
        connection.execute('COPY orders TO ? (FORMAT PARQUET)', [str(paths['parquet'])])

    connection = sqlite3.connect(paths['sqlite'])
    try:
        with connection:
            connection.execute('CREATE TABLE orders (' + ','.join('"' + column + '" TEXT' for column in COLUMNS) + ')')
            connection.executemany('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)', rows)
    finally:
        connection.close()


def export_samples(directory: Path, order_count=12000) -> dict:
    """Create five importable copies without replacing existing target files.

    Rows are fabricated for learning and testing. No live business data or
    prebuilt application snapshot is read. Returns paths and lightweight metadata.
    """
    if type(order_count) is not int or not len(PROVINCES) <= order_count <= 20000:
        raise ValueError('订单数量必须为 31 到 20,000 之间的整数')
    directory = Path(directory).resolve()
    paths = {kind: directory / ('订单数据.' + kind) for kind in _FORMATS}
    if any(path.exists() or path.is_symlink() for path in paths.values()):
        raise FileExistsError('目标订单文件已存在，请选择新的导出目录')
    rows = _orders(order_count)
    directory.mkdir(parents=True, exist_ok=True)
    # A normal child directory inherits the delivery directory ACL on Windows.
    # tempfile's owner-only 0700 directory would transfer its protected ACL to
    # the published hard links, making them unreadable by the desktop user.
    staging = directory / ('.order-export-' + uuid.uuid4().hex)
    staging.mkdir()
    staged = {kind: staging / path.name for kind, path in paths.items()}
    published = []
    try:
        _write_files(staged, rows)
        for kind, target in paths.items():
            # Linking on the same filesystem publishes completed files and
            # atomically refuses any target created after the preflight.
            os.link(staged[kind], target)
            published.append(target)
    except Exception:
        for target in published:
            target.unlink()
        raise
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
        staging.rmdir()
    return {'directory': str(directory), 'order_count': order_count, 'currency': 'CNY',
            'date_min': rows[0][1], 'date_max': rows[-1][1],
            'files': {kind: str(path) for kind, path in paths.items()}}


def main():
    parser = argparse.ArgumentParser(description='导出可手动导入的订单文件')
    parser.add_argument('directory', type=Path)
    parser.add_argument('--order-count', type=int, default=12000)
    arguments = parser.parse_args()
    result = export_samples(arguments.directory, order_count=arguments.order_count)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
