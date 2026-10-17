# Week 1 Data Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In ten hours, create a reproducible project skeleton, validate the five core Olist files, document table grain and relationships, and prove two base metrics against a hand-checkable fixture.

**Architecture:** Keep raw CSV files outside version control and describe them with a manifest. Put reusable Python logic in `src/zhishu_inspection`, keep metric definitions as readable SQL, and use a tiny committed fixture for deterministic tests. Real-data profiling writes generated reports to `artifacts/` so exploration can be repeated without changing source files.

**Tech Stack:** Python 3.11, DuckDB, pytest, PowerShell, Markdown, Git

---

## Scope and time budget

This plan covers the first 10 hours only.

| Task | Budget | Evidence produced |
|---|---:|---|
| Repository and environment | 1.0 h | Installable package and passing smoke test |
| Data contract and miniature fixture | 1.5 h | Five small CSVs plus manifest validation |
| Dataset inventory | 2.0 h | Machine-readable and Markdown profiles |
| Grain and relationship checks | 2.0 h | Primary-key and foreign-key check report |
| Two base metrics | 2.0 h | Tested product amount and order count SQL |
| First-week notes and clean-room verification | 1.5 h | Data discovery report and fresh verification log |

If real-data download is blocked, complete every task against the fixture and record the blocker in `docs/week-01-data-discovery.md`. Do not substitute an unverified mirror.

## File map

```text
.
├── .gitignore                         # Generated data, database and environment exclusions
├── README.md                          # Project purpose and first-week commands
├── pyproject.toml                     # Runtime and test dependencies
├── data/
│   ├── README.md                      # Authorized raw-data acquisition instructions
│   └── manifest.json                  # Expected source files and business keys
├── docs/
│   └── week-01-data-discovery.md      # Findings, table grain and supported questions
├── sql/
│   └── metrics/
│       ├── completed_order_count.sql  # Delivered distinct-order count
│       └── completed_product_amount.sql # Delivered item-price sum
├── src/
│   └── zhishu_inspection/
│       ├── __init__.py
│       ├── checks.py                  # Grain, uniqueness and referential checks
│       ├── cli.py                     # Profile/check command entry point
│       ├── manifest.py                # Manifest parsing and raw-file validation
│       └── profiling.py               # CSV inventory and report rendering
├── tests/
│   ├── fixtures/
│   │   └── olist_mini/                # Committed hand-checkable CSV fixture
│   ├── test_checks.py
│   ├── test_manifest.py
│   ├── test_metrics.py
│   └── test_profiling.py
└── artifacts/                         # Generated reports, ignored by Git
```

## Task 1: Initialize the repository and Python package

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `pyproject.toml`
- Create: `src/zhishu_inspection/__init__.py`
- Create: `tests/test_manifest.py`

- [ ] **Step 1: Initialize Git**

Run:

```powershell
git init
```

Expected: Git reports an initialized empty repository in the current project directory.

- [ ] **Step 2: Write the first failing smoke test**

Create `tests/test_manifest.py`:

```python
from zhishu_inspection.manifest import EXPECTED_FILES


def test_expected_files_lists_the_five_core_sources() -> None:
    assert set(EXPECTED_FILES) == {
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_customers_dataset.csv",
        "olist_products_dataset.csv",
        "olist_order_payments_dataset.csv",
    }
```

- [ ] **Step 3: Add package metadata and exclusions**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "zhishu-inspection"
version = "0.1.0"
description = "Auditable e-commerce data quality and analysis portfolio project"
requires-python = ">=3.11"
dependencies = ["duckdb>=1.4,<2"]

[project.optional-dependencies]
dev = ["pytest>=8,<10"]

[project.scripts]
zhishu-profile = "zhishu_inspection.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

Create `.gitignore`:

```gitignore
.venv/
__pycache__/
.pytest_cache/
*.pyc
*.duckdb
data/raw/
artifacts/
```

Create `src/zhishu_inspection/__init__.py`:

