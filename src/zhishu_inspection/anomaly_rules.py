"""Pure, past-only rules for integer counts and high order amounts."""

import hashlib
import json
from collections import deque
from datetime import date
from decimal import Decimal
from itertools import groupby
from statistics import median
from typing import Any

from .anomaly_models import AnomalySuiteConfig


def _score(actual: Decimal, baseline: Decimal, radius: Decimal) -> dict[str, str]:
    return {'kind': 'deviation_over_threshold',
            'value': format((abs(actual - baseline) / radius).quantize(Decimal('0.0001')), 'f')}


def evaluate_count(point: dict, history: list[dict], config: AnomalySuiteConfig,
                   limitations: list[str]) -> dict[str, Any]:
    values = [Decimal(p['order_count']) for p in history]
    actual = Decimal(point['order_count'])
    result = {
        'rule_id': 'A_COUNT_DAILY_MAD', 'rule_version': '1.0',
        'entity_type': 'purchase_date', 'entity_key': point['day'], 'observed_at': point['day'],
        'metric': 'completed_order_count', 'actual_value': point['order_count'],
        'baseline_value': None, 'threshold': None, 'severity': 'info', 'direction': None,
        'confidence_or_score': None, 'sample_size': len(values), 'status': 'INSUFFICIENT_HISTORY',
        'evidence': {'history_start': history[0]['day'] if history else None,
                     'history_end': history[-1]['day'] if history else None,
                     'history': [{'date': p['day'], 'order_count': p['order_count']} for p in history]},
        'explanation_zh': f'有记录的历史日期 {len(values)} 个，至少需要 {config.sales.min_history} 个。',
        'limitations': list(limitations),
    }
    if len(values) < config.sales.min_history:
        return result
    baseline = median(values)
    result['baseline_value'] = format(baseline, 'f')
    if baseline == 0:
        result.update(status='INSUFFICIENT_ACTIVITY', explanation_zh='历史完成订单数中位数为零，稀疏交易暂不武断报警。')
        return result
    mad = median([abs(value - baseline) for value in values])
    radius = max(config.sales.mad_multiplier * mad, config.sales.relative_floor * baseline,
                 Decimal(config.count_absolute_floor))
    lower, upper = max(Decimal(0), baseline - radius), baseline + radius
    alert = actual < lower or actual > upper
    result.update(status='ALERT' if alert else 'NORMAL', severity='warning' if alert else 'info',
                  direction=('high' if actual > upper else 'low') if alert else None,
                  threshold={'lower': format(lower, 'f'), 'upper': format(upper, 'f'), 'radius': format(radius, 'f')},
                  confidence_or_score=_score(actual, baseline, radius),
                  explanation_zh=f'当日完成订单 {point["order_count"]} 单，历史中位数 {baseline}、MAD {mad}；'
                                 f'允许区间 [{lower}, {upper}]，使用独立的 {config.count_absolute_floor} 单绝对底线。'
                                 + ('超出阈值，建议核查交易与采集情况。' if alert else '未超出阈值。'))
    result['evidence']['mad'] = format(mad, 'f')
    return result


def evaluate_order_amounts(orders: list[dict], config: AnomalySuiteConfig, fingerprint: str,
                           start: str | None, limitations: list[str]) -> list[dict[str, Any]]:
    history: deque[dict] = deque()
    results: list[dict[str, Any]] = []
    ordinal = 0
    for day, group in groupby(orders, key=lambda row: row['day']):
        current = list(group)
        cutoff = max(1, date.fromisoformat(day).toordinal() - config.sales.window_days)
        while history and date.fromisoformat(history[0]['day']).toordinal() < cutoff:
            history.popleft()
        valid = [Decimal(row['amount']) for row in history if row['amount'] is not None]
        baseline = median(valid) if valid else None
        mad = median([abs(value - baseline) for value in valid]) if valid else None
        history_digest = hashlib.sha256(json.dumps(
            [(row['day'], row['amount']) for row in history], separators=(',', ':')).encode()).hexdigest()
        for order in current:
            ordinal += 1
            if start and day < start:
                continue
            key_hash = hashlib.sha256((fingerprint + ':' + order['order_id']).encode('utf-8')).hexdigest()
            result = {
                'rule_id': 'A_ORDER_AMOUNT_MAD', 'rule_version': '1.0',
                'entity_type': 'order_fingerprint', 'entity_key': key_hash[:24], 'observed_at': day,
                'metric': 'order_product_amount', 'actual_value': order['amount'],
                'baseline_value': format(baseline, 'f') if baseline is not None else None,
                'threshold': None, 'severity': 'info', 'direction': None,
                'confidence_or_score': None, 'sample_size': len(valid), 'status': 'INSUFFICIENT_HISTORY',
                'evidence': {'history_start': history[0]['day'] if history else None,
                             'history_end': history[-1]['day'] if history else None,
                             'baseline_inputs_sha256': history_digest,
                             'locator': {'table': 'scoped_completed_orders', 'sort': ['purchase_date', 'order_id'],
                                         'selected_input_row': ordinal, 'order_key_sha256': key_hash}},
                'explanation_zh': f'当前订单商品金额 {order["amount"]}；此前日期有 {len(valid)} 笔完整订单，'
                                  f'至少需要 {config.min_order_history} 笔。',
                'limitations': list(limitations) + ['单笔只检查极高金额，不把合法零金额视为异常；同日订单不参与彼此的历史基线。',
                    '定位行号相对于本报告相同筛选及回看窗口的订单输入，按购买日期和订单号排序；编号仅保存盐化指纹。'],
            }
            if order['amount'] is None:
                result.update(status='INCOMPLETE_DATA', explanation_zh='订单缺少完整商品金额，属于数据覆盖问题，不计为统计异常。')
            elif len(valid) >= config.min_order_history and baseline == 0:
                result.update(status='INSUFFICIENT_ACTIVITY', explanation_zh='历史单笔金额中位数为零，缺少稳定金额基线，暂不报警。')
            elif len(valid) >= config.min_order_history:
                radius = max(config.order_mad_multiplier * mad, config.order_relative_floor * baseline,
                             config.sales.absolute_floor)
                upper = baseline + radius
                actual = Decimal(order['amount'])
                alert = actual > upper
                result.update(status='ALERT' if alert else 'NORMAL', severity='warning' if alert else 'info',
                    direction='high' if alert else None,
                    threshold={'lower': '0.00', 'upper': format(upper, 'f'), 'radius': format(radius, 'f')},
                    confidence_or_score=_score(actual, baseline, radius),
                    explanation_zh=f'订单商品金额 {order["amount"]}，此前 {len(valid)} 笔订单的中位数 {baseline}、MAD {mad}；'
                                   f'极高金额上界 {upper}。' + ('超出上界，需核对原订单；不认定欺诈或损失。' if alert else '未超出上界。'))
                result['evidence']['mad'] = format(mad, 'f')
            results.append(result)
        # Publish today's values to the rolling history only after scoring all peers.
        history.extend(current)
    return results
