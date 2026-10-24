"""Explain daily sales changes using past-only, successful snapshot evidence."""

import hashlib
import json
import re
import threading
import uuid
from datetime import date, datetime, timezone
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from statistics import median
from typing import Any

from .anomaly_models import AnomalyConfig, AnomalySuiteConfig
from .anomaly_inputs import read_scoped_orders
from .anomaly_rules import evaluate_count, evaluate_order_amounts
from .anomaly_filters import validate_category_filter
from .pipeline import load_snapshot
from .query_gateway import execute_readonly
from .question_catalog import validate_filters


RULE_ID = 'A_SALES_DAILY_MAD'
RULE_VERSION = '1.0'
SCHEMA_VERSION = '1.0'
MAX_EVIDENCE_POINTS = 100000
_SNAPSHOT_READ_LOCK = threading.RLock()
LIMITATIONS = [
    '描述统计规则，不是异常概率、因果解释或财务损失认定；尚未校正星期、节假日与促销季节性。',
    '使用快照最终已完成状态回看购买日期；不推断净收入、退款或数据完整性。',
    '无源订单的日期不补零；历史中位数为零时视为缺少稳定交易历史，不武断报警。',
    '日期按源购买日历日期处理，不进行时区换算；历史窗口可早于待检测的开始日期。',
]


def _digest(value: Any) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _daily_series(snapshot: dict, config: AnomalyConfig, start: str | None,
                  end: str | None, state: str | None, category: str | None) -> list[dict]:
    database = snapshot['directory'] / 'data.duckdb'
    conditions, parameters = ['1=1'], []
    if start:
        # Clamp at date.min instead of overflowing on valid boundary dates.
        earliest = date.fromordinal(max(1, date.fromisoformat(start).toordinal() - config.window_days))
        conditions.append('o.purchase_date>=CAST(? AS DATE)')
        parameters.append(earliest.isoformat())
    if end:
        conditions.append('o.purchase_date<=CAST(? AS DATE)')
        parameters.append(end)
    if state == '__unknown__':
        conditions.append('o.customer_state IS NULL')
    elif state is not None:
        conditions.append('o.customer_state=?')
        parameters.append(state)
    source, amount = 'dwd_orders o', 'o.product_amount'
    if category is not None:
        validate_category_filter(category)
        present = execute_readonly(database,
            "SELECT count(*) AS value FROM dwd_order_items i WHERE coalesce(i.product_category_name, '未知品类')=?",
            [category])[0]['value']
        if not present:
            raise ValueError('请选择数据中存在的品类')
        source += ' JOIN dwd_order_items i ON o.order_id=i.order_id'
        amount = 'i.price'
        conditions.append("coalesce(i.product_category_name, '未知品类')=?")
        parameters.append(category)
    sql = (
        "SELECT o.purchase_date AS day, "
        f"CAST(sum(CASE WHEN o.order_status='delivered' THEN {amount} ELSE 0 END) AS DECIMAL(18,2)) AS amount, "
        "count(DISTINCT CASE WHEN o.order_status='delivered' THEN o.order_id END) AS order_count, "
        f"count(CASE WHEN o.order_status='delivered' AND {amount} IS NULL THEN 1 END) AS missing_amounts "
        f"FROM {source} WHERE {' AND '.join(conditions)} GROUP BY 1 ORDER BY 1"
    )
    series = execute_readonly(database, sql, parameters, max_rows=10000)
    for point in series:
        point['day'] = point['day'].isoformat()
        # A partial sum is not a complete sales value, even when SQL SUM returns one.
        if point['missing_amounts']:
            point['amount'] = None
    return series


