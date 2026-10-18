"""Bounded local tabular file readers. Never execute workbook code or macros."""

import csv
import io
import json
import re
import sqlite3
import struct
import time
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
import posixpath

import duckdb

from .source_types import MAX_BYTES, MAX_COLUMNS, MAX_ROWS, TableData

MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2000
_WORKBOOKS = {'xlsx', 'xls', 'xlsb', 'ods'}
_FORMATS = _WORKBOOKS | {'csv', 'tsv', 'txt', 'json', 'jsonl', 'ndjson', 'parquet', 'sqlite', 'sqlite3', 'db', 'duckdb'}


class _ReadError(ValueError):
    pass


def _table(name, columns, rows, path, kind):
    if len(rows) > MAX_ROWS:
        raise _ReadError('数据行数超过 20,000；请缩小范围，未截断分析数据')
    try:
        return TableData(name, tuple(columns), rows,
                         {'format': kind, 'file': path.name, 'table': name})
    except ValueError as error:
        raise _ReadError(str(error)) from None


def _row_size(row):
    size = 0
    for value in row:
        if isinstance(value, (dict, list, tuple)):
            raise _ReadError('数据包含嵌套字段，请先展开为平面表格')
        if isinstance(value, bytes):
            size += len(value)
        else:
            value = '' if value is None else str(value)
            if len(value) > MAX_BYTES:
                raise _ReadError('数据展开后大小超过 20 MB，请缩小文件')
            size += len(value.encode('utf-8'))
    return size


def _fetch_rows(cursor):
    if len(cursor.description) > MAX_COLUMNS:
        raise _ReadError('表格列数超过 200，请缩小字段范围')
    rows, size = [], 0
    while True:
        row = cursor.fetchone()
        if row is None:
            return rows
        size += _row_size(row)
        if size > MAX_BYTES:
            raise _ReadError('数据展开后大小超过 20 MB，请缩小文件')
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise _ReadError('数据行数超过 20,000；请缩小范围，未截断分析数据')


def _append(tables, table):
    if len(tables) >= MAX_COLUMNS:
        raise _ReadError('文件数据表过多，最多支持 200 张表')
    tables.append(table)
    if sum(len(item.rows) for item in tables) > MAX_ROWS:
        raise _ReadError('文件合计数据行数超过 20,000；请缩小范围，未截断分析数据')
    if sum(_row_size(row) for item in tables for row in item.rows) > MAX_BYTES:
        raise _ReadError('文件数据展开后合计大小超过 20 MB，请缩小文件')


def _decode(content):
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise _ReadError('文件编码无法识别，请另存为 UTF-8 或 GB18030')


def _delimited(path, kind, content):
    text = _decode(content)
    delimiter = {'csv': ',', 'tsv': '\t'}.get(kind)
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:65536], delimiters=',\t;|').delimiter
        except csv.Error:
            raise _ReadError('TXT 分隔符无法确定，请使用逗号、制表符、分号或竖线分隔并提供表头') from None
    reader = csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True)
    header = next(reader, [])
    rows = []
    for row in reader:
        if not row or all(cell == '' for cell in row):
            continue
        rows.append(tuple(row))
        if len(rows) > MAX_ROWS:
            raise _ReadError('数据行数超过 20,000；请缩小范围，未截断分析数据')
    return [_table(path.stem, header, rows, path, kind)]


