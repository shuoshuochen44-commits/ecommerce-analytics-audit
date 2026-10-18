"""Bounded physical-table extraction; no arbitrary SQL or connection options.

Local sources are opened read-only. Optional network sources use fixed SQLAlchemy
dialects and transaction policies; availability never implies live connectivity
has been tested. Each call opens a fresh transaction for one table extraction.
"""

from contextlib import contextmanager
from datetime import date, datetime, time
from decimal import Decimal
import importlib.util
import ipaddress
import math
from pathlib import Path
import re
import sqlite3
from threading import Timer
from time import monotonic

from .source_types import MAX_BYTES, MAX_COLUMNS, MAX_ROWS, TableData


_DRIVERS = {
    'sqlite': ('sqlite3', None), 'duckdb': ('duckdb', None),
    'mysql': ('pymysql', 'mysql+pymysql'),
    'mariadb': ('pymysql', 'mariadb+pymysql'),
    'postgresql': ('psycopg', 'postgresql+psycopg'),
    'mssql': ('pymssql', 'mssql+pymssql'),
    'oracle': ('oracledb', 'oracle+oracledb'),
}
_SYSTEM_SCHEMAS = {
    'information_schema', 'pg_catalog', 'pg_toast', 'mysql',
    'performance_schema', 'sys', 'system', 'dbsnmp', 'outln', 'xdb',
    'ctxsys', 'mdsys', 'ordsys', 'wmsys', 'audsys', 'sysaux',
}
_MAX_TABLES = 1000
_NETWORK_CONSISTENCY = {
    'postgresql': 'single-table repeatable-read read-only transaction',
    'mysql': 'single-table SELECT in read-only repeatable-read transaction; snapshot requires transactional storage',
    'mariadb': 'single-table SELECT in read-only repeatable-read transaction; snapshot requires transactional storage',
    'oracle': 'single-table read-only transaction snapshot',
    'mssql': 'single-table SELECT in serializable transaction, rolled back; no server-enforced read-only mode',
}


class DatabaseSourceError(ValueError):
    """Public error containing only adapter-authored, credential-free text."""