def _evaluate(point: dict, history: list[dict], config: AnomalyConfig) -> dict:
    complete = [Decimal(p['amount']) for p in history if p['amount'] is not None]
    result = {
        'entity_type': 'purchase_date', 'entity_key': point['day'], 'observed_at': point['day'],
        'metric': 'completed_product_amount', 'actual_value': point['amount'],
        'baseline_value': None, 'threshold': None, 'severity': 'info', 'direction': None,
        'confidence_or_score': None, 'sample_size': len(complete), 'status': 'INSUFFICIENT_HISTORY',
        'evidence': {
            'history_start': history[0]['day'] if history else None,
            'history_end': history[-1]['day'] if history else None,
            'history': [{'date': p['day'], 'amount': p['amount'], 'order_count': p['order_count']} for p in history],
            'observed_order_count': point['order_count'], 'missing_amounts': point['missing_amounts'],
        },
        'explanation_zh': f'完整历史日期 {len(complete)} 个，至少需要 {config.min_history} 个，暂不判断异常。',
        'limitations': list(LIMITATIONS),
    }
    if point['amount'] is None or any(p['amount'] is None for p in history):
        result.update(status='INCOMPLETE_DATA', explanation_zh='当前日期或历史窗口缺少完整商品金额，不能把缺失值当作零或正常销售。')
        return result
    if len(complete) < config.min_history:
        return result
    baseline = median(complete)
    result['baseline_value'] = format(baseline, 'f')
    if baseline == 0:
        result.update(status='INSUFFICIENT_ACTIVITY', explanation_zh='历史销售额中位数为零，缺少稳定交易历史，暂不使用该统计阈值报警。')
        return result
    mad = median([abs(value - baseline) for value in complete])
    radius = max(config.mad_multiplier * mad, config.relative_floor * baseline, config.absolute_floor)
    lower, upper = max(Decimal('0.00'), baseline - radius), baseline + radius
    actual = Decimal(point['amount'])
    alert = actual < lower or actual > upper
    score = abs(actual - baseline) / radius
    result.update(
        threshold={'lower': format(lower, 'f'), 'upper': format(upper, 'f'), 'radius': format(radius, 'f')},
        confidence_or_score={'kind': 'deviation_over_threshold', 'value': format(score.quantize(Decimal('0.0001')), 'f')},
        status='ALERT' if alert else 'NORMAL', severity='warning' if alert else 'info',
        direction=('high' if actual > upper else 'low') if alert else None,
        explanation_zh=(f'当日完成订单商品金额 {point["amount"]}，此前 {len(complete)} 个完整日期的中位数 '
                        f'{baseline}、MAD {mad}；阈值区间 [{lower}, {upper}]。'
                        + ('超出阈值，建议核查订单与业务活动；该结果不认定原因。' if alert else '未超出配置的阈值。')),
    )
    result['evidence']['mad'] = format(mad, 'f')
    return result


