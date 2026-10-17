"""Small SQL dialect, statically authorized columns, bounded read-only execution."""

import math
from threading import Timer
from time import perf_counter as monotonic

import duckdb
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from .modeling import json_value


SCHEMA = {
    'dwd_orders': {name: 'UNKNOWN' for name in (
        'order_id', 'order_status', 'purchase_date', 'customer_state',
        'customer_unique_id', 'product_amount', 'freight_amount',
        'item_count', 'payment_count', 'payment_amount',
        'reconciliation_status', 'missing_customer')},
    'dwd_order_items': {name: 'UNKNOWN' for name in (
        'order_id', 'product_id', 'price', 'freight_value',
        'product_category_name', 'missing_order', 'missing_product')},
}

NODES = set('''select from table identifier column alias where and or not eq neq gt gte
lt lte is between in literal null boolean placeholder group order ordered limit distinct
sum count avg min max round coalesce nullif cast datatype datatypeparam star
add sub mul div paren with cte subquery tablealias join timetostr case if
neg having window windowspec lag lead'''.split())


def validate_join(join):
    """Only the declared order-to-item relationship can introduce a join."""
    select=join.find_ancestor(exp.Select)
    origin=select.args.get('from_') if select else None
    left=origin.this if origin else None
    right=join.this
    if (not isinstance(left,exp.Table) or not isinstance(right,exp.Table)
            or {left.name.lower(),right.name.lower()}!={'dwd_orders','dwd_order_items'}):
        raise ValueError('仅允许订单与商品明细的已声明关联')
    if join.args.get('using'):
        if [x.name.lower() for x in join.args['using']] != ['order_id']:
            raise ValueError('仅允许按 order_id 关联')
        return
    on=join.args.get('on')
    if (not isinstance(on,exp.EQ) or not isinstance(on.left,exp.Column)
            or not isinstance(on.right,exp.Column)
            or on.left.name.lower()!='order_id' or on.right.name.lower()!='order_id'
            or {on.left.table.lower(),on.right.table.lower()}!={left.alias_or_name.lower(),right.alias_or_name.lower()}
            or on.left.table.lower()==on.right.table.lower()):
        raise ValueError('仅允许不同表的 order_id 等值关联，不允许恒真或扩展条件')


def validate_sql(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 16000:
        raise ValueError('SQL 为空或超过长度限制')
    try:
        statements = sqlglot.parse(sql, read='duckdb')
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise ValueError('仅允许单条 SELECT 或非递归 CTE')
        tree = statements[0]
        nodes = list(tree.walk())
        if len(nodes) > 500:
            raise ValueError('查询结构超过预算')
        for node in nodes:
            if node.key not in NODES:
                raise ValueError(f'不允许的 SQL 结构：{node.key}')
            if isinstance(node, exp.With) and node.args.get('recursive'):
                raise ValueError('不允许递归查询')
            if isinstance(node, exp.CTE) and node.alias_or_name.lower() in SCHEMA:
                raise ValueError('CTE 不能遮蔽已授权的物理表名')
            if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
                raise ValueError('必须显式指定授权字段')
            if isinstance(node, exp.Table) and (node.db or node.catalog or not isinstance(node.this, exp.Identifier)):
                raise ValueError('不允许跨库、跨 Schema 或表函数')
            if isinstance(node, exp.Join) and (node.args.get('kind') == 'CROSS' or not (node.args.get('on') or node.args.get('using'))):
                raise ValueError('不允许笛卡尔积')
            if isinstance(node, exp.Join):
                validate_join(node)
        if len(list(tree.find_all(exp.Join))) > 1:
            raise ValueError('关联数量超过预算')
        sources = set()
        for scope in traverse_scope(tree):
            for _, source in scope.selected_sources.values():
                if isinstance(source, Scope):
                    continue
                name = source.name.lower()
                if name not in SCHEMA:
                    raise ValueError('查询包含未授权表')
                sources.add(name)
        if not sources:
            raise ValueError('查询必须引用授权数据表')
        qualified = qualify(tree, dialect='duckdb', schema=SCHEMA,
                            infer_schema=False, validate_qualify_columns=True)
        return qualified.sql(dialect='duckdb'), sources
    except (sqlglot.errors.SqlglotError, RecursionError) as error:
        raise ValueError('SQL 解析或表字段校验失败') from error


def execute_readonly(database_path, sql, parameters=(), *, max_rows=1000,
                     max_source_rows=1000000, timeout_seconds=5.0):
    if (not isinstance(max_rows, int) or not 1 <= max_rows <= 10000
            or not isinstance(max_source_rows, int) or max_source_rows < 1
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30):
        raise ValueError('无效执行预算')
    started = monotonic()
    safe_sql, sources = validate_sql(sql)
    remaining = timeout_seconds - (monotonic() - started)
    if remaining <= 0:
        raise ValueError('查询超时')
    # Match existing readers' connect-time configuration. These fixed SET operations
    # harden the shared DuckDB instance without incompatible concurrent open flags.
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        for setting in (
            'SET enable_external_access=false', 'SET autoinstall_known_extensions=false',
            'SET autoload_known_extensions=false', 'SET threads=1',
            "SET memory_limit='256MB'", 'SET max_expression_depth=100',
        ):
            connection.execute(setting)
    except duckdb.Error as error:
        connection.close()
        raise ValueError('无法应用安全执行配置') from error
    timer = Timer(max(0.000001, timeout_seconds - (monotonic() - started)), connection.interrupt)
    timer.daemon = True
    timer.start()
    try:
        source_rows = sum(connection.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in sources)
        if source_rows > max_source_rows:
            raise ValueError('参与源行数超过执行预算')
        cursor = connection.execute(safe_sql, parameters)
        names = [col[0] for col in cursor.description]
        values = cursor.fetchmany(max_rows + 1)
        if monotonic() - started >= timeout_seconds:
            raise ValueError('查询超时')
        if len(values) > max_rows:
            raise ValueError('结果行数超过限制，未返回部分答案')
        return [dict(zip(names, map(json_value, row))) for row in values]
    except duckdb.InterruptException as error:
        raise ValueError('查询超时') from error
    except duckdb.Error as error:
        raise ValueError('受限查询执行失败') from error
    finally:
        timer.cancel()
        timer.join()
        connection.close()
