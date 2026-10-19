# 智数：电商经营分析与数据质量监控

本分支新增 **离线可审计问答内核**：30 条精确匹配的中文问题（21 条数据/质量计算、4 条口径说明、5 条明确拒答），保留实际 SQL、绑定参数、原始层独立核验、质量提示和可重放运行记录。此功能通过命令行使用，尚未接入看板或大模型。详见 [使用与安全边界](docs/auditable-analysis.md)。

```powershell
# 完成下文“新环境复现”中的安装后执行
.\.venv\Scripts\python.exe scripts/verify_analysis.py --fixture-gold
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli --list
.\.venv\Scripts\python.exe -m zhishu_inspection.analysis_cli artifacts/analysis-acceptance "完成订单商品金额是多少"
```

以上验收仅使用仓库内自造小样本，产生本地模板工程验收报告，不代表模型或论文实验结果。

当前版本启动为空工作区，由用户导入文件或连接数据库后生成经营结果；页面不预置经营数据，也不显示演示/模拟提示。底层保留明细建模、18 条质量检查、经营筛选、对账、来源证据和失败恢复。

## 立即使用

桌面交付位置为 `C:\Users\32253\Desktop\智数巡检`：目录内放置 Windows exe 与五份可独立导入的订单文件。双击 exe 直接打开独立桌面窗口，不启动外部浏览器；关闭窗口退出后台，重复启动恢复已有窗口。已导入的数据继续保留，首次使用仍为空工作区。在“数据接入”中选择文件或数据库，不需要安装 Python。本机已具备系统 Edge WebView2 运行时；换电脑使用时需具备该运行时。

开发环境安装桌面依赖后运行 `python -m zhishu_inspection.desktop`。原有 **打开智数看板.cmd** 与 launcher 保留为浏览器兼容入口，默认尝试本机 8765—8774 端口；桌面版使用独立的随机本机端口。

1. 首次打开进入空工作区，在“数据接入”选择上传文件、监测本机文件或连接数据库。
2. 选择表/工作表，核对预览，确认九个业务字段与“每行一笔完整订单、人民币金额”的口径，再导入。
3. 成功后选择月份或省份查看结果，查询/导出订单，或保存当前筛选下的 HTML 报告。

页面内有“使用说明”和“数据检查”。下载报告固定使用当前页面的数据版本和筛选范围；技术检查报告覆盖全批次。

## 数据接入与使用

- **文件与字段映射**：支持 CSV/TSV/分隔 TXT、XLSX/BIFF8 XLS/XLSB/ODS、平面 JSON/JSONL/NDJSON、Parquet、SQLite/DuckDB 文件。工作表/物理表可预览，已知中英文字段名提供保守建议，仍需确认全部九个字段。上传源文件上限 20 MB，展开后的表格也受 20 MB 字节预算约束；最多 20,000 行、200 列，超限直接拒绝。转换后的九列订单 CSV 仍受既有 5 MB 上限约束。
- **数据库与刷新**：SQLite、DuckDB 已做真实本地读表与变化回归。MySQL/MariaDB、PostgreSQL、SQL Server、Oracle 的驱动已纳入打包，尚未连接真实服务验收。可手动刷新、设置 10—3600 秒定时采集，或以 1—30 秒轮询监测本机文件/选定数据库表，再通过 SSE 更新页面。这是全量快照采集，不是日志 CDC；未测量通用端到端延迟。
- **查询和导出订单**：点击“查订单”，按订单号或买家编号片段、状态查询。继承当前经营页的月份和地区，每页 20 笔；包含取消和未交付订单。修改条件后需重新查询；导出当前查询的全部结果，最多 20,000 笔。CSV 文本已处理公式前缀，Excel 可直接打开。
- **完整月份环比**：选择一个月即可比较四项指标与上月的变化。两个月都在源数据日期覆盖范围内才计算，同一地区筛选下重新统计人数；零基数不显示百分比，日期覆盖不保证交易全量。
- **来源与版本**：选择已接入并成功发布的来源；每次变化生成独立成功快照，旧版本保留。失败保持上次成功数据，结构变化需要重新确认映射。订单查询、导出与报告固定到当前显示版本。上传文件是静态副本，需要跟踪原文件变化时选择“监测本机文件”。

接入配置与各来源快照保存在工作区的 `connections/` 下；九列规范化输入、来源元数据及映射参与审计。数据库密码仅保存在当前进程内存，重启后重新填写。九列订单模型支持 31 个省级地区全称和四种中文状态；金额非负、最多两位小数。模板没有真实交付日期，不推断物流时效。多商品订单应先汇总为一行，退款口径需另行确认。详见 [数据连接、更新与边界](docs/data-connections.md)。