def detect_anomalies(output_root: Path | str, *, snapshot_run_id: str | None = None,
                     start: str | None = None, end: str | None = None,
                     state: str | None = None, category: str | None = None,
                     config: AnomalyConfig | AnomalySuiteConfig | None = None,
                     rules: str = 'sales') -> dict[str, Any]:
    """Detect daily sales changes; persist a new record without modifying snapshots.

    Date filters select scored dates; each date may use up to window_days of
    earlier data with the same region/category filters. Missing dates stay missing.
    """
    if rules not in ('sales', 'all'):
        raise ValueError('rules 仅支持 sales 或 all')
    suite_config = None
    if rules == 'all':
        suite_config = (config if isinstance(config, AnomalySuiteConfig)
                        else AnomalySuiteConfig(sales=AnomalyConfig() if config is None else config))
        config = suite_config.sales
    config = AnomalyConfig() if config is None else config
    if not isinstance(config, AnomalyConfig):
        raise ValueError('config 必须是 AnomalyConfig')
    snapshot = load_snapshot(output_root, run_id=snapshot_run_id)
    if any(r['blocking'] and r['failed_count'] for r in snapshot['quality']):
        raise ValueError('该快照存在阻断质量错误，不执行统计异常检测')
    # The existing analysis service also admits one analysis query at a time.
    # Concurrent connection teardown in Windows/DuckDB 1.5.6 caused a native
    # access violation in the new API's stress test; serialize its engine phase.
    # Decimal evaluation and exclusive record writes remain independent.
    with _SNAPSHOT_READ_LOCK:
        validate_filters(snapshot, start=start, end=end, state=state)
        series = _daily_series(snapshot, config, start, end, state, category)
        orders = (read_scoped_orders(snapshot['directory'] / 'data.duckdb', config, start, end, state, category)
                  if suite_config else [])
    filters = {'start': start, 'end': end, 'state': state, 'category': category}
    common = {'rule_id': RULE_ID, 'rule_version': RULE_VERSION, 'snapshot_id': snapshot['run_id'],
              'source_fingerprint': snapshot['manifest']['input_fingerprint'], 'filters': filters}
    results, order_count, observed_dates, evidence_points = [], 0, 0, 0
    # Decimal context is local so concurrent callers and application defaults cannot
    # change thresholds. Current DECIMAL(18,2) source budgets fit this precision.
    with localcontext(Context(prec=38, rounding=ROUND_HALF_UP)):
        for index, point in enumerate(series):
            if start and point['day'] < start:
                continue
            cutoff = max(1, date.fromisoformat(point['day']).toordinal() - config.window_days)
            # One aggregate per calendar date: the window contains at most this
            # many rows, even when the source has a long, sparse history.
            history = [p for p in series[max(0, index - config.window_days):index]
                       if date.fromisoformat(p['day']).toordinal() >= cutoff]
            evidence_points += len(history) * (2 if suite_config else 1)
            if evidence_points > MAX_EVIDENCE_POINTS:
                raise ValueError('聚合历史证据超过 100,000 点预算，请缩小日期范围或历史窗口；未保存部分结果')
            results.append({**common, **_evaluate(point, history, config)})
            if suite_config:
                results.append({**common, **evaluate_count(point, history, suite_config, LIMITATIONS)})
            order_count += point['order_count']
            observed_dates += 1
        if suite_config:
            results.extend({**common, **row} for row in evaluate_order_amounts(
                orders, suite_config, common['source_fingerprint'], start, LIMITATIONS))
    report = {
        'schema_version': SCHEMA_VERSION, **common, 'config': config.to_dict(),
        'currency': snapshot['manifest']['dataset']['currency'],
        'status': 'COMPLETED' if results else 'NO_DATA',
        'sample_size': order_count, 'observed_dates': observed_dates,
        'alert_count': sum(r['status'] == 'ALERT' for r in results), 'results': results,
        'limitations': list(LIMITATIONS),
    }
    if suite_config:
        report.update(schema_version='1.1', rule_id='ANOMALY_SUITE', config=suite_config.to_dict(),
                      rules=[RULE_ID, 'A_COUNT_DAILY_MAD', 'A_ORDER_AMOUNT_MAD'],
                      quality_evidence=[{'rule_id': q['rule_id'], 'rule_version': q['version'],
                                         'label': q['label'], 'failed_count': q['failed_count'],
                                         'status': q['status'], 'scope': 'full_snapshot'}
                                        for q in snapshot['quality'] if q['rule_id'] in ('Q01','Q02','Q07','Q08','Q09','Q10','Q14')])
    # Mathematical results are stable; invocation identity and time intentionally vary.
    report['result_fingerprint'] = _digest(report)
    report['run_id'] = 'anomaly_' + uuid.uuid4().hex
    report['created_at'] = datetime.now(timezone.utc).isoformat()
    for result in results:
        result['run_id'] = report['run_id']
    report['record_sha256'] = _digest(report)
    directory = Path(output_root) / 'anomaly_runs'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / f"{report['run_id']}.json").open('x', encoding='utf-8') as target:
        json.dump(report, target, ensure_ascii=False, indent=2, allow_nan=False)
    return report


def get_anomaly_run(output_root: Path | str, run_id: str) -> dict[str, Any]:
    """Read one saved record, checking its identity and accidental-corruption hash."""
    if not isinstance(run_id, str) or not re.fullmatch(r'anomaly_[0-9a-f]{32}', run_id):
        raise ValueError('无效异常检测运行 ID')
    result = json.loads((Path(output_root) / 'anomaly_runs' / f'{run_id}.json').read_text(encoding='utf-8'))
    if not isinstance(result, dict):
        raise ValueError('异常检测记录完整性校验失败')
    recorded = result.pop('record_sha256', None)
    if result.get('run_id') != run_id or recorded != _digest(result):
        raise ValueError('异常检测记录完整性校验失败')
    result['record_sha256'] = recorded
    return result
