"""Exact-match offline questions. This module never guesses a user's intent."""

from dataclasses import dataclass

import duckdb

from .analytics import validate_dates


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    kind: str
    metric: str = ''
    dimension: str = ''
    rules: tuple = ()
    definition: str = ''


AMOUNT = '已交付订单商品金额，不含运费，按购买日期归属；不是利润或财务收入。'
CUSTOMER = '使用 customer_unique_id 在当前筛选内独立去重；不累加月份或地区客户数。'
QUESTIONS = (
    Question('A01','完成订单商品金额是多少','data','amount',rules=('Q04',),definition=AMOUNT),
    Question('A02','完成订单数是多少','data','orders',definition='已交付源订单数，无明细订单仍计入。'),
    Question('A03','完成订单商品金额客单价是多少','data','aov',rules=('Q04',),definition=AMOUNT+'除以完成订单数；无订单返回空值。'),
    Question('A04','唯一购买客户数是多少','data','customers',rules=('Q06','Q16'),definition=CUSTOMER),
    Question('A05','复购买家数是多少','data','repeat_buyers',rules=('Q06','Q16'),definition='当前筛选内至少有两笔已交付订单的稳定客户数。'),
    Question('A06','复购买家占比是多少','data','repeat_rate',rules=('Q06','Q16'),definition='复购买家数除以唯一购买客户数，单位为百分比；无客户时为空。'),
    Question('T01','每月完成订单商品金额趋势','data','amount','month',('Q04',),AMOUNT+'边界月可能不完整，不据此断言完整月变化。'),
    Question('T02','每月完成订单数趋势','data','orders','month',definition='按购买月份统计已交付订单。'),
    Question('T03','每月商品金额客单价趋势','data','aov','month',('Q04',),AMOUNT+'按月分别计算客单价。'),
    Question('T04','每月唯一购买客户数趋势','data','customers','month',('Q06','Q16'),CUSTOMER),
    Question('T05','每月取消订单数趋势','data','canceled','month',definition='按购买月份及快照最终 canceled 状态统计；包含零取消月份。'),
    Question('D01','各地区完成订单商品金额排名','data','amount','region',('Q04','Q06'),AMOUNT+'未知地区单列；前十。'),
    Question('D02','各地区完成订单数排名','data','orders','region',('Q06',),'按已交付订单计数；未知地区单列；前十。'),
    Question('D03','各品类完成订单商品金额排名','data','amount','category',('Q04','Q05'),AMOUNT+'商品行粒度；未知品类单列；前十。'),
    Question('D04','各品类完成订单数排名','data','orders','category',('Q04','Q05'),'品类内订单去重；跨品类订单数不可相加；前十。'),
    Question('D05','商品完成订单商品金额前十','data','amount','product',('Q04','Q05'),AMOUNT+'商品行粒度；按商品 ID 聚合。'),
    Question('D06','各订单状态的订单数','data','orders','status',definition='包含取消和未交付订单，按快照最终状态统计。'),
    Question('Q01','本批次有多少条质量规则未通过','quality','failed_rules',definition='全批次失败规则条数，不是异常行数；不随筛选变化。'),
    Question('Q02','支付对账各状态的订单数','quality','orders','reconciliation',('Q18',),'含全部源订单状态；商品加运费与支付先按订单汇总，差额容差 0.01；孤儿支付另示警告。'),
    Question('Q03','有多少订单缺少商品明细','quality','missing_items',definition='所有订单状态中 item_count=0 的订单数；不擅自删除。'),
    Question('Q04','有多少订单缺少支付记录','quality','missing_payments',definition='所有订单状态中 payment_count=0 的订单数；差异不直接视为损失。'),
    Question('K01','商品金额的计算口径是什么','knowledge',definition=AMOUNT),
    Question('K02','购买客户数使用什么标识','knowledge',definition=CUSTOMER),
    Question('K03','订单按什么日期统计','knowledge',definition='按购买日期归属，并使用快照最终状态回看历史；边界月可能不完整。'),
    Question('K04','当前数据是什么币种和来源','knowledge',definition='以数据快照元信息为准；模拟数据不能解释为真实市场。'),
    Question('R01','净利润是多少','refusal',definition='缺少成本、费用、税费和利润口径，不能由商品金额推导净利润。'),
    Question('R02','预测下个月的销售额','refusal',definition='当前仅提供历史描述统计，没有经过验证的预测模型。'),
    Question('R03','列出客户姓名和手机号','refusal',definition='数据源不包含这些个人信息，当前问答也不提供身份明细。'),
    Question('R04','删除取消订单','refusal',definition='分析服务只读，不执行删除或其他源数据修改。'),
    Question('R05','销售下降一定是广告导致的吗','refusal',definition='缺少广告投放、实验与因果证据，不能从订单变化认定因果关系。'),
)


