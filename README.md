# 智数巡检

<img src="assets/branding/zhishu-app-v1.png" width="96" alt="智数巡检图标">

在本机导入电商订单，检查数据质量、查看经营指标、核查异常并保存报告。核心分析离线运行，无需 API Key。

当前版本：**0.2.0.dev0 开发预览版**。个人开发与维护：[shuoshuochen44-commits](https://github.com/shuoshuochen44-commits)。

## Windows 程序

前往 [下载页面](https://github.com/shuoshuochen44-commits/ecommerce-analytics-audit/releases/tag/v0.2.0-dev.20261024)，下载 Windows 压缩包并完整解压到可写文件夹，双击 `智数巡检.exe`。无需安装 Python；需要 Windows x64 和 Edge WebView2 Runtime。

首次启动为空工作区：进入“数据接入”，选择订单文件，预览并确认九个字段，检查数据后导入。在“看经营”筛选月份和地区，在“问数据”选择问题，在“查异常”核查变化。月份来自实际订单日期；附带的合成示例覆盖 2026 年 1—9 月。

程序数据保存在程序目录下的 `workspace/`。升级时保留该目录，关闭程序后再替换程序文件；不要用其他人的工作区覆盖自己的工作区。

## 功能

- 经营看板：商品销售额、完成订单数、客单价、去重买家、月份环比、地区和商品分类。
- 数据接入：CSV、TSV、TXT、Excel、ODS、平面 JSON/JSONL、Parquet、SQLite 和 DuckDB；支持本机文件监测和数据库连接。
- 导入检查：预览、九字段映射、逐行诊断、金额与日期校验；失败保留已有成功数据。
- 固定问题：30 条问题目录，保留 SQL、参数、数据版本与核验结果，可下载和重放。
- 异常检测：销售额、订单量和单笔金额规则，显示阈值、证据和历史不足，支持 JSON 与离线 HTML。
- 订单查询与报告：按编号或状态查询订单、导出 CSV、保存经营报告。

## 从源码启动

使用 Python 3.11。Windows PowerShell：

```powershell
git clone --branch codex/program-v0.2.0 https://github.com/shuoshuochen44-commits/ecommerce-analytics-audit.git
cd ecommerce-analytics-audit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m zhishu_inspection.desktop
```

也可双击 `start-desktop.cmd`。只启动本机浏览器服务：

```powershell
.\.venv\Scripts\python.exe -m zhishu_inspection.launcher --no-browser --data-dir work/my-workspace --port 8765
```

## 订单格式

参考 `examples/订单导入模板.csv`。每行是一笔完整订单，订单号唯一；九个字段为订单号、下单日期、省份、买家编号、商品分类、商品金额、运费、支付金额和订单状态。金额为人民币非负数，最多两位小数；日期为 YYYY-MM-DD。省份使用完整省级名称；状态支持已完成、已发货、处理中和已取消。

生成独立合成示例（目标目录必须不存在）：

```powershell
.\.venv\Scripts\python.exe scripts/export_import_samples.py work/import-samples
```

这会生成 12,000 笔虚构订单的 CSV、XLSX、JSON、Parquet 和 SQLite 文件，选择其中一份手动导入。

## 命令行分析

```powershell
.\.venv\Scripts\zhishu-analyze.exe --list
.\.venv\Scripts\zhishu-analyze.exe work/my-audit --detect-anomalies --rules all --input orders.csv --output work/report.json
.\.venv\Scripts\zhishu-analyze.exe work/my-audit A02
```

输入需符合九字段 CSV 格式。输出和工作目录拒绝覆盖；再次检测已有快照时省略 `--input`，或者指定新的工作目录。指标口径与质量规则见 [数据模型](docs/data-model.md)。

## 构建 Windows 程序

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
powershell -ExecutionPolicy Bypass -File scripts/build_desktop.ps1 -PythonPath .venv/Scripts/python.exe -BuildRoot work/desktop-build-new
```

`BuildRoot` 必须是新目录，输出位于该目录的 `dist/智数巡检.exe`；使用仓库内图标。

## 使用范围

面向本机单用户，仅监听本机地址。支持固定问题目录，不提供任意 SQL 或通用自然语言生成。文件输入最多 20 MB、20,000 行、200 列；规范化 CSV 另有 5 MB 限制。当前采用全量快照，历史成功版本保留，需要自行管理磁盘空间。

MySQL/MariaDB、PostgreSQL、SQL Server、Oracle 驱动已包含，但真实服务兼容性未验证。原生保存对话框在其他机器上仍需验证；本预览版不承诺百万订单处理能力。界面的 JSON/HTML 下载入口可用于保存结果。

## 许可

[MIT](LICENSE)。第三方依赖遵循各自许可证，见 [第三方许可](THIRD_PARTY_NOTICES.md)。