```python
"""Data discovery and quality checks for the Zhishu portfolio project."""
```

- [ ] **Step 4: Install the project in an isolated environment**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected: installation exits with code 0 and includes DuckDB and pytest.

- [ ] **Step 5: Run the smoke test and confirm the planned failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_manifest.py -v
```

Expected: collection fails with `ModuleNotFoundError` for `zhishu_inspection.manifest`.

- [ ] **Step 6: Add the minimal manifest module**

Create `src/zhishu_inspection/manifest.py`:

```python
EXPECTED_FILES = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_order_payments_dataset.csv",
)
```

- [ ] **Step 7: Re-run the smoke test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_manifest.py -v
```

Expected: `1 passed`.

- [ ] **Step 8: Add the initial README**

Create `README.md`:

```markdown
# 电商经营分析与数据质量监控平台

本项目把公开电商 CSV 加工为口径明确、可核对的经营指标，并展示数据质量问题如何影响分析结果。

第一周目标：完成数据清单、表粒度、主外键检查，以及商品金额和订单数两个基础指标的人工核对。

## 本地环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
```

- [ ] **Step 9: Commit the project skeleton**

Run:

```powershell
git add .gitignore README.md pyproject.toml src/zhishu_inspection/__init__.py src/zhishu_inspection/manifest.py tests/test_manifest.py
git commit -m "chore: initialize data inspection project"
```

Expected: one root commit is created.

## Task 2: Define the source contract and miniature dataset

**Files:**
- Create: `data/README.md`
- Create: `data/manifest.json`
- Create: `tests/fixtures/olist_mini/olist_orders_dataset.csv`
- Create: `tests/fixtures/olist_mini/olist_order_items_dataset.csv`
- Create: `tests/fixtures/olist_mini/olist_customers_dataset.csv`
- Create: `tests/fixtures/olist_mini/olist_products_dataset.csv`
- Create: `tests/fixtures/olist_mini/olist_order_payments_dataset.csv`
- Modify: `src/zhishu_inspection/manifest.py`
- Modify: `tests/test_manifest.py`

- [ ] **Step 1: Create a hand-checkable five-table fixture**

Create `tests/fixtures/olist_mini/olist_orders_dataset.csv`:

```csv
order_id,customer_id,order_status,order_purchase_timestamp,order_delivered_customer_date,order_estimated_delivery_date
o1,c1,delivered,2018-01-05 10:00:00,2018-01-10 12:00:00,2018-01-12 00:00:00
o2,c2,canceled,2018-01-06 11:00:00,,2018-01-13 00:00:00
o3,c3,delivered,2018-02-01 09:00:00,2018-02-08 13:00:00,2018-02-07 00:00:00
```

Create `tests/fixtures/olist_mini/olist_order_items_dataset.csv`:

```csv
order_id,order_item_id,product_id,seller_id,shipping_limit_date,price,freight_value
o1,1,p1,s1,2018-01-08 00:00:00,100.00,10.00
o1,2,p2,s1,2018-01-08 00:00:00,50.00,5.00
o2,1,p1,s1,2018-01-09 00:00:00,200.00,20.00
o3,1,p2,s2,2018-02-04 00:00:00,80.00,8.00
```

Create `tests/fixtures/olist_mini/olist_customers_dataset.csv`:

```csv
customer_id,customer_unique_id,customer_zip_code_prefix,customer_city,customer_state
c1,u1,01001,sao paulo,SP
c2,u2,20040,rio de janeiro,RJ
c3,u1,01001,sao paulo,SP
```

Create `tests/fixtures/olist_mini/olist_products_dataset.csv`:

```csv
product_id,product_category_name
p1,beleza_saude
p2,livros_tecnicos
```

Create `tests/fixtures/olist_mini/olist_order_payments_dataset.csv`:

```csv
order_id,payment_sequential,payment_type,payment_installments,payment_value
o1,1,credit_card,1,100.00
o1,2,voucher,1,65.00
o2,1,credit_card,2,220.00
o3,1,credit_card,1,88.00
```

