"""Real local extraction tests; network mocks only verify configuration/policy."""

from decimal import Decimal
from contextlib import contextmanager
import hashlib
import socket
import sqlite3
import sys
from time import monotonic
from types import SimpleNamespace

import duckdb
import pytest

from zhishu_inspection import database_sources as sources


@pytest.fixture(params=['sqlite', 'duckdb'])
def local_db(tmp_path, request):
    kind = request.param
    path = tmp_path / ('sample.' + kind)
    connection = sqlite3.connect(path) if kind == 'sqlite' else duckdb.connect(str(path))
    connection.execute('CREATE TABLE "order ""lines" ("item id" INTEGER, amount DECIMAL(12,2))')
    connection.execute('INSERT INTO "order ""lines" VALUES (1, 12.34), (2, NULL)')
    connection.execute('CREATE VIEW hidden_view AS SELECT * FROM "order ""lines"')
    connection.commit()
    connection.close()
    return {'kind': kind, 'path': str(path)}


def test_inspect_and_extract_exact_quoted_table_without_changes(local_db):
    before = hashlib.sha256(open(local_db['path'], 'rb').read()).digest()
    catalog = sources.inspect_database(local_db)
    assert catalog['kind'] == local_db['kind']
    assert len(catalog['tables']) == 1
    entry = catalog['tables'][0]
    assert entry['name'] == 'order "lines'
    assert entry['columns'] == ['item id', 'amount']
    data = sources.read_database_table(local_db, entry['name'], entry['schema'])
    assert data.columns == ('item id', 'amount')
    assert data.rows[0][0] == 1
    assert str(data.rows[0][1]) == '12.34'
    assert data.rows[1] == (2, None)
    if local_db['kind'] == 'duckdb':
        assert isinstance(data.rows[0][1], Decimal)
    assert data.origin['kind'] == local_db['kind']
    assert 'consistency' in data.origin
    assert local_db['path'] not in str(data.origin)
    assert hashlib.sha256(open(local_db['path'], 'rb').read()).digest() == before


@pytest.mark.parametrize('table', ['hidden_view', 'sqlite_master', 'information_schema.tables', 'order "lines; DROP TABLE x', 'absent'])
def test_only_enumerated_physical_user_tables_can_be_read(local_db, table):
    with pytest.raises(ValueError):
        sources.read_database_table(local_db, table)


def test_duckdb_ambiguous_table_requires_schema(tmp_path):
    path = tmp_path / 'schemas.duckdb'
    with duckdb.connect(str(path)) as connection:
        connection.execute('CREATE TABLE same (x INT)')
        connection.execute('CREATE SCHEMA sales')
        connection.execute('CREATE TABLE sales.same (x INT)')
        connection.execute('INSERT INTO sales.same VALUES (7)')
    config = {'kind': 'duckdb', 'path': str(path)}
    with pytest.raises(ValueError, match='[Ss]chema|歧义'):
        sources.read_database_table(config, 'same')
    assert sources.read_database_table(config, 'same', 'sales').rows == [(7,)]


def test_row_overflow_fails_without_truncation(tmp_path):
    path = tmp_path / 'overflow.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE rows (x INTEGER)')
        connection.executemany('INSERT INTO rows VALUES (?)', ((i,) for i in range(20001)))
    with pytest.raises(ValueError, match='20,000|行数'):
        sources.read_database_table({'kind': 'sqlite', 'path': str(path)}, 'rows')


def test_column_and_byte_overflow_fail(tmp_path):
    path = tmp_path / 'wide.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE wide (' + ','.join(f'x{i} INT' for i in range(201)) + ')')
        connection.execute('CREATE TABLE big (x BLOB)')
        connection.execute('INSERT INTO big VALUES (zeroblob(20971521))')
    config = {'kind': 'sqlite', 'path': str(path)}
    with pytest.raises(ValueError, match='列数'):
        sources.read_database_table(config, 'wide')
    with pytest.raises(ValueError, match='20|字节'):
        sources.read_database_table(config, 'big')


@pytest.mark.parametrize('patch', [
    {'path': 'relative.sqlite'}, {'path': 'file:///tmp/db'}, {'kind': 'other'},
    {'uri': 'sqlite:///x'}, {'sql': 'SELECT 1'}, {'connect_args': {}},
    {'timeout_seconds': 0}, {'timeout_seconds': float('nan')}, {'timeout_seconds': True},
])
def test_local_config_validation_is_closed(local_db, patch):
    with pytest.raises(ValueError):
        sources.inspect_database({**local_db, **patch})


def test_missing_path_does_not_create_database(tmp_path):
    path = tmp_path / 'absent.sqlite'
    with pytest.raises(ValueError):
        sources.inspect_database({'kind': 'sqlite', 'path': str(path)})
    assert not path.exists()


def test_directory_is_not_a_database(tmp_path):
    with pytest.raises(ValueError):
        sources.inspect_database({'kind': 'sqlite', 'path': str(tmp_path)})


