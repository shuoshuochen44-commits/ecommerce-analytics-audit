# 电商经营分析与数据质量监控平台

本项目把公开电商 CSV 加工为口径明确、可核对的经营指标，并展示数据质量问题如何影响分析结果。

第一周目标：完成数据清单、表粒度、主外键检查，以及商品金额和订单数两个基础指标的人工核对。

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