- [ ] **Step 2: Add the exact source contract**

Create `data/manifest.json`:

```json
{
  "dataset": "Olist Brazilian E-Commerce Public Dataset",
  "source_url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
  "required_files": {
    "olist_orders_dataset.csv": {
      "grain": "one row per order",
      "primary_key": ["order_id"]
    },
    "olist_order_items_dataset.csv": {
      "grain": "one row per item position within an order",
      "primary_key": ["order_id", "order_item_id"]
    },
    "olist_customers_dataset.csv": {
      "grain": "one order-scoped customer record",
      "primary_key": ["customer_id"]
    },
    "olist_products_dataset.csv": {
      "grain": "one row per product",
      "primary_key": ["product_id"]
    },
    "olist_order_payments_dataset.csv": {
      "grain": "one payment sequence within an order",
      "primary_key": ["order_id", "payment_sequential"]
    }
  }
}
```

- [ ] **Step 3: Extend the manifest tests**

Replace `tests/test_manifest.py` with:

```python
from pathlib import Path

import pytest

from zhishu_inspection.manifest import EXPECTED_FILES, load_manifest, validate_raw_files


FIXTURE_DIR = Path("tests/fixtures/olist_mini")


def test_expected_files_lists_the_five_core_sources() -> None:
    assert set(EXPECTED_FILES) == {
        "olist_orders_dataset.csv",
        "olist_order_items_dataset.csv",
        "olist_customers_dataset.csv",
        "olist_products_dataset.csv",
        "olist_order_payments_dataset.csv",
    }


def test_manifest_matches_expected_files() -> None:
    manifest = load_manifest(Path("data/manifest.json"))
    assert set(manifest["required_files"]) == set(EXPECTED_FILES)


def test_validate_raw_files_accepts_complete_fixture() -> None:
    validate_raw_files(FIXTURE_DIR)


def test_validate_raw_files_reports_missing_names(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="olist_orders_dataset.csv"):
        validate_raw_files(tmp_path)
```

- [ ] **Step 4: Run the tests and confirm the planned failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_manifest.py -v
```

Expected: import fails because `load_manifest` and `validate_raw_files` are not defined.

- [ ] **Step 5: Implement manifest loading and file validation**

Replace `src/zhishu_inspection/manifest.py` with:

```python
import json
from pathlib import Path
from typing import Any