交付附带 `订单数据.csv`、`订单数据.xlsx`、`订单数据.json`、`订单数据.parquet`、`订单数据.sqlite` 五份独立文件，均为相同的 12,000 笔订单，由用户任选一种手动导入。覆盖 2026 年 1—9 月、31 个地区、8 个分类、重复买家与三种订单状态；金额直接按人民币分生成。数据由 `scripts/export_import_samples.py` 确定性构造，不来自真实交易，也不会在程序启动时自动导入。导出拒绝覆盖已有同名文件。

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.launcher
# 可选：另行生成五种可导入文件，目标目录中不能已有同名文件
.\.venv\Scripts\python.exe -B scripts/export_import_samples.py work/import-samples
```

## 保留的 Olist 真实历史数据版本

原始巴西数据及其成果仍独立保留，币种仍是 BRL。需要运行这个版本时，在另一个端口启动：

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.pipeline data/raw/olist artifacts/analytics
.\.venv\Scripts\python.exe -m zhishu_inspection.server artifacts/analytics --port 8766
```

服务仅接受本机访问。Ctrl+C 停止服务。重新导入时可在另一个终端运行加工命令；网页更改筛选或点击“恢复全部”后读取新成功批次。

## 新环境复现

需要 Python 3.11 或更高版本和当前源码目录。`requirements-lock.txt` 记录当前环境验证过的直接依赖，采用 editable 安装，运行时保留源码和根目录 sql/。本轮未完成从全新环境清空依赖再安装的独立验收，下面是复现步骤。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pytest
```

启动空工作区无需下载数据。安装后运行 launcher，再手动导入文件或配置数据库。需要复现原始巴西历史版时，从 [Olist 发布页](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 获取数据，解压这五个文件到 `data/raw/olist/`：

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

每次运行保存独立 run_id。各输出目录的 `latest.json` 只指向成功批次；批次目录保留 data.duckdb、manifest.json、quality.json、summary.json 和 report.md。错误批次不替换旧结果。统一接入的内容指纹包含规范化记录和来源/映射，文件主文件 SHA 同时保留为来源证据。SQLite 已提交的 WAL 变化通过只读采集后的内容识别；不能单凭主文件哈希判定数据库没有变化。生成数据不作为内置业务数据发布。

数据模型、字段粒度、质量策略和指标口径见 [数据模型文档](docs/data-model.md)。页面中的质量结果与技术报告覆盖全批次；“保存当前报告”的经营指标、趋势和排名跟随筛选。边界月份可能不完整，不能直接解读为完整月环比。

## 实测验收与分析简报

本轮全套自动化回归已有 321 项通过；最后新增边界回归后的数量以最终运行输出为准。冻结 exe 已实际导入上述五种格式，结果一致：完成订单商品金额 **3,891,488.72 元**、完成订单数 **10,843**、商品金额客单价 **358.89 元**、去重购买客户数 **6,776**。这组数值用于独立文件的一致性验收，启动空工作区不会直接显示这些结果。最终桌面目录拷贝仍需完成最后验收。

```powershell
.\.venv\Scripts\python.exe scripts/verify_demo.py data/raw/olist artifacts/analytics outputs
```

此命令完整重建两次，核对输入指纹、四项指标、模型行数和规则结果的一致性，核对日期/州/品类金额之和与总体相符，并以独立原始层 SQL 核对 SP 州 2018 年 1 月筛选。生成 outputs/ 中的验收 JSON、经营分析简报与质量运行报告。人为异常注入、快照更新和失败恢复见 tests/，使用临时目录，不修改真实源数据。

## 工程边界

这是本机单用户的表格/关系数据分析工具。接入后按确认的单表订单模型做全量快照与更新；不支持任意业务语义、多表自动关联或日志增量 CDC。嵌套 JSON 展开、ZIP 多文件包、PDF/Word 表格提取、图片 OCR、NoSQL 及未列出的文件类型尚未实现。旧于 BIFF8 的 XLS、加密工作簿及超限表格需先转换或缩小范围。每次成功变化生成新目录，需要保留磁盘空间。网络数据库驱动可用不等于真实服务器已验证；源码依赖也不构成完整跨平台锁或容器镜像。

早期 profile、build-db 和 week2 命令仍可使用；开发工作现按可用里程碑持续推进。
