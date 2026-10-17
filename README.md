# 电商经营分析与数据质量监控平台

本项目把公开电商 CSV 加工为口径明确、可核对的经营指标，并展示数据质量问题如何影响分析结果。

第一周完成数据清单、表粒度、主外键检查，以及商品金额和订单数两个基础指标的人工核对。第二周建立持久化 DuckDB、支付对账和四项核心指标。

## 本地环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

## 第一周复现

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\zhishu-profile.exe tests/fixtures/olist_mini --output-dir artifacts/week-01/fixture
```

真实数据放入 `data/raw/olist/` 后，将命令中的 fixture 路径替换为该目录。

## 第二周：建立数据库并生成指标报告

```powershell
.\.venv\Scripts\zhishu-week2.exe data/raw/olist data/zhishu.duckdb artifacts/week-02/real
```

命令会重新生成五张 `raw_*` 表，计算四项指标并输出支付对账结果。重复执行会替换数据表，不会追加重复记录。

数据库文件 `data/zhishu.duckdb` 和 `artifacts/` 中的生成报告均由 Git 忽略。版本库保留生成逻辑、SQL、测试和经过核验的中文报告。

## 查询数据库

```powershell
.\.venv\Scripts\python.exe
```

```python
import duckdb

con = duckdb.connect("data/zhishu.duckdb", read_only=True)
con.sql("SHOW TABLES").show()
con.sql("SELECT order_status, count(*) FROM raw_orders GROUP BY 1 ORDER BY 2 DESC").show()
con.close()
```