EXPECTED_FILES = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_order_payments_dataset.csv",
)


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_raw_files(raw_dir: Path) -> None:
    missing = [name for name in EXPECTED_FILES if not (raw_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(missing))
```

- [ ] **Step 6: Run the manifest tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_manifest.py -v
```

Expected: `4 passed`.

- [ ] **Step 7: Document authorized data acquisition**

Create `data/README.md`:

```markdown
# 原始数据

数据来源：[Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)。

从发布页面下载并解压后，把以下文件放入 `data/raw/olist/`：

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_order_payments_dataset.csv`

`data/raw/` 不进入 Git。下载后记录页面显示的版本、下载日期，并用下面的命令计算哈希：

```powershell
Get-FileHash -Algorithm SHA256 data/raw/olist/*.csv
```

测试与持续集成使用 `tests/fixtures/olist_mini/`，不依赖原始文件。
```

- [ ] **Step 8: Commit the data contract and fixture**

Run:

```powershell
git add data tests/fixtures src/zhishu_inspection/manifest.py tests/test_manifest.py
git commit -m "feat: define source data contract"
```

Expected: a commit containing the five-file contract and deterministic fixture.

## Task 3: Build repeatable CSV profiling

**Files:**
- Create: `src/zhishu_inspection/profiling.py`
- Create: `src/zhishu_inspection/cli.py`
- Create: `tests/test_profiling.py`

- [ ] **Step 1: Write failing profile tests**

Create `tests/test_profiling.py`:

```python
from pathlib import Path

from zhishu_inspection.profiling import profile_dataset, render_profile_markdown


FIXTURE_DIR = Path("tests/fixtures/olist_mini")


def test_profile_dataset_reports_rows_columns_and_date_range() -> None:
    profile = profile_dataset(FIXTURE_DIR)
    orders = profile["olist_orders_dataset.csv"]
    assert orders["row_count"] == 3
    assert orders["column_count"] == 6
    assert orders["blank_counts"]["order_delivered_customer_date"] == 1
    assert orders["purchase_date_min"] == "2018-01-05 10:00:00"
    assert orders["purchase_date_max"] == "2018-02-01 09:00:00"


def test_render_profile_markdown_contains_each_file() -> None:
    report = render_profile_markdown(profile_dataset(FIXTURE_DIR))
    assert "olist_orders_dataset.csv" in report
    assert "olist_order_items_dataset.csv" in report
```

- [ ] **Step 2: Run the profile tests and confirm the planned failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profiling.py -v
```

Expected: collection fails because `zhishu_inspection.profiling` does not exist.

- [ ] **Step 3: Implement profiling**

Create `src/zhishu_inspection/profiling.py`:

```python
from pathlib import Path
from typing import Any

import duckdb

from .manifest import EXPECTED_FILES, validate_raw_files


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def profile_dataset(raw_dir: Path) -> dict[str, dict[str, Any]]:
    validate_raw_files(raw_dir)
    connection = duckdb.connect(":memory:")
    profile: dict[str, dict[str, Any]] = {}
    try:
        for filename in EXPECTED_FILES:
            source = _quoted_path(raw_dir / filename)
            relation = f"read_csv('{source}', header=true, all_varchar=true)"
            columns = [row[0] for row in connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()]
            row_count = connection.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
            blank_counts = {}
            for column in columns:
                escaped = column.replace('"', '""')
                blank_counts[column] = connection.execute(
                    f'SELECT count(*) FROM {relation} WHERE "{escaped}" IS NULL OR trim("{escaped}") = \'\''
                ).fetchone()[0]
            result: dict[str, Any] = {
                "row_count": row_count,
                "column_count": len(columns),
                "columns": columns,
                "blank_counts": blank_counts,
            }
            if filename == "olist_orders_dataset.csv":
                date_range = connection.execute(
                    f"SELECT min(order_purchase_timestamp), max(order_purchase_timestamp) FROM {relation}"
                ).fetchone()
                result["purchase_date_min"], result["purchase_date_max"] = date_range
            profile[filename] = result
    finally:
        connection.close()
    return profile


def render_profile_markdown(profile: dict[str, dict[str, Any]]) -> str:
    lines = ["# 数据画像", "", "| 文件 | 行数 | 列数 | 空值单元格 |", "|---|---:|---:|---:|"]
    for filename, details in profile.items():
        blank_total = sum(details["blank_counts"].values())
        lines.append(f"| {filename} | {details['row_count']} | {details['column_count']} | {blank_total} |")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the profile tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_profiling.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Add the command-line report writer**

Create `src/zhishu_inspection/cli.py`:

```python
import argparse
import json
from pathlib import Path

from .profiling import profile_dataset, render_profile_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the five core Olist CSV files")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/week-01"))
    args = parser.parse_args()

    profile = profile_dataset(args.raw_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "profile.md").write_text(
        render_profile_markdown(profile), encoding="utf-8"
    )
    print(f"Profiled {len(profile)} files into {args.output_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Generate the fixture profile**

Run:

```powershell
.\.venv\Scripts\zhishu-profile.exe tests/fixtures/olist_mini --output-dir artifacts/week-01/fixture
```

Expected: output states `Profiled 5 files` and creates `profile.json` and `profile.md`.

- [ ] **Step 7: Commit the profiler**

Run:

```powershell
git add src/zhishu_inspection/profiling.py src/zhishu_inspection/cli.py tests/test_profiling.py
git commit -m "feat: add repeatable csv profiling"
```

Expected: one profiler commit; generated `artifacts/` files remain untracked.

## Task 4: Check grain and relationships

**Files:**
- Create: `src/zhishu_inspection/checks.py`
- Create: `tests/test_checks.py`

- [ ] **Step 1: Write failing relationship-check tests**

Create `tests/test_checks.py`:

```python
from pathlib import Path

from zhishu_inspection.checks import run_relationship_checks


def test_fixture_keys_and_foreign_keys_are_valid() -> None:
    results = run_relationship_checks(Path("tests/fixtures/olist_mini"))
    assert results == {
        "duplicate_order_ids": 0,
        "duplicate_order_item_keys": 0,
        "orphan_item_orders": 0,
        "orphan_item_products": 0,
        "orphan_order_customers": 0,
    }
```

- [ ] **Step 2: Run the check test and confirm the planned failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_checks.py -v
```

Expected: collection fails because `zhishu_inspection.checks` does not exist.

- [ ] **Step 3: Implement explicit key checks**

Create `src/zhishu_inspection/checks.py`:

```python
from pathlib import Path

import duckdb

from .manifest import validate_raw_files


def _path(raw_dir: Path, filename: str) -> str:
    return str((raw_dir / filename).resolve()).replace("'", "''")


def run_relationship_checks(raw_dir: Path) -> dict[str, int]:
    validate_raw_files(raw_dir)
    connection = duckdb.connect(":memory:")
    try:
        sources = {
            "orders": "olist_orders_dataset.csv",
            "items": "olist_order_items_dataset.csv",
            "customers": "olist_customers_dataset.csv",
            "products": "olist_products_dataset.csv",
        }
        for view, filename in sources.items():
            connection.execute(
                f"CREATE VIEW {view} AS SELECT * FROM read_csv('{_path(raw_dir, filename)}', header=true, all_varchar=true)"
            )
        queries = {
            "duplicate_order_ids": "SELECT count(*) FROM (SELECT order_id FROM orders GROUP BY 1 HAVING count(*) > 1)",
            "duplicate_order_item_keys": "SELECT count(*) FROM (SELECT order_id, order_item_id FROM items GROUP BY 1, 2 HAVING count(*) > 1)",
            "orphan_item_orders": "SELECT count(*) FROM items i LEFT JOIN orders o USING(order_id) WHERE o.order_id IS NULL",
            "orphan_item_products": "SELECT count(*) FROM items i LEFT JOIN products p USING(product_id) WHERE p.product_id IS NULL",
            "orphan_order_customers": "SELECT count(*) FROM orders o LEFT JOIN customers c USING(customer_id) WHERE c.customer_id IS NULL",
        }
        return {name: connection.execute(sql).fetchone()[0] for name, sql in queries.items()}
    finally:
        connection.close()
```

- [ ] **Step 4: Run the relationship-check test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_checks.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit the checks**

Run:

```powershell
git add src/zhishu_inspection/checks.py tests/test_checks.py
git commit -m "feat: validate table grain and relationships"
```

Expected: one commit for deterministic grain and referential checks.

## Task 5: Prove two base metrics without join multiplication

**Files:**
- Create: `sql/metrics/completed_order_count.sql`
- Create: `sql/metrics/completed_product_amount.sql`
- Create: `tests/test_metrics.py`

- [ ] **Step 1: Add exact metric SQL**

Create `sql/metrics/completed_order_count.sql`:

```sql
SELECT count(DISTINCT order_id) AS completed_order_count
FROM orders
WHERE order_status = 'delivered';
```

Create `sql/metrics/completed_product_amount.sql`:

```sql
SELECT CAST(sum(CAST(i.price AS DECIMAL(18, 2))) AS DECIMAL(18, 2)) AS completed_product_amount
FROM order_items AS i
INNER JOIN orders AS o USING (order_id)
WHERE o.order_status = 'delivered';
```

- [ ] **Step 2: Write metric tests with hand-calculated values**

Create `tests/test_metrics.py`:

```python
from decimal import Decimal
from pathlib import Path

import duckdb


FIXTURE_DIR = Path("tests/fixtures/olist_mini").resolve()


def _load_views(connection: duckdb.DuckDBPyConnection) -> None:
    orders = str(FIXTURE_DIR / "olist_orders_dataset.csv").replace("'", "''")
    items = str(FIXTURE_DIR / "olist_order_items_dataset.csv").replace("'", "''")
    connection.execute(f"CREATE VIEW orders AS SELECT * FROM read_csv('{orders}', header=true, all_varchar=true)")
    connection.execute(f"CREATE VIEW order_items AS SELECT * FROM read_csv('{items}', header=true, all_varchar=true)")


def _run_metric(filename: str):
    connection = duckdb.connect(":memory:")
    try:
        _load_views(connection)
        sql = Path("sql/metrics", filename).read_text(encoding="utf-8")
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


def test_completed_order_count_is_two() -> None:
    assert _run_metric("completed_order_count.sql") == 2


def test_completed_product_amount_is_230() -> None:
    assert _run_metric("completed_product_amount.sql") == Decimal("230.00")


def test_naive_order_payment_join_would_multiply_item_amount() -> None:
    connection = duckdb.connect(":memory:")
    try:
        _load_views(connection)
        payments = str(FIXTURE_DIR / "olist_order_payments_dataset.csv").replace("'", "''")
        connection.execute(
            f"CREATE VIEW payments AS SELECT * FROM read_csv('{payments}', header=true, all_varchar=true)"
        )
        naive = connection.execute(
            "SELECT sum(CAST(i.price AS DECIMAL(18, 2))) FROM order_items i "
            "JOIN orders o USING(order_id) JOIN payments p USING(order_id) "
            "WHERE o.order_status = 'delivered'"
        ).fetchone()[0]
        assert naive == Decimal("380.00")
        assert naive != Decimal("230.00")
    finally:
        connection.close()
```

- [ ] **Step 3: Run the metric tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_metrics.py -v
```

Expected: `3 passed`. The third test proves that directly joining two one-to-many tables changes the item amount from 230.00 to 380.00.

- [ ] **Step 4: Commit the metric evidence**

Run:

```powershell
git add sql/metrics tests/test_metrics.py
git commit -m "feat: define and verify base sales metrics"
```

Expected: one commit containing readable SQL and hand-calculated assertions.

## Task 6: Profile real data and write the first-week discovery report

**Files:**
- Create: `docs/week-01-data-discovery.md`
- Modify: `README.md`

- [ ] **Step 1: Acquire the published dataset**

Open the source URL recorded in `data/manifest.json`, download the publisher's archive, and extract the five required files into `data/raw/olist/`. Do not commit the raw files.

Run:

```powershell
Get-FileHash -Algorithm SHA256 data/raw/olist/*.csv
```

Expected: one SHA-256 line per downloaded CSV. Record the source page version, download date and hashes in the discovery report.

If the publisher requires an account that is not available, record `真实数据下载受账号限制；本周验证使用已提交的小样本` and continue with the fixture.

- [ ] **Step 2: Generate the real-data profile**

Run:

```powershell
.\.venv\Scripts\zhishu-profile.exe data/raw/olist --output-dir artifacts/week-01/real
```

Expected: five files are profiled. Review `profile.json` for row counts, columns, blanks and the order purchase date range.

When real data is unavailable, run the same command against `tests/fixtures/olist_mini` and write only fixture-based findings.

- [ ] **Step 3: Run relationship checks on real data**

Run:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; from zhishu_inspection.checks import run_relationship_checks; print(run_relationship_checks(Path('data/raw/olist')))"
```

Expected: a dictionary containing all five check names and non-negative counts. Investigate each non-zero result before treating it as an error; this step records evidence and does not silently delete rows.

- [ ] **Step 4: Write the fixture-confirmed discovery report**

Create `docs/week-01-data-discovery.md` with the following baseline. It deliberately labels fixture evidence. If Step 1 produced authorized real data, add a separate `真实数据画像` section containing the exact version, download date, hashes, row counts, date range and relationship-check counts from Steps 1–3; do not overwrite the fixture evidence.

```markdown
# 第一周：数据摸底与指标基线

## 数据来源与版本

计划数据源为 Olist 发布页面。本节当前结论来自仓库中的测试小样本；真实数据的版本、下载日期和文件哈希仅在实际下载并核验后另行记录。

## 表粒度与业务键

| 表 | 一行代表什么 | 主键或业务键 | 关联方向 |
|---|---|---|---|
| orders | 一个订单 | order_id | customer_id → customers |
| order_items | 订单中的一个商品位置 | order_id + order_item_id | order_id → orders；product_id → products |
| customers | 一个订单使用的客户记录 | customer_id | customer_unique_id 用于识别跨订单同一客户 |
| products | 一个商品 | product_id | 被 order_items 引用 |
| payments | 一个订单内的一次支付序号 | order_id + payment_sequential | order_id → orders |

## 数据画像证据

测试小样本包含 3 个订单、4 条商品明细、3 条订单级客户记录、2 个商品和 4 条支付记录。订单购买时间范围为 2018-01-05 10:00:00 至 2018-02-01 09:00:00；取消订单 o2 的实际交付时间为空。

## 两项指标口径

1. 完成订单商品金额：已交付订单的商品明细 `price` 之和，不含运费，以订单下单时间归属。
2. 完成订单数：已交付订单的 `order_id` 去重数，以订单下单时间归属。

## 关联放大实验

小样本的正确商品金额为 230.00。商品明细直接连接支付明细后得到 380.00，因为订单 o1 的两条商品记录和两条支付记录形成四行组合。金额指标应在正确粒度计算，或先把各侧聚合到订单粒度再连接。

## 五个开发问题

1. 每月完成订单商品金额是多少？
2. 每月完成订单数是多少？
3. 哪些州的完成订单商品金额最高？
4. 哪些商品品类贡献了主要金额？
5. 哪些月份的数据不完整，不适合直接做环比？

## 当前数据不能回答的问题

广告 ROI、利润和页面转化率缺少广告成本、商品成本、曝光及点击数据，当前数据不能可靠回答。

## 发现、限制与第二周入口

已验证：小样本完成订单商品金额为 230.00，完成订单数为 2；直接连接商品明细和支付明细会放大商品金额。仍需使用真实数据核实字段、日期范围、空值和关联异常。第二周补充支付金额核对、客单价与购买客户数。
```

- [ ] **Step 5: Update the README with repeatable commands**

Append to `README.md`:

```markdown
## 第一周复现

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\zhishu-profile.exe tests/fixtures/olist_mini --output-dir artifacts/week-01/fixture
```

真实数据放入 `data/raw/olist/` 后，将命令中的 fixture 路径替换为该目录。
```

- [ ] **Step 6: Run clean verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
git status --short
```

Expected: all tests pass. `git status` lists only the intended documentation changes; raw data, virtual environment and generated artifacts do not appear.

- [ ] **Step 7: Commit the first-week evidence**

Run:

```powershell
git add README.md docs/week-01-data-discovery.md
git commit -m "docs: record first week data discovery"
```

Expected: the working tree is clean after the commit.

## Week 1 completion gate

Week 1 is complete only when all statements below have current evidence:

- The full test command passes.
- The fixture profile contains all five files.
- Every table has a documented grain and business key.
- Primary-key and foreign-key checks produce named counts.
- Completed product amount equals 230.00 and completed order count equals 2 on the fixture.
- The direct item-to-payment join is demonstrated to inflate item amount to 380.00.
- The discovery report distinguishes verified findings from unsupported questions.
- Real-data availability and provenance are stated accurately.

