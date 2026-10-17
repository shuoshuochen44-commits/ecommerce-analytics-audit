# 第二周数据库与指标结果

## 本周范围

本周把五张 Olist CSV 重建为持久化 DuckDB，完成四项 V1 指标，并在订单粒度比较商品加运费金额与支付金额。数据库和报告均由同一条命令生成，可重复执行且不会追加重复记录。

## 数据库表

| 表 | 行数 | 粒度 | 业务键 |
|---|---:|---|---|
| raw_orders | 99,441 | 一个订单 | order_id |
| raw_order_items | 112,650 | 一条订单商品明细 | order_id + order_item_id |
| raw_customers | 99,441 | 一个订单客户映射 | customer_id |
| raw_products | 32,951 | 一个商品 | product_id |
| raw_payments | 103,886 | 一条订单支付记录 | order_id + payment_sequential |

数据库文件为 `data/zhishu.duckdb`。它由原始 CSV 重建并被 Git 忽略，源代码和测试不依赖提交该二进制文件。

## 四项指标

| 指标 | 字段名 | 结果 |
|---|---|---:|
| 完成订单商品金额 | `completed_product_amount` | 13,221,498.11 |
| 完成订单数 | `completed_order_count` | 96,478 |
| 完成订单商品金额客单价 | `completed_average_order_value` | 137.04 |
| 完成订单唯一购买客户数 | `completed_unique_customer_count` | 93,358 |

指标口径：

- 商品金额只包含已交付订单的商品 `price`，不含运费。
- 完成订单数按 `order_id` 去重。
- 客单价为已交付订单商品金额除以已交付订单数；分母为零时结果为空。
- 购买客户数使用 `customer_unique_id` 去重，不能用订单级 `customer_id` 代替。
- 这些分析指标不等同于企业财务收入或利润。

## 支付对账

商品金额加运费和支付金额先分别汇总到订单粒度，再做全连接。匹配容差为 0.01。

| 状态 | 订单数 |
|---|---:|
| matched | 98,362 |
| mismatch | 303 |
| missing_items | 775 |
| missing_payment | 1 |

303 笔金额不一致订单的绝对差额合计为 3,269.22，最大单笔绝对差额为 182.81。这些记录需要后续结合优惠、支付调整或数据缺失继续调查，当前不直接判定为错误。

775 笔有支付但没有商品明细的订单中，603 笔状态为 `unavailable`、164 笔为 `canceled`、5 笔为 `created`、2 笔为 `invoiced`、1 笔为 `shipped`。这表明缺失明细与订单状态存在明显联系，不应静默删除。

唯一一笔缺少支付的订单 ID 为 `bfbd0f9bdef84302105ad712db648a6c`，状态为 `delivered`，商品加运费金额为 143.46。后续质量规则应把它标记为需要核查。

## 小样本人工核对

| 检查项 | 预期结果 |
|---|---:|
| 完成订单商品金额 | 230.00 |
| 完成订单数 | 2 |
| 完成订单商品金额客单价 | 115.00 |
| 完成订单唯一购买客户数 | 1 |
| 支付匹配订单 | 3 |

小样本中 o1 的商品加运费为 165.00、支付为 165.00；o2 为 220.00；o3 为 88.00，三笔均匹配。

## 复现命令

```powershell
cd "C:\Users\32253\Documents\Codex\2026-10-17\ban"
.\.venv\Scripts\zhishu-week2.exe data/raw/olist data/zhishu.duckdb artifacts/week-02/real
```

结果文件为 `artifacts/week-02/real/summary.json` 和 `summary.md`。

## 已知限制与第三周入口

当前 `raw_*` 表按文本保留 CSV 字段，避免邮编前导零等信息丢失；金额在计算时显式转为两位小数。第三周将建立粒度明确、字段类型明确的明细层表，包括订单事实、订单商品事实、客户映射和订单支付汇总，并把支付对账异常保留为可追溯字段。

报告命令会同时生成异常差额、缺明细订单状态分布和缺支付订单清单，因此上述调查结果也可由同一条命令复现。客单价分母独立从订单表统计，包含已交付但无商品明细的订单。