def resolve_question(text):
    if not isinstance(text, str) or len(text) > 500:
        return None
    normalized = text.strip().rstrip('？?。').strip()
    return next((q for q in QUESTIONS if normalized in (q.id, q.text)), None)


def validate_filters(snapshot, start=None, end=None, state=None):
    for value in (start,end):
        if value is not None and (not isinstance(value,str) or not value):
            raise ValueError('日期必须为 YYYY-MM-DD，不能使用空值代替筛选')
    validate_dates(start, end)
    if state is not None:
        if not isinstance(state, str) or len(state) > 50:
            raise ValueError('无效地区')
        if state != '__unknown__':
            with duckdb.connect(str(snapshot['directory']/'data.duckdb'), read_only=True) as con:
                if con.execute('SELECT count(*) FROM dwd_orders WHERE customer_state=?', [state]).fetchone()[0] == 0:
                    raise ValueError('请选择数据中存在的地区')


EXPRESSIONS = {
    'amount': 'CAST(sum(o.product_amount) AS DECIMAL(18,2))',
    'orders': 'count(*)',
    'aov': 'CAST(sum(o.product_amount)/nullif(count(*),0) AS DECIMAL(18,2))',
    'customers': 'count(DISTINCT o.customer_unique_id)',
    'canceled': "sum(CASE WHEN o.order_status='canceled' THEN 1 ELSE 0 END)",
    'missing_items': 'count(CASE WHEN o.item_count=0 THEN 1 END)',
    'missing_payments': 'count(CASE WHEN o.payment_count=0 THEN 1 END)',
}


def prepare_query(question, start=None, end=None, state=None):
    if question.kind in ('knowledge','refusal') or question.metric == 'failed_rules':
        return None, []
    all_status = question.kind == 'quality' or question.dimension == 'status' or question.metric == 'canceled'
    conditions = ['1=1'] if all_status else ["o.order_status='delivered'"]
    params = []
    for name, op, value in (('purchase_date','>=',start),('purchase_date','<=',end)):
        if value:
            conditions.append(f'o.{name}{op}CAST(? AS DATE)')
            params.append(value)
    if state == '__unknown__':
        conditions.append('o.customer_state IS NULL')
    elif state is not None:
        conditions.append('o.customer_state=?')
        params.append(state)
    where = ' WHERE ' + ' AND '.join(conditions)
    if question.metric in ('repeat_buyers','repeat_rate'):
        cte = 'WITH buyers AS (SELECT o.customer_unique_id, count(*) AS purchases FROM dwd_orders o' + where + ' AND o.customer_unique_id IS NOT NULL GROUP BY 1) '
        expression = ('count(CASE WHEN purchases>=2 THEN 1 END)' if question.metric == 'repeat_buyers' else
                      'CAST(100.0*sum(CASE WHEN purchases>=2 THEN 1 ELSE 0 END)/nullif(count(*),0) AS DECIMAL(18,2))')
        return cte + f'SELECT {expression} AS value FROM buyers', params
    expression = EXPRESSIONS[question.metric]
    source = ' FROM dwd_orders o'
    dimension = question.dimension
    if dimension in ('category','product'):
        source += ' JOIN dwd_order_items i ON o.order_id=i.order_id'
        label = ("coalesce(i.product_category_name, '未知品类')" if dimension == 'category' else "coalesce(i.product_id, '未知商品')")
        expression = ('CAST(sum(i.price) AS DECIMAL(18,2))' if question.metric == 'amount' else 'count(DISTINCT o.order_id)')
    else:
        label = {'month':"strftime(o.purchase_date, '%Y-%m')", 'region':"coalesce(o.customer_state, '未知地区')",
                 'status':'o.order_status','reconciliation':'o.reconciliation_status'}.get(dimension)
    if label:
        alias = 'month' if dimension == 'month' else 'dimension'
        order = '1' if dimension == 'month' else 'value DESC NULLS LAST, 1'
        limit = '' if dimension == 'month' else ' LIMIT 10'
        return f'SELECT {label} AS {alias}, {expression} AS value{source}{where} GROUP BY 1 ORDER BY {order}{limit}', params
    return f'SELECT {expression} AS value{source}{where}', params
