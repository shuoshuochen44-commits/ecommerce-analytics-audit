# 智数：电商经营分析与数据质量监控

本分支新增 **离线可审计问答内核**：30 条精确匹配的中文问题（21 条数据/质量计算、4 条口径说明、5 条明确拒答），保留实际 SQL、绑定参数、原始层独立核验、质量提示和可重放运行记录。此功能通过命令行使用，尚未接入看板或大模型。详见 [使用与安全边界](docs/auditable-analysis.md)。

```powershell
# 完成下文“新环境复现”中的安装后执行
.\.venv\Scripts\python.exe scripts/verify_analysis.py --fixture-gold
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli --list
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli artifacts/analysis-acceptance "完成订单商品金额是多少"
```

以上验收仅使用仓库内自造小样本，产生本地模板工程验收报告，不代表模型或论文实验结果。

默认打开中国大陆模拟经营演示版：31 个省级地区、8 个中文商品分类、人民币金额，页面和报告明确标注模拟数据。适合零基础用户直接查看经营结果。底层支持导入、明细建模、18 条质量检查、经营筛选、对账、来源证据和失败恢复。

## 立即使用

Windows 已有本地环境时，双击 **打开智数看板.cmd**。首次自动生成数据、检查并打开浏览器；以后直接打开。使用期间保持启动窗口开启。也可访问 [本地看板](http://127.0.0.1:8765)。无需注册账号或操作数据库。

1. 首页自动显示全部经营结果。
2. 选择月份或省份，结果自动更新；点击“恢复全部”回到初始状态。
3. 点击“保存当前报告”下载 HTML 文件，双击即可阅读，也可通过浏览器打印成 PDF。

页面内有“使用说明”和“数据检查”。下载报告固定使用当前页面的数据版本和筛选范围；技术检查报告覆盖全批次。

## 新增实用功能

- **导入自己的订单表格**：点击“导入数据”，下载九列中文 CSV 模板。删除示例行后填写订单，Excel 另存为 CSV UTF-8。每行一笔完整订单、一个汇总商品分类；人民币、非负且最多两位小数。支持 31 个省级地区全称和四种中文订单状态。先检查预览，确认后才保存。上限 5 MB、20,000 笔，支持 UTF-8/GB18030。
- **查询和导出订单**：点击“查订单”，按订单号或买家编号片段、状态查询。继承当前经营页的月份和地区，每页 20 笔；包含取消和未交付订单。修改条件后需重新查询；导出当前查询的全部结果，最多 20,000 笔。CSV 文本已处理公式前缀，Excel 可直接打开。
- **完整月份环比**：选择一个月即可比较四项指标与上月的变化。两个月都在源数据日期覆盖范围内才计算，同一地区筛选下重新统计人数；零基数不显示百分比，日期覆盖不保证交易全量。
- **切换数据来源**：页面上方可在演示数据和“我的导入数据”之间切换。导入按整表生成新快照，旧版本保留，原演示快照不变；订单查询、导出与报告固定到当前显示版本。

用户导入数据存放于默认输出目录的 `customer-data/`，原表随哈希保留为 source.csv。表格来源及准确性由提供者确认。模板没有真实交付日期，保持空值并显示检查提示；不推断物流时效。多商品订单应先汇总，退款口径需另外确认。本版尚未实现 MySQL 直接连接和任意 Excel 表结构解析。

演示数据独立生成，覆盖 2026 年 1—9 月，共 12,000 笔订单；买家、订单和交易全部虚构。金额从人民币分直接生成，不是汇率换算；31 个地区的分布与排名不代表真实市场。包含少量人为设置的异常练习样例。原始演示文件存放在 `data/raw/china_demo/`，独立发布在 `artifacts/china-demo/`。生成器拒绝覆盖已有目录。

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.launcher
```

## 保留的 Olist 真实历史数据版本

原始巴西数据及其成果仍独立保留，币种仍是 BRL。需要运行这个版本时，在另一个端口启动：

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.pipeline data/raw/olist artifacts/analytics
.\.venv\Scripts\python.exe -m zhishu_inspection.server artifacts/analytics --port 8766
```

服务仅接受本机访问。Ctrl+C 停止服务。重新导入时可在另一个终端运行加工命令；网页更改筛选或点击“恢复全部”后读取新成功批次。

## 新环境复现

需要 Python 3.11 或更高版本和当前源码目录。以下固定经过验证的直接依赖版本，采用 editable 安装，运行时保留源码和根目录 sql/。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pytest
```

国内模拟版无需下载外部数据；环境安装后直接运行 launcher。需要复现原始巴西历史版时，从 [Olist 发布页](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 获取数据，解压这五个文件到 `data/raw/olist/`：

- olist_orders_dataset.csv
- olist_order_items_dataset.csv
- olist_customers_dataset.csv
- olist_products_dataset.csv
- olist_order_payments_dataset.csv

原始数据未纳入 Git。来源与许可核对记录见 docs/week-01-data-discovery.md。无法下载时，可用已提交的自造样本演示：

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.pipeline tests/fixtures/olist_mini artifacts/demo
.\.venv\Scripts\python.exe -m zhishu_inspection.server artifacts/demo --port 8766
```

## 四项经营指标

| 指标 | 当前 Olist 基线 |
|---|---:|
| 已交付订单商品金额（BRL，不含运费） | 13,221,498.11 |
| 完成订单数 | 96,478 |
| 商品金额客单价（BRL） | 137.04 |
| 唯一购买客户数 | 93,358 |

统一按购买日期归属、使用快照最终状态；客户数用 customer_unique_id 独立去重。原始层与明细层每批逐项核对。金额不是财务收入或利润。

## 数据链路与证据

```text
CSV → raw_* → 质量检查 → dim_* / dwd_* → dws_daily_state / ads_overview
                                     ↓
                            独立指标核对与输入哈希
                                     ↓
                            完整批次原子发布
                                     ↓
                          中文看板 / 运行报告 / 清单
```

每次运行保存独立 run_id。各输出目录的 `latest.json` 只指向成功批次；批次目录保留 data.duckdb、manifest.json、quality.json、summary.json 和 report.md。错误批次不替换旧结果。国内模拟版的 dataset.json 也参与输入哈希，来源、模拟标记和币种进入清单、API 与报告。所有生成数据均被 Git 忽略。

数据模型、字段粒度、质量策略和指标口径见 [数据模型文档](docs/data-model.md)。页面中的质量结果与技术报告覆盖全批次；“保存当前报告”的经营指标、趋势和排名跟随筛选。边界月份可能不完整，不能直接解读为完整月环比。

## 实测验收与分析简报

```powershell
.\.venv\Scripts\python.exe scripts/verify_demo.py data/raw/olist artifacts/analytics outputs
```

此命令完整重建两次，核对输入指纹、四项指标、模型行数和规则结果的一致性，核对日期/州/品类金额之和与总体相符，并以独立原始层 SQL 核对 SP 州 2018 年 1 月筛选。生成 outputs/ 中的验收 JSON、经营分析简报与质量运行报告。人为异常注入、快照更新和失败恢复见 tests/，使用临时目录，不修改真实源数据。

## 工程边界

这是本地单用户的模拟经营/历史数据分析版本。固定模板只读查询之外，增加了本机同源的 CSV 预览与确认导入。其他业务表结构仍需先映射字段，不支持实时采集或增量更新。每次全量重建生成新目录，需要保留磁盘空间。这里只固定已验证的直接依赖；尚未提供完整跨平台依赖锁或容器镜像。

早期 profile、build-db 和 week2 命令仍可使用；开发工作现按可用里程碑持续推进。