def test_broken_database_error_is_scrubbed(tmp_path):
    path = tmp_path / 'secret-password.sqlite'
    path.write_bytes(b'not a database secret-password')
    with pytest.raises(ValueError) as caught:
        sources.inspect_database({'kind': 'sqlite', 'path': str(path)})
    assert 'secret-password' not in str(caught.value)
    assert caught.value.__cause__ is None


NETWORK = {'kind': 'postgresql', 'host': '127.0.0.1', 'port': 5432,
           'database': 'shop', 'username': 'reader', 'password': 's3cr3t:@/%'}


@pytest.mark.parametrize('patch', [
    {'host': 'postgresql://localhost/db'}, {'host': 'a/b'}, {'port': 0},
    {'port': True}, {'port': '5432'}, {'database': ''}, {'username': ''},
    {'password': None}, {'schema': 'pg_catalog'}, {'schema': 'information_schema'},
    {'url': 'postgresql://secret'}, {'query': {}}, {'engine_args': {}}, {'sql': 'DROP TABLE t'},
])
def test_network_config_rejects_unsafe_fields_without_connecting(patch):
    with pytest.raises(ValueError):
        sources.inspect_database({**NETWORK, **patch})


def test_capabilities_do_not_claim_live_network_tests():
    capabilities = {row['kind']: row for row in sources.database_capabilities()}
    assert set(capabilities) == {'sqlite', 'duckdb', 'mysql', 'mariadb', 'postgresql', 'mssql', 'oracle'}
    assert capabilities['sqlite']['installed'] is True
    assert capabilities['sqlite']['tested'] is True
    for kind in ('mysql', 'mariadb', 'postgresql', 'mssql', 'oracle'):
        assert capabilities[kind]['tested'] is False
        assert isinstance(capabilities[kind]['installed'], bool)
        assert capabilities[kind]['driver']


def test_missing_network_driver_has_actionable_safe_error(monkeypatch):
    monkeypatch.setattr(sources, '_installed', lambda name: False)
    with pytest.raises(ValueError, match='驱动.*安装') as caught:
        sources.inspect_database(NETWORK)
    assert NETWORK['password'] not in str(caught.value)


