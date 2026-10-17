"""Self-contained Chinese reports that open without a server or Markdown editor."""

from decimal import Decimal
from html import escape


def number(value, places=0):
    return "暂无数据" if value is None else f"{Decimal(str(value)):,.{places}f}"


def user_report(data):
    dataset, metrics, filters = data["dataset"], data["metrics"], data["filters"]
    currency = escape(dataset["currency_label"] + "（" + dataset["currency"] + "）")
    scope = escape(f"{filters['start'] or data['date_bounds']['min']} 至 {filters['end'] or data['date_bounds']['max']} · "
                   f"{('未知地区' if filters['state'] == '__unknown__' else filters['state']) or '全部地区'}")
    def table(records, key, title):
        body = "".join(f"<tr><td>{escape(str(row[key]))}</td><td>{number(row['product_amount'], 2)}</td></tr>" for row in records)
        return f"<h2>{title}</h2><table><thead><tr><th>名称</th><th>商品销售额（{currency}）</th></tr></thead><tbody>{body or '<tr><td colspan=2>当前范围暂无数据</td></tr>'}</tbody></table>"
    title = "模拟经营报告" if dataset["simulated"] else "经营分析报告"
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>智数 · {title}</title><style>body{{max-width:860px;margin:40px auto;padding:0 24px;font:16px/1.8 'Microsoft YaHei',sans-serif;color:#203c35}}h1{{color:#176b53}}.note{{background:#fff4de;padding:16px;border-radius:10px}}table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #dde6e0}}th{{background:#f3f7f4}}footer{{font-size:12px;color:#65776f;overflow-wrap:anywhere}}@media print{{body{{margin:0}}}}</style>
<h1>智数 · {title}</h1><p class="note">{escape(dataset['description'])}</p><p><strong>本报告范围：</strong>{scope}</p>
<p>金额单位：{currency}。按下单日期统计已完成交付的订单，商品销售额不含运费，不等于利润。</p>
<table><tr><th>指标</th><th>结果</th></tr>
<tr><td>商品销售额</td><td>{number(metrics['completed_product_amount'], 2)}</td></tr>
<tr><td>已完成订单</td><td>{number(metrics['completed_order_count'])} 单</td></tr>
<tr><td>平均每单金额</td><td>{number(metrics['completed_average_order_value'], 2)}</td></tr>
<tr><td>购买人数（同一买家只算一次）</td><td>{number(metrics['completed_unique_customer_count'])} 人</td></tr></table>
{table(data['monthly'], 'month', '每月销售额')}{table(data['regions'], 'state', '地区销售额')}{table(data['categories'], 'category', '商品分类销售额')}
<h2>数据检查说明</h2><p>全批次 {len(data['quality'])} 项检查中，{sum(not r['failed_count'] for r in data['quality'])} 项通过。检查结果覆盖整个数据集，不随本报告筛选变化。{'异常是人为设置的练习样例；' if dataset['simulated'] else ''}支付差异不等于损失。</p>
<p>客户数在当前范围重新统计，不可将各月份的人数直接相加。首尾月份可能未覆盖整月。</p>
<footer>数据版本：{escape(data['run_id'])}<br>数据指纹：{escape(data['input_fingerprint'])}</footer></html>"""