def _json_object(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise _ReadError('JSON 字段重复，无法确定字段映射')
        record[key] = value
    return record


def _json(path, kind, content):
    def decode(value):
        return json.loads(value, parse_float=Decimal, object_pairs_hook=_json_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(_ReadError('JSON 包含非有限数字')))
    text = _decode(content)
    if kind == 'json':
        records = decode(text)
        if isinstance(records, dict) and set(records) == {'records'}:
            records = records['records']
    else:
        records = []
        for line in text.splitlines():
            if line.strip():
                records.append(decode(line))
                if len(records) > MAX_ROWS:
                    raise _ReadError('数据行数超过 20,000；请缩小范围，未截断分析数据')
    if not isinstance(records, list) or not records or not isinstance(records[0], dict):
        raise _ReadError('JSON 必须为记录对象数组或 {"records": [...]} 平面表格')
    columns = tuple(records[0])
    rows = []
    for record in records:
        if not isinstance(record, dict) or set(record) != set(columns):
            raise _ReadError('JSON 每行必须包含完全相同的字段，请先统一为平面记录')
        if any(isinstance(value, (dict, list)) for value in record.values()):
            raise _ReadError('JSON 包含嵌套对象或数组，请先展开为每行一笔记录的平面字段')
        rows.append(tuple(record[column] for column in columns))
    return [_table(path.stem, columns, rows, path, kind)]


def _coordinates(row, column):
    # Row zero is the header; the limits include it. Binary coordinates are zero based.
    if row > MAX_ROWS or column >= MAX_COLUMNS:
        raise _ReadError('工作表行数或列数超过限制，请缩小有效区域')


def _xlsb_records(source):
    """Yield bounded BIFF12 records without constructing a worksheet cell matrix."""
    while True:
        first = source.read(1)
        if not first:
            return
        record_type = first[0] & 0x7f
        if first[0] & 0x80:
            second = source.read(1)
            if not second or second[0] & 0x80:
                raise _ReadError('XLSB 记录类型损坏，请重新导出')
            record_type |= second[0] << 7
        length = 0
        for shift in range(0, 28, 7):
            byte = source.read(1)
            if not byte:
                raise _ReadError('XLSB 记录长度损坏，请重新导出')
            length |= (byte[0] & 0x7f) << shift
            if not byte[0] & 0x80:
                break
        else:
            raise _ReadError('XLSB 记录长度损坏，请重新导出')
        if length > MAX_ARCHIVE_BYTES:
            raise _ReadError('XLSB 记录展开后过大，请缩小工作簿')
        payload = source.read(length)
        if len(payload) != length:
            raise _ReadError('XLSB 记录内容损坏，请重新导出')
        yield record_type, payload


def _check_xlsb_sheet(source):
    for record_type, payload in _xlsb_records(source):
        if record_type == 0x94:  # BrtWsDim: inclusive start/end row and column.
            if len(payload) != 16:
                raise _ReadError('XLSB 工作表维度损坏，请重新导出')
            start_row, end_row, start_column, end_column = struct.unpack('<4I', payload)
            _coordinates(start_row, start_column)
            _coordinates(end_row, end_column)
            if end_row < start_row or end_column < start_column:
                raise _ReadError('XLSB 工作表维度损坏，请重新导出')
        elif record_type == 0:  # BrtRowHdr, including rows beyond a forged dimension.
            if len(payload) < 4:
                raise _ReadError('XLSB 行记录损坏，请重新导出')
            _coordinates(struct.unpack_from('<I', payload)[0], 0)
        elif 1 <= record_type <= 0x0b:  # Blank/value/formula cell records.
            if len(payload) < 4:
                raise _ReadError('XLSB 单元格记录损坏，请重新导出')
            _coordinates(0, struct.unpack_from('<I', payload)[0])


def _check_xls(path):
    """Inspect bounded OLE/BIFF8 bytes before Calamine constructs any ranges."""
    try:
        import olefile
    except ImportError:
        raise _ReadError('XLS 安全读取需要 olefile，请安装后重试或另存为 XLSX') from None
    with olefile.OleFileIO(path) as archive:
        streams = [name for name in archive.listdir() if len(name) == 1 and name[0].casefold() in {'workbook', 'book'}]
        if len(streams) != 1 or archive.get_size(streams[0]) > MAX_BYTES:
            raise _ReadError('XLS 工作簿流缺失、重复或过大，请另存为 XLSX')
        content = archive.openstream(streams[0]).read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise _ReadError('XLS 工作簿展开后过大，请另存为 XLSX')
    offset, bof_offsets, sheet_offsets = 0, set(), []
    cells = {0x0006, 0x0201, 0x0203, 0x0204, 0x0205, 0x027e, 0x00fd, 0x00d6}
    while offset + 4 <= len(content):
        record_type, length = struct.unpack_from('<HH', content, offset)
        start = offset + 4
        if record_type == 0 and length == 0:
            if any(content[offset:]):
                raise _ReadError('XLS 记录结构损坏，请另存为 XLSX')
            break  # OLE workbook streams may end with zero padding.
        if start + length > len(content):
            raise _ReadError('XLS 记录长度损坏，请另存为 XLSX')
        payload = memoryview(content)[start:start + length]
        if record_type == 0x0809:
            if length < 4 or struct.unpack_from('<H', payload)[0] != 0x0600:
                raise _ReadError('仅支持可安全检查的 BIFF8 XLS，请将旧版 XLS 另存为 XLSX')
            bof_offsets.add(offset)
        elif not bof_offsets:
            raise _ReadError('仅支持可安全检查的 BIFF8 XLS，请另存为 XLSX')
        elif record_type == 0x002f:  # FILEPASS: encrypted records cannot be inspected.
            raise _ReadError('不支持加密 XLS，请提供未加密副本')
        elif record_type == 0x0085:  # BoundSheet8 offsets must point at inspected BOFs.
            if length < 6:
                raise _ReadError('XLS 工作表索引损坏，请另存为 XLSX')
            sheet_offsets.append(struct.unpack_from('<I', payload)[0])
            if len(sheet_offsets) > MAX_COLUMNS:
                raise _ReadError('工作表数量超过 200，请缩小工作簿')
        elif record_type == 0x0200:
            if length not in (14, 16):
                raise _ReadError('仅支持可安全检查的 BIFF8 XLS 维度，请另存为 XLSX')
            first_row, end_row, first_column, end_column = struct.unpack_from('<IIHH', payload)
            _coordinates(first_row, first_column)
            _coordinates(max(0, end_row - 1), max(0, end_column - 1))
            if end_row < first_row or end_column < first_column:
                raise _ReadError('XLS 工作表维度损坏，请另存为 XLSX')
        elif record_type == 0x0208:  # ROW index and exclusive last column.
            if length < 6:
                raise _ReadError('XLS 行记录损坏，请另存为 XLSX')
            row, first_column, end_column = struct.unpack_from('<HHH', payload)
            _coordinates(row, first_column)
            _coordinates(row, max(0, end_column - 1))
        elif record_type in cells or record_type in {0x00bd, 0x00be}:
            if length < 4:
                raise _ReadError('XLS 单元格记录损坏，请另存为 XLSX')
            row, column = struct.unpack_from('<HH', payload)
            _coordinates(row, column)
            if record_type in {0x00bd, 0x00be}:
                if length < 6:
                    raise _ReadError('XLS 多单元格记录损坏，请另存为 XLSX')
                _coordinates(row, struct.unpack_from('<H', payload, length - 2)[0])
        offset = start + length
    if not bof_offsets or any(position not in bof_offsets for position in sheet_offsets):
        raise _ReadError('XLS 工作表索引或 BIFF8 记录损坏，请另存为 XLSX')


def _check_archive(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS or sum(item.file_size for item in members) > MAX_ARCHIVE_BYTES:
            raise _ReadError('工作簿解压后过大或文件过多，请缩小工作簿')
        if any(item.flag_bits & 1 for item in members):
            raise _ReadError('不支持加密工作簿，请提供未加密的表格副本')
        names = {member.filename for member in members}
        worksheet_parts = set()
        for relationship_path in ('xl/_rels/workbook.bin.rels', 'xl/_rels/workbook.xml.rels'):
            if relationship_path in names:
                root = ET.fromstring(archive.read(relationship_path))
                for relationship in root:
                    if relationship.get('Type', '').endswith('/worksheet'):
                        target = relationship.get('Target', '')
                        resolved = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl', target))
                        if relationship.get('TargetMode') == 'External' or resolved.startswith('../') or resolved not in names:
                            raise _ReadError('工作表引用无效，请重新导出本地工作簿')
                        worksheet_parts.add(resolved)
        for member in members:
            worksheet = member.filename in worksheet_parts or (member.filename.startswith('xl/worksheets/') and '/_rels/' not in member.filename)
            if worksheet and (member.filename.endswith('.bin') or path.suffix.lower() == '.xlsb'):
                with archive.open(member) as source:
                    _check_xlsb_sheet(source)
            elif worksheet and member.filename.endswith('.xml'):
                with archive.open(member) as source:
                    for _, element in ET.iterparse(source):
                        tag = element.tag.rsplit('}', 1)[-1]
                        if tag in {'dimension', 'c'}:
                            reference = element.get('ref', '') if tag == 'dimension' else element.get('r', '')
                            for letters, digits in re.findall(r'([A-Z]+)([0-9]+)', reference):
                                column = 0
                                for letter in letters:
                                    column = column * 26 + ord(letter) - 64
                                if column > MAX_COLUMNS or int(digits) > MAX_ROWS + 1:
                                    raise _ReadError('工作表行数或列数超过限制，请缩小有效区域')
                        element.clear()
            elif member.filename == 'content.xml':
                namespace = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
                row_count = column_count = 0
                with archive.open(member) as source:
                    for event, element in ET.iterparse(source, events=('start', 'end')):
                        tag = element.tag
                        if event == 'start' and tag == namespace + 'table':
                            row_count = 0
                        elif event == 'start' and tag == namespace + 'table-row':
                            row_count += int(element.get(namespace + 'number-rows-repeated', '1'))
                            column_count = 0
                            if row_count > MAX_ROWS + 1:
                                raise _ReadError('工作表行数超过限制，请缩小有效区域')
                        elif event == 'start' and tag in {namespace + 'table-cell', namespace + 'covered-table-cell'}:
                            column_count += int(element.get(namespace + 'number-columns-repeated', '1'))
                            if column_count > MAX_COLUMNS:
                                raise _ReadError('工作表列数超过限制，请缩小有效区域')
                        if event == 'end':
                            element.clear()


def _workbook(path, kind):
    if kind in {'xlsx', 'xlsb', 'ods'}:
        _check_archive(path)
    elif kind == 'xls':
        _check_xls(path)
    try:
        from python_calamine import CalamineWorkbook
    except ImportError:
        raise _ReadError('缺少工作簿读取依赖 python-calamine，请先安装后重试') from None
    tables = []
    with CalamineWorkbook.from_path(str(path)) as workbook:
        for name in workbook.sheet_names:
            sheet = workbook.get_sheet_by_name(name)
            if not sheet.height or not sheet.width:
                continue
            if sheet.total_height > MAX_ROWS + 1 or sheet.total_width > MAX_COLUMNS:
                raise _ReadError('工作表行数或列数超过限制，请缩小范围，未截断分析数据')
            values = sheet.to_python(skip_empty_area=False)
            if not values or not any(any(value != '' for value in row) for row in values):
                continue
            columns = values[0]
            if any(not isinstance(column, str) for column in columns):
                raise _ReadError('工作表首行必须是明确的文本表头，请移除标题行和合并单元格')
            rows = [tuple(row) for row in values[1:] if any(value != '' for value in row)]
            _append(tables, _table(name, columns, rows, path, kind))
    return tables


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite(path, kind):
    tables = []
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    deadline = time.monotonic() + 5
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        connection.enable_load_extension(False)
        connection.execute('PRAGMA query_only=ON')
        connection.execute('PRAGMA trusted_schema=OFF')
        connection.execute('BEGIN')
        names = connection.execute("SELECT name FROM pragma_table_list WHERE schema='main' AND type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        for (name,) in names:
            cursor = connection.execute(f'SELECT * FROM {_quote(name)} LIMIT ?', [MAX_ROWS + 1])
            _append(tables, _table(name, [column[0] for column in cursor.description], _fetch_rows(cursor), path, kind))
    finally:
        connection.close()
    return tables


def _duckdb(path, kind):
    config = {'memory_limit': '128MB', 'threads': '1', 'autoinstall_known_extensions': 'false',
              'autoload_known_extensions': 'false', 'max_temp_directory_size': '0B'}
    if kind != 'parquet':
        config['enable_external_access'] = 'false'
    connection = duckdb.connect(':memory:' if kind == 'parquet' else str(path),
                                read_only=kind != 'parquet', config=config)
    try:
        if kind == 'parquet':
            cursor = connection.execute('SELECT * FROM read_parquet(?) LIMIT ?', [str(path), MAX_ROWS + 1])
            return [_table(path.stem, [column[0] for column in cursor.description], _fetch_rows(cursor), path, kind)]
        names = connection.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('information_schema','pg_catalog') ORDER BY table_schema,table_name").fetchall()
        tables = []
        for schema, name in names:
            cursor = connection.execute(f'SELECT * FROM {_quote(schema)}.{_quote(name)} LIMIT ?', [MAX_ROWS + 1])
            label = name if schema == 'main' else schema + '.' + name
            _append(tables, _table(label, [column[0] for column in cursor.description], _fetch_rows(cursor), path, kind))
        return tables
    finally:
        connection.close()


def read_file_tables(path: Path) -> list[TableData]:
    """Read supported tables, or fail without returning a truncated partial result."""
    try:
        path = Path(path)
        kind = path.suffix.lower().lstrip('.')
        if kind not in _FORMATS:
            raise _ReadError('不支持此文件类型。请将 PDF、文档或图片整理为 CSV、Excel 或平面 JSON 表格')
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise _ReadError('文件不存在、为空或大小超过 20 MB，请缩小文件后重试')
        if kind in {'csv', 'tsv', 'txt', 'json', 'jsonl', 'ndjson'}:
            with path.open('rb') as source:
                content = source.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise _ReadError('文件大小超过 20 MB，请缩小文件后重试')
            tables = _delimited(path, kind, content) if kind in {'csv', 'tsv', 'txt'} else _json(path, kind, content)
        elif kind in _WORKBOOKS:
            tables = _workbook(path, kind)
        elif kind in {'sqlite', 'sqlite3', 'db'}:
            tables = _sqlite(path, kind)
        else:
            tables = _duckdb(path, kind)
        if not tables:
            raise _ReadError('文件没有可读取的用户数据表')
        if sum(len(table.rows) for table in tables) > MAX_ROWS:
            raise _ReadError('文件合计数据行数超过 20,000；请缩小范围，未截断分析数据')
        return tables
    except _ReadError:
        raise
    except Exception:
        raise ValueError('文件无法读取：格式损坏、受保护或内容不符合表格要求，请重新导出为标准表格') from None