def _installed(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def database_capabilities():
    result = []
    for kind, (driver, _) in _DRIVERS.items():
        installed = _installed(driver) and (kind in ('sqlite', 'duckdb') or _installed('sqlalchemy'))
        tested = kind in ('sqlite', 'duckdb') and installed
        result.append({'kind': kind, 'driver': driver, 'installed': installed,
                       'tested': tested,
                       'status': 'local-tested' if tested else 'not-live-tested' if installed else 'missing-driver'})
    return result


def _identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 200 and bool(value.strip()) and not any(ord(c) < 32 for c in value)


def _system_schema(schema):
    return schema.casefold() in _SYSTEM_SCHEMAS or schema.casefold().startswith(('pg_', 'sqlite_'))


def _validate(config):
    if (not isinstance(config, dict) or not isinstance(config.get('kind'), str)
            or config['kind'] not in _DRIVERS):
        raise DatabaseSourceError('无效数据库类型或配置')
    config = dict(config)
    local = config['kind'] in ('sqlite', 'duckdb')
    allowed = {'kind', 'schema', 'timeout_seconds'} | ({'path'} if local else {'host', 'port', 'database', 'username', 'password'})
    if set(config) - allowed:
        raise DatabaseSourceError('不允许连接 URI、SQL 或额外连接参数')
    timeout = config.get('timeout_seconds', 10)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise DatabaseSourceError('连接与读取超时必须在 0 到 30 秒之间')
    config['timeout_seconds'] = float(timeout)
    schema = config.get('schema')
    if schema is not None and (not _identifier(schema) or _system_schema(schema)):
        raise DatabaseSourceError('无效或不允许的 Schema')
    if local:
        path = config.get('path')
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise DatabaseSourceError('数据库路径必须是现有文件的绝对路径')
        try:
            path = Path(path).resolve(strict=True)
            if not path.is_file():
                raise OSError
        except (OSError, ValueError):
            raise DatabaseSourceError('数据库文件不存在或不是普通文件') from None
        config['path'] = path
        if config['kind'] == 'sqlite' and schema not in (None, 'main'):
            raise DatabaseSourceError('SQLite 仅允许 main Schema')
    else:
        for field in ('host', 'database', 'username'):
            value = config.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 255 or any(ord(c) < 32 for c in value):
                raise DatabaseSourceError('必须明确提供主机、端口、数据库和用户')
        host = config['host']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', host):
            try:
                ipaddress.IPv6Address(host)
            except ValueError:
                raise DatabaseSourceError('主机必须为域名或 IP，不能包含连接 URI') from None
        if type(config.get('port')) is not int or not 1 <= config['port'] <= 65535:
            raise DatabaseSourceError('必须明确提供有效端口')
        if not isinstance(config.get('password'), str) or len(config['password']) > 4096:
            raise DatabaseSourceError('必须提供密码字段')
    return config


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _columns(names):
    if not 0 < len(names) <= MAX_COLUMNS:
        raise DatabaseSourceError('表格列数必须在 1 到 200 之间')
    if not all(_identifier(name) for name in names) or len({n.casefold() for n in names}) != len(names):
        raise DatabaseSourceError('表头为空、重复、过长或含控制字符')
    return tuple(names)


def _bounded_rows(cursor, columns, deadline):
    size = sum(len(c.encode('utf-8')) + 4 for c in columns)
    rows = []
    while True:
        batch = cursor.fetchmany(min(256, MAX_ROWS + 1 - len(rows)))
        if monotonic() >= deadline:
            raise DatabaseSourceError('数据库读取超时')
        if not batch:
            return rows
        for row in batch:
            values = tuple(row)
            if len(rows) >= MAX_ROWS:
                raise DatabaseSourceError('数据行数超过 20,000；未截断分析数据')
            for value in values:
                if value is None:
                    size += 4
                elif isinstance(value, (bytes, bytearray, memoryview)):
                    size += len(value) * 2 + 4
                elif isinstance(value, (str, int, float, Decimal, date, datetime, time)):
                    size += len(str(value).encode('utf-8')) + 4
                else:
                    raise DatabaseSourceError('数据库包含暂不支持的字段类型')
                if size > MAX_BYTES:
                    raise DatabaseSourceError('表格数据超过 20 MB 字节预算，未返回部分数据')
            size += 4
            if size > MAX_BYTES:
                raise DatabaseSourceError('表格数据超过 20 MB 字节预算，未返回部分数据')
            rows.append(values)


@contextmanager
def _local_connection(config):
    deadline = monotonic() + config['timeout_seconds']
    connection = None
    timer = None
    try:
        if config['kind'] == 'sqlite':
            connection = sqlite3.connect(config['path'].as_uri() + '?mode=ro', uri=True,
                                         timeout=config['timeout_seconds'])
            connection.enable_load_extension(False)
            connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
            connection.execute('BEGIN')
        else:
            import duckdb
            connection = duckdb.connect(str(config['path']), read_only=True)
            for setting in ('SET enable_external_access=false',
                            'SET autoinstall_known_extensions=false',
                            'SET autoload_known_extensions=false', 'SET threads=1',
                            "SET memory_limit='256MB'", 'SET max_expression_depth=100'):
                connection.execute(setting)
            connection.execute('BEGIN TRANSACTION')
        timer = Timer(max(0.000001, deadline - monotonic()), connection.interrupt)
        timer.daemon = True
        timer.start()
        yield connection, deadline
    finally:
        if timer:
            timer.cancel()
        if connection is not None:
            connection.close()


def _local_catalog(connection, config):
    if config['kind'] == 'sqlite':
        entries = connection.execute(
            "SELECT name FROM pragma_table_list WHERE schema='main' AND type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?", (_MAX_TABLES + 1,)).fetchall()
        tables = [{'name': row[0], 'schema': 'main',
                   'columns': [col[1] for col in connection.execute('SELECT * FROM pragma_table_xinfo(?)', (row[0],)).fetchall() if col[6] != 1]}
                  for row in entries]
    else:
        entries = connection.execute(
            "SELECT table_name, table_schema FROM information_schema.tables "
            "WHERE table_type='BASE TABLE' AND table_catalog=current_database() "
            "ORDER BY table_schema, table_name LIMIT ?", (_MAX_TABLES + 1,)).fetchall()
        tables = []
        for name, schema in entries:
            if _system_schema(schema) or (config.get('schema') is not None and schema != config['schema']):
                continue
            names = connection.execute(
                'SELECT column_name FROM information_schema.columns WHERE table_catalog=current_database() '
                'AND table_name=? AND table_schema=? ORDER BY ordinal_position', (name, schema)).fetchall()
            tables.append({'name': name, 'schema': schema, 'columns': [c[0] for c in names]})
    if len(entries) > _MAX_TABLES:
        raise DatabaseSourceError('数据库表数量超过元数据预算')
    return tables


def _select_table(tables, table, schema):
    if not _identifier(table) or (schema is not None and (not _identifier(schema) or _system_schema(schema))):
        raise DatabaseSourceError('无效表名或 Schema')
    matches = [item for item in tables if item['name'] == table and (schema is None or item['schema'] == schema)]
    if not matches:
        raise DatabaseSourceError('表不存在或不允许访问；仅支持枚举的用户物理表')
    if len(matches) > 1:
        raise DatabaseSourceError('表名存在歧义，请明确指定 Schema')
    return matches[0]


@contextmanager
def _network_connection(config):
    driver, dialect = _DRIVERS[config['kind']]
    if not _installed('sqlalchemy') or not _installed(driver):
        raise DatabaseSourceError('数据库驱动尚未安装：需要 SQLAlchemy 和 ' + driver)
    import sqlalchemy as sa
    timeout = config['timeout_seconds']
    seconds = max(1, math.ceil(timeout))
    milliseconds = max(1, math.ceil(timeout * 1000))
    kind = config['kind']
    url_fields = {key: config[key] for key in ('host', 'port', 'username', 'password')}
    if kind == 'oracle':
        url_fields['query'] = {'service_name': config['database']}
        connect_args = {'tcp_connect_timeout': timeout}
    else:
        url_fields['database'] = config['database']
        if kind in ('mysql', 'mariadb'):
            connect_args = {'connect_timeout': seconds, 'read_timeout': timeout,
                            'write_timeout': timeout, 'local_infile': False}
        elif kind == 'postgresql':
            # libpq rounds connect_timeout up to a minimum of two seconds.
            connect_args = {'connect_timeout': max(2, seconds),
                            'options': f'-c statement_timeout={milliseconds} -c lock_timeout={milliseconds}'}
        else:
            connect_args = {'login_timeout': seconds, 'timeout': seconds}
    url = sa.URL.create(dialect, **url_fields)
    engine = None
    connection = None
    deadline = monotonic() + timeout
    try:
        engine = sa.create_engine(url, connect_args=connect_args, poolclass=sa.pool.NullPool,
                                  echo=False, hide_parameters=True)
        connection = engine.connect()
        if monotonic() >= deadline:
            raise DatabaseSourceError('数据库连接超时')
        if kind == 'postgresql':
            policies = ['SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY',
                        f'SET LOCAL statement_timeout={milliseconds}',
                        f'SET LOCAL lock_timeout={milliseconds}']
        elif kind in ('mysql', 'mariadb'):
            policies = [f'SET SESSION MAX_EXECUTION_TIME={milliseconds}' if kind == 'mysql'
                        else f'SET SESSION max_statement_time={timeout}',
                        'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ',
                        'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY']
        elif kind == 'oracle':
            connection.connection.driver_connection.call_timeout = milliseconds
            policies = ['SET TRANSACTION READ ONLY']
        else:
            # SQL Server has no SET TRANSACTION READ ONLY. Never claim it does.
            policies = [f'SET LOCK_TIMEOUT {milliseconds}',
                        'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE']
        for policy in policies:
            result = connection.exec_driver_sql(policy)
            if result is not None:
                result.close()
        yield connection, deadline
    finally:
        try:
            if connection is not None:
                try:
                    connection.rollback()
                finally:
                    connection.close()
        finally:
            if engine is not None:
                engine.dispose()


def _network_catalog(connection, config):
    import sqlalchemy as sa
    inspector = sa.inspect(connection)
    schema = config.get('schema') or inspector.default_schema_name
    if not _identifier(schema) or _system_schema(schema):
        raise DatabaseSourceError('不允许枚举系统 Schema；请明确指定用户 Schema')
    # Enumerate the configured/default schema only; never discover other users'
    # schemas, views, synonyms or foreign databases.
    names = inspector.get_table_names(schema=schema)
    if len(names) > _MAX_TABLES:
        raise DatabaseSourceError('数据库表数量超过元数据预算')
    tables = []
    metadata_bytes = 0
    for name in sorted(names):
        if not _identifier(name) or name.casefold().startswith(('sqlite_', 'pg_')):
            continue
        columns = [column['name'] for column in inspector.get_columns(name, schema=schema)]
        metadata_bytes += sum(len(str(value).encode('utf-8')) + 4 for value in [name, schema, *columns])
        if metadata_bytes > MAX_BYTES:
            raise DatabaseSourceError('数据库元数据超过 20 MB 字节预算')
        tables.append({'name': name, 'schema': schema, 'columns': columns})
    return tables


def inspect_database(config):
    config = _validate(config)
    try:
        if config['kind'] in ('sqlite', 'duckdb'):
            with _local_connection(config) as (connection, deadline):
                tables = _local_catalog(connection, config)
                if monotonic() >= deadline:
                    raise DatabaseSourceError('数据库元数据读取超时')
        else:
            with _network_connection(config) as (connection, deadline):
                tables = _network_catalog(connection, config)
                if monotonic() >= deadline:
                    raise DatabaseSourceError('数据库元数据读取超时')
        return {'kind': config['kind'], 'tables': tables}
    except DatabaseSourceError:
        raise
    except Exception:
        raise DatabaseSourceError('数据库连接或元数据读取失败；请检查文件、权限、驱动和连接配置') from None


def read_database_table(config, table, schema=None):
    config = _validate(config)
    schema = schema if schema is not None else config.get('schema')
    try:
        if config['kind'] in ('sqlite', 'duckdb'):
            with _local_connection(config) as (connection, deadline):
                entry = _select_table(_local_catalog(connection, config), table, schema)
                columns = _columns(entry['columns'])
                query = ('SELECT ' + ', '.join(_quote(c) for c in columns) + ' FROM '
                         + _quote(entry['schema']) + '.' + _quote(entry['name']) + f' LIMIT {MAX_ROWS + 1}')
                rows = _bounded_rows(connection.execute(query), columns, deadline)
            consistency = 'single-table read-only transaction snapshot'
        else:
            with _network_connection(config) as (connection, deadline):
                entry = _select_table(_network_catalog(connection, config), table, schema)
                columns = _columns(entry['columns'])
                import sqlalchemy as sa
                relation = sa.table(entry['name'], *(sa.column(c) for c in columns), schema=entry['schema'])
                statement = sa.select(relation).limit(MAX_ROWS + 1)
                cursor = connection.execution_options(stream_results=True, yield_per=256).execute(statement)
                try:
                    rows = _bounded_rows(cursor, columns, deadline)
                finally:
                    cursor.close()
            consistency = _NETWORK_CONSISTENCY[config['kind']]
        return TableData(name=entry['name'], columns=columns, rows=rows,
                         origin={'kind': config['kind'], 'table': entry['name'],
                                 'schema': entry['schema'], 'consistency': consistency})
    except DatabaseSourceError:
        raise
    except Exception:
        raise DatabaseSourceError('数据库表读取失败；请检查权限、字段类型和读取超时') from None