@pytest.mark.parametrize('kind, expected_policy', [
    ('postgresql', 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'),
    ('mysql', 'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'),
    ('mariadb', 'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY'),
    ('mssql', 'SET TRANSACTION ISOLATION LEVEL SERIALIZABLE'),
    ('oracle', 'SET TRANSACTION READ ONLY'),
])
def test_network_configuration_and_read_policy_mock_not_live_e2e(monkeypatch, kind, expected_policy):
    captured = {'statements': []}

    class Connection:
        connection = SimpleNamespace(driver_connection=SimpleNamespace(call_timeout=None))

        def exec_driver_sql(self, statement):
            captured['statements'].append(statement)

        def rollback(self):
            captured['rollback'] = True

        def close(self):
            captured['closed'] = True

    class Engine:
        def connect(self):
            return Connection()

        def dispose(self):
            captured['disposed'] = True

    def create_url(drivername, **kwargs):
        captured['url'] = {'drivername': drivername, **kwargs}
        return object()

    def create_engine(url, **kwargs):
        captured['engine_options'] = kwargs
        return Engine()

    inspector = SimpleNamespace(default_schema_name='public',
                                get_table_names=lambda schema: ['orders'],
                                get_columns=lambda table, schema: [{'name': 'amount'}])
    fake = SimpleNamespace(URL=SimpleNamespace(create=create_url), create_engine=create_engine,
                           pool=SimpleNamespace(NullPool=object), inspect=lambda con: inspector)
    monkeypatch.setitem(sys.modules, 'sqlalchemy', fake)
    monkeypatch.setattr(sources, '_installed', lambda name: True)
    config = {**NETWORK, 'kind': kind}
    assert sources.inspect_database(config)['tables'] == [{'name': 'orders', 'schema': 'public', 'columns': ['amount']}]
    assert captured['url']['password'] == NETWORK['password']
    assert captured['url']['host'] == NETWORK['host']
    assert expected_policy in captured['statements']
    assert captured['engine_options']['echo'] is False
    assert captured['engine_options']['hide_parameters'] is True
    assert captured['engine_options']['connect_args']
    assert captured['rollback'] and captured['closed'] and captured['disposed']


def test_network_driver_exception_does_not_leak_credentials(monkeypatch):
    def failing_connection(config):
        raise RuntimeError('connect failed: ' + config['password'])
    monkeypatch.setattr(sources, '_network_connection', failing_connection, raising=False)
    with pytest.raises(ValueError) as caught:
        sources.inspect_database(NETWORK)
    assert NETWORK['password'] not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize('kind', ['mysql', 'mariadb', 'postgresql'])
def test_installed_real_driver_url_roundtrip_and_refused_local_connection(kind, monkeypatch):
    """Loads real dialect+driver, but deliberately has no live database server."""
    import sqlalchemy as sa
    real_create = sa.create_engine
    captured = {}

    def capture_engine(url, **kwargs):
        captured['url'] = url
        return real_create(url, **kwargs)

    monkeypatch.setattr(sa, 'create_engine', capture_engine)
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        config = {**NETWORK, 'kind': kind, 'port': reserved.getsockname()[1],
                  'database': 'shop @%/:', 'username': 'reader @/:', 'timeout_seconds': 2}
        with pytest.raises(ValueError) as caught:
            sources.inspect_database(config)
    assert caught.value.__cause__ is None
    assert config['password'] not in str(caught.value)
    assert captured['url'].password == config['password']
    assert captured['url'].username == config['username']
    assert captured['url'].database == config['database']


@pytest.mark.parametrize('kind', ['mysql', 'mariadb', 'postgresql', 'mssql', 'oracle'])
def test_network_select_compiles_with_real_dialect_and_bound_budget_not_live_e2e(monkeypatch, kind):
    from sqlalchemy.dialects import mysql, postgresql, mssql, oracle
    dialects = {'mysql': mysql.dialect(), 'mariadb': mysql.dialect(),
                'postgresql': postgresql.dialect(), 'mssql': mssql.dialect(), 'oracle': oracle.dialect()}
    captured = {}
    table_name = 'odd"\'; DROP TABLE x;--'

    class Cursor:
        calls = 0

        def fetchmany(self, count):
            self.calls += 1
            return [(Decimal('4.25'),)] if self.calls == 1 else []

        def close(self):
            captured['cursor_closed'] = True

    class Connection:
        def execution_options(self, **kwargs):
            captured['streaming'] = kwargs
            return self

        def execute(self, statement):
            captured['compiled'] = statement.compile(dialect=dialects[kind])
            return Cursor()

    @contextmanager
    def connection(config):
        yield Connection(), monotonic() + 10

    monkeypatch.setattr(sources, '_network_connection', connection)
    monkeypatch.setattr(sources, '_network_catalog', lambda con, cfg: [
        {'name': table_name, 'schema': 'sales', 'columns': ['amount']}])
    result = sources.read_database_table({**NETWORK, 'kind': kind}, table_name)
    assert result.rows == [(Decimal('4.25'),)]
    sql = str(captured['compiled'])
    quote = dialects[kind].identifier_preparer.quote
    assert quote('sales') + '.' + quote(table_name) in sql
    assert 20001 in captured['compiled'].params.values()
    assert captured['streaming']['stream_results'] is True
    assert captured['cursor_closed'] is True
    assert NETWORK['password'] not in str(result.origin)


def test_empty_table_is_valid(local_db):
    connection = sqlite3.connect(local_db['path']) if local_db['kind'] == 'sqlite' else duckdb.connect(local_db['path'])
    connection.execute('DELETE FROM "order ""lines"')
    connection.commit()
    connection.close()
    assert sources.read_database_table(local_db, 'order "lines').rows == []


def test_sqlite_virtual_tables_and_shadow_storage_are_not_exposed(tmp_path):
    path = tmp_path / 'fts.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE public_data (x INT)')
        connection.execute('CREATE VIRTUAL TABLE search_index USING fts5(content)')
    catalog = sources.inspect_database({'kind': 'sqlite', 'path': str(path)})
    assert [row['name'] for row in catalog['tables']] == ['public_data']


def test_byte_budget_includes_record_overhead(tmp_path, monkeypatch):
    path = tmp_path / 'small.sqlite'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE small (x TEXT)')
        connection.execute("INSERT INTO small VALUES ('a')")
    monkeypatch.setattr(sources, 'MAX_BYTES', 13)
    with pytest.raises(ValueError, match='字节'):
        sources.read_database_table({'kind': 'sqlite', 'path': str(path)}, 'small')


@pytest.mark.parametrize('config', [None, [], {'kind': []}, {'kind': {}}, {'kind': None}])
def test_malformed_config_types_are_safe_value_errors(config):
    with pytest.raises(ValueError):
        sources.inspect_database(config)


def test_network_system_default_schema_never_enumerated(monkeypatch):
    import sqlalchemy as sa
    inspector = SimpleNamespace(default_schema_name='information_schema')
    monkeypatch.setattr(sa, 'inspect', lambda connection: inspector)

    @contextmanager
    def connection(config):
        yield object(), monotonic() + 10

    monkeypatch.setattr(sources, '_network_connection', connection)
    with pytest.raises(ValueError, match='系统'):
        sources.inspect_database(NETWORK)


def test_expired_metadata_deadline_fails_even_if_no_query_was_interrupted(local_db, monkeypatch):
    original = sources._local_connection

    @contextmanager
    def expired(config):
        with original(config) as (connection, _):
            yield connection, monotonic() - 1

    monkeypatch.setattr(sources, '_local_connection', expired)
    with pytest.raises(ValueError, match='超时'):
        sources.inspect_database(local_db)
