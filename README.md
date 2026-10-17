# 智数：电商经营分析与数据质量监控

把 Olist 五张公开电商 CSV 加工为可核对的指标与中文看板。当前里程碑覆盖导入、明细建模、18 条质量检查、经营筛选、对账、来源证据、失败恢复与全量快照重建。

## 立即使用

Windows 已有本地环境时，双击 `start-dashboard.cmd`，保持终端窗口打开，然后访问 [本地看板](http://127.0.0.1:8765)。页面包括经营概览、质量报告和数据证据。

也可以在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.pipeline data/raw/olist artifacts/analytics
.\.venv\Scripts\python.exe -m zhishu_inspection.server artifacts/analytics --port 8765
```

默认仅接受本机访问。若端口已在使用，使用 `--port 8766` 并打开相应地址。Ctrl+C 停止服务。重新导入时可在另一个终端运行加工命令；网页重新应用筛选后读取新成功批次。

## 新环境复现

需要 Python 3.11 或更高版本和当前源码目录。以下固定经过验证的直接依赖版本，采用 editable 安装，运行时保留源码和根目录 sql/。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pytest
```

从 [Olist 发布页](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) 获取数据，解压这五个文件到 `data/raw/olist/`：

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

每次运行保存独立 run_id。`artifacts/analytics/latest.json` 只指向成功批次；批次目录保留 data.duckdb、manifest.json、quality.json、summary.json 和 report.md。错误批次不替换旧结果。所有生成数据均被 Git 忽略。

数据模型、字段粒度、质量策略和指标口径见 [数据模型文档](docs/data-model.md)。页面中的质量结果与下载报告覆盖全批次，不随经营筛选变化。边界月份可能不完整，不能直接解读为完整月环比。

## 实测验收与分析简报

```powershell
.\.venv\Scripts\python.exe scripts/verify_demo.py data/raw/olist artifacts/analytics outputs
```

此命令完整重建两次，核对输入指纹、四项指标、模型行数和规则结果的一致性，核对日期/州/品类金额之和与总体相符，并以独立原始层 SQL 核对 SP 州 2018 年 1 月筛选。生成 outputs/ 中的验收 JSON、经营分析简报与质量运行报告。人为异常注入、快照更新和失败恢复见 tests/，使用临时目录，不修改真实源数据。

## 工程边界

这是本地单用户的公开历史数据分析版本。当前提供固定模板只读查询；未加入未知表结构上传、自然语言 SQL、实时采集或增量更新。每次全量重建生成新目录，需要保留磁盘空间。这里只固定已验证的直接依赖；尚未提供完整跨平台依赖锁或容器镜像。

早期 profile、build-db 和 week2 命令仍可使用；开发工作现按可用里程碑持续推进。
