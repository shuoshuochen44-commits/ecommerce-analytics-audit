"""Offline HTML presentation of saved anomaly or quality-blocked evidence."""

import html
import json
from typing import Any


METRIC_LABELS = {'completed_product_amount': '每日商品销售额', 'completed_order_count': '每日完成订单数',
                 'order_product_amount': '单笔订单商品金额'}


def render_anomaly_html(report: dict[str, Any]) -> str:
    escape = lambda value: html.escape(str(value if value is not None else '暂无'), quote=True)
    blocked = report.get('status') == 'BLOCKED_QUALITY'
    alerts = [row for row in report.get('results', []) if row.get('status') == 'ALERT']
    rows = []
    for row in alerts:
        evidence = escape(json.dumps(row.get('evidence', {}), ensure_ascii=False, indent=2, allow_nan=False))
        rows.append('<tr><td>' + escape(METRIC_LABELS.get(row['metric'], row['metric'])) + '</td><td>'
                    + escape(row['observed_at']) + '</td><td>' + escape(row['actual_value']) + '</td><td>'
                    + escape(row.get('baseline_value')) + '</td><td>' + escape(row['explanation_zh'])
                    + '<details><summary>规则与定位证据</summary><p>' + escape(row['rule_id']) + ' / '
                    + escape(row['rule_version']) + '</p><pre>' + evidence + '</pre></details></td></tr>')
    issues = ''.join('<tr><td>' + escape(i.get('row_number')) + '</td><td>' + escape(i.get('target_field'))
                     + '</td><td>' + escape(i.get('reason')) + '</td><td>' + escape(i.get('suggestion'))
                     + ('；相关行：' + escape(i['related_rows']) if 'related_rows' in i else '') + '</td></tr>'
                     for i in report.get('quality_issues', []))
    quality = ''.join('<li>' + escape(q['rule_id']) + ' ' + escape(q['label']) + '：失败 '
                      + escape(q['failed_count']) + '，覆盖整个快照</li>' for q in report.get('quality_evidence', []))
    limitations = ''.join('<li>' + escape(value) + '</li>' for value in report.get('limitations', []))
    summary = ('输入质量未通过，未运行统计检测' if blocked else
               '发现 ' + str(report.get('alert_count', 0)) + ' 条规则告警')
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
            '<title>智数巡检 · 异常检测报告</title><style>'
            'body{font:15px/1.7 system-ui,sans-serif;background:#f4f7f2;color:#183e32;margin:0;padding:32px}'
            'main{max-width:1150px;margin:auto}section{background:white;border:1px solid #dce6dd;border-radius:14px;padding:24px;margin:20px 0}'
            'h1{font-size:28px}h2{font-size:19px}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #e3e9e1}'
            'th{white-space:nowrap}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f7f2;padding:12px}dd{overflow-wrap:anywhere}'
            '.muted{color:#5b7468}.table{overflow:auto}summary{cursor:pointer;color:#17694c}</style></head><body><main>'
            '<h1>智数巡检 · 异常检测报告</h1><p>' + escape(summary) + '</p><p class="muted">'
            + ('输入行数' if blocked else '当前范围完成订单样本') + '：' + escape(report.get('sample_size'))
            + '；不同规则可指向同一天或订单，告警条数不是异常订单去重数。</p><section><h2>检测范围与版本</h2><dl>'
            + ''.join('<dt>' + label + '</dt><dd>' + escape(value) + '</dd>' for label, value in (
                ('数据版本', report.get('snapshot_id')), ('来源指纹', report.get('source_fingerprint')),
                ('运行编号', report.get('run_id')), ('币种', report.get('currency')),
                ('筛选', json.dumps(report.get('filters', {}), ensure_ascii=False))))
            + '</dl></section><section><h2>统计告警</h2><div class="table"><table><thead><tr><th>指标</th><th>发生日期</th><th>实际值</th><th>历史中位数</th><th>解释与证据</th></tr></thead><tbody>'
            + (''.join(rows) or '<tr><td colspan="5">' + ('未运行统计检测' if blocked else '当前规则没有检出告警；历史不足等状态请查看 JSON 记录') + '</td></tr>')
            + '</tbody></table></div></section>'
            + ('<section><h2>输入质量问题</h2><table><thead><tr><th>行号</th><th>字段</th><th>原因</th><th>建议</th></tr></thead><tbody>'
               + issues + '</tbody></table><p>问题总数：' + escape(report.get('quality_issue_count'))
               + ('；只展示前 50 项' if report.get('issues_truncated') else '') + '</p></section>' if blocked else '')
            + ('<section><h2>已有质量检查证据</h2><ul>' + quality + '</ul></section>' if quality else '')
            + '<section><h2>方法与限制</h2><pre>' + escape(json.dumps(report.get('config', {}), ensure_ascii=False, indent=2))
            + '</pre><ul>' + limitations + '</ul></section></main></body></html>')
