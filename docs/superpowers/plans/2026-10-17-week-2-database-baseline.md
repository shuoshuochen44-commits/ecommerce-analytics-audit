# Week 2 Persistent Database and Metric Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable persistent DuckDB from the five Olist CSV files, reconcile order payments at order grain, calculate all four required V1 metrics, and generate a human-readable week-two report.

**Architecture:** `database.py` owns repeatable CSV-to-DuckDB loading and never contains metric definitions. SQL files own business calculations. `week2_report.py` executes those SQL files against the persisted database and writes JSON plus Markdown evidence. Tests use the committed miniature dataset and a temporary DuckDB file.

**Tech Stack:** Python 3.11, DuckDB, pytest, SQL, Markdown, Git

---

## Scope and time budget

| Task | Budget | Result |
|---|---:|---|
| Persistent database builder | 2.0 h | Five `raw_*` tables and idempotent rebuild command |
| Payment reconciliation | 2.0 h | Order-grain reconciliation query and fixture proof |
| Four required metrics | 2.0 h | Amount, order count, average order value, unique buyers |
| One-command report | 2.0 h | Database plus JSON/Markdown summary |
| Real-data run, documentation and review | 2.0 h | Week-two evidence and reproducible commands |

## File map

```text
src/zhishu_inspection/
├── database.py          # Build and inspect persistent DuckDB files
└── week2_report.py      # Execute metric SQL and render evidence
sql/
├── metrics/
│   ├── completed_average_order_value.sql
│   └── completed_unique_customer_count.sql
└── quality/
    └── payment_reconciliation.sql
tests/
├── test_database.py
├── test_metrics.py
└── test_week2_report.py
docs/
└── week-02-database-baseline.md
```

## Task 1: Build a persistent DuckDB repeatably

**Files:**
- Create: `src/zhishu_inspection/database.py`
- Create: `tests/test_database.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing database tests**

Create `tests/test_database.py`:

```python
from pathlib import Path

import duckdb

from zhishu_inspection.database import build_database


FIXTURE_DIR = Path("tests/fixtures/olist_mini")


def test_build_database_creates_five_raw_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "zhishu.duckdb"
    counts = build_database(FIXTURE_DIR, database_path)

    assert counts == {
        "raw_orders": 3,
        "raw_order_items": 4,
        "raw_customers": 3,
        "raw_products": 2,
        "raw_payments": 4,
    }
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    finally:
        connection.close()
    assert tables == set(counts)


def test_rebuild_replaces_tables_without_duplicating_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "zhishu.duckdb"
    first = build_database(FIXTURE_DIR, database_path)
    second = build_database(FIXTURE_DIR, database_path)
    assert second == first
```

- [ ] **Step 2: Run tests and verify the import failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_database.py -v
```

Expected: collection fails because `zhishu_inspection.database` does not exist.

- [ ] **Step 3: Implement the builder and CLI**

Create `src/zhishu_inspection/database.py`:

```python
import argparse
from pathlib import Path

import duckdb

from .manifest import validate_raw_files


TABLE_FILES = {
    "raw_orders": "olist_orders_dataset.csv",
    "raw_order_items": "olist_order_items_dataset.csv",
    "raw_customers": "olist_customers_dataset.csv",
    "raw_products": "olist_products_dataset.csv",
    "raw_payments": "olist_order_payments_dataset.csv",
}


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def build_database(raw_dir: Path, database_path: Path) -> dict[str, int]:
    validate_raw_files(raw_dir)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    counts: dict[str, int] = {}
    try:
        connection.execute("BEGIN TRANSACTION")
        for table, filename in TABLE_FILES.items():
            source = _quoted_path(raw_dir / filename)
            connection.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv('{source}', header=true, auto_detect=true)"
            )
            counts[table] = connection.execute(
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0]
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the persistent Zhishu DuckDB")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("database_path", type=Path)
    args = parser.parse_args()
    counts = build_database(args.raw_dir, args.database_path)
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add the console command**

Add under `[project.scripts]` in `pyproject.toml`:

```toml
zhishu-build-db = "zhishu_inspection.database:main"
```

- [ ] **Step 5: Reinstall and run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_database.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit the builder**

```powershell
git add pyproject.toml src/zhishu_inspection/database.py tests/test_database.py
git commit -m "feat: build persistent DuckDB from source files"
```

## Task 2: Reconcile item plus freight totals with payments

**Files:**
- Create: `sql/quality/payment_reconciliation.sql`
- Create: `tests/test_payment_reconciliation.py`

- [ ] **Step 1: Write the order-grain SQL**

Create `sql/quality/payment_reconciliation.sql`:

```sql
WITH item_totals AS (
    SELECT
        order_id,
        CAST(sum(price + freight_value) AS DECIMAL(18, 2)) AS item_and_freight_total
    FROM raw_order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT
        order_id,
        CAST(sum(payment_value) AS DECIMAL(18, 2)) AS payment_total
    FROM raw_payments
    GROUP BY order_id
)
SELECT
    coalesce(i.order_id, p.order_id) AS order_id,
    i.item_and_freight_total,
    p.payment_total,
    CAST(p.payment_total - i.item_and_freight_total AS DECIMAL(18, 2)) AS difference,
    CASE
        WHEN i.order_id IS NULL THEN 'missing_items'
        WHEN p.order_id IS NULL THEN 'missing_payment'
        WHEN abs(p.payment_total - i.item_and_freight_total) <= 0.01 THEN 'matched'
        ELSE 'mismatch'
    END AS reconciliation_status
FROM item_totals AS i
FULL OUTER JOIN payment_totals AS p USING (order_id)
ORDER BY order_id;
```

- [ ] **Step 2: Write fixture tests**

Create `tests/test_payment_reconciliation.py`:

```python
from pathlib import Path

import duckdb

from zhishu_inspection.database import build_database


def test_fixture_payments_match_item_and_freight_totals(tmp_path: Path) -> None:
    database_path = tmp_path / "zhishu.duckdb"
    build_database(Path("tests/fixtures/olist_mini"), database_path)
    sql = Path("sql/quality/payment_reconciliation.sql").read_text(encoding="utf-8")
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(sql).fetchall()
    finally:
        connection.close()

    assert len(rows) == 3
    assert {row[4] for row in rows} == {"matched"}
    assert {row[3] for row in rows} == {0}
```

- [ ] **Step 3: Run the reconciliation test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_payment_reconciliation.py -v
```

Expected: `1 passed`.

- [ ] **Step 4: Commit the reconciliation rule**

```powershell
git add sql/quality/payment_reconciliation.sql tests/test_payment_reconciliation.py
git commit -m "feat: reconcile payments at order grain"
```

## Task 3: Complete the four V1 metrics

**Files:**
- Create: `sql/metrics/completed_average_order_value.sql`
- Create: `sql/metrics/completed_unique_customer_count.sql`
- Modify: `tests/test_metrics.py`

- [ ] **Step 1: Add average order value SQL**

Create `sql/metrics/completed_average_order_value.sql`:

```sql
SELECT CAST(
    sum(i.price) / nullif(count(DISTINCT o.order_id), 0)
    AS DECIMAL(18, 2)
) AS completed_average_order_value
FROM raw_order_items AS i
INNER JOIN raw_orders AS o USING (order_id)
WHERE o.order_status = 'delivered';
```

- [ ] **Step 2: Add unique buyer SQL**

Create `sql/metrics/completed_unique_customer_count.sql`:

```sql
SELECT count(DISTINCT c.customer_unique_id) AS completed_unique_customer_count
FROM raw_orders AS o
INNER JOIN raw_customers AS c USING (customer_id)
WHERE o.order_status = 'delivered';
```

- [ ] **Step 3: Update existing metric table names**

Change `completed_order_count.sql` to read from `raw_orders`, and change `completed_product_amount.sql` to join `raw_order_items` with `raw_orders`. The status filter and definitions remain unchanged.

- [ ] **Step 4: Replace metric tests with persistent-database tests**

Replace `tests/test_metrics.py` with:

```python
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from zhishu_inspection.database import build_database


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "zhishu.duckdb"
    build_database(Path("tests/fixtures/olist_mini"), path)
    return path


def _metric(database_path: Path, filename: str):
    sql = Path("sql/metrics", filename).read_text(encoding="utf-8")
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        return connection.execute(sql).fetchone()[0]
    finally:
        connection.close()


def test_completed_product_amount(database_path: Path) -> None:
    assert _metric(database_path, "completed_product_amount.sql") == Decimal("230.00")


def test_completed_order_count(database_path: Path) -> None:
    assert _metric(database_path, "completed_order_count.sql") == 2


def test_completed_average_order_value(database_path: Path) -> None:
    assert _metric(database_path, "completed_average_order_value.sql") == Decimal("115.00")


def test_completed_unique_customer_count(database_path: Path) -> None:
    assert _metric(database_path, "completed_unique_customer_count.sql") == 1
```

- [ ] **Step 5: Run all metric tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_metrics.py -v
```

Expected: `4 passed`.

- [ ] **Step 6: Commit the four-metric baseline**

```powershell
git add sql/metrics tests/test_metrics.py
git commit -m "feat: complete v1 metric baseline"
```

## Task 4: Generate one-command week-two evidence

**Files:**
- Create: `src/zhishu_inspection/week2_report.py`
- Create: `tests/test_week2_report.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_week2_report.py`:

```python
import json
from pathlib import Path

from zhishu_inspection.week2_report import build_week2_evidence


def test_week2_evidence_contains_metrics_and_reconciliation(tmp_path: Path) -> None:
    output_dir = tmp_path / "report"
    result = build_week2_evidence(
        Path("tests/fixtures/olist_mini"),
        tmp_path / "zhishu.duckdb",
        output_dir,
    )

    assert result["metrics"] == {
        "completed_product_amount": "230.00",
        "completed_order_count": 2,
        "completed_average_order_value": "115.00",
        "completed_unique_customer_count": 1,
    }
    assert result["reconciliation"] == {"matched": 3}
    assert json.loads((output_dir / "summary.json").read_text(encoding="utf-8")) == result
    markdown = (output_dir / "summary.md").read_text(encoding="utf-8")
    assert "230.00" in markdown
    assert "matched" in markdown
```

- [ ] **Step 2: Run the test and verify the import failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_week2_report.py -v
```

Expected: collection fails because `zhishu_inspection.week2_report` does not exist.

- [ ] **Step 3: Implement report generation**

Create `src/zhishu_inspection/week2_report.py` with:

```python
import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .database import build_database


METRIC_FILES = {
    "completed_product_amount": "completed_product_amount.sql",
    "completed_order_count": "completed_order_count.sql",
    "completed_average_order_value": "completed_average_order_value.sql",
    "completed_unique_customer_count": "completed_unique_customer_count.sql",
}


def _json_value(value: Any) -> Any:
    return format(value, "f") if isinstance(value, Decimal) else value


def build_week2_evidence(
    raw_dir: Path, database_path: Path, output_dir: Path
) -> dict[str, Any]:
    counts = build_database(raw_dir, database_path)
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        metrics = {}
        for name, filename in METRIC_FILES.items():
            sql = Path("sql/metrics", filename).read_text(encoding="utf-8")
            metrics[name] = _json_value(connection.execute(sql).fetchone()[0])
        reconciliation_sql = Path(
            "sql/quality/payment_reconciliation.sql"
        ).read_text(encoding="utf-8")
        reconciliation = dict(
            connection.execute(
                "SELECT reconciliation_status, count(*) FROM ("
                + reconciliation_sql.rstrip().rstrip(";")
                + ") GROUP BY 1 ORDER BY 1"
            ).fetchall()
        )
    finally:
        connection.close()

    result = {
        "table_counts": counts,
        "metrics": metrics,
        "reconciliation": reconciliation,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    metric_lines = [f"| {name} | {value} |" for name, value in metrics.items()]
    reconciliation_lines = [
        f"| {status} | {count} |" for status, count in reconciliation.items()
    ]
    markdown = "\n".join(
        [
            "# 第二周数据库与指标结果",
            "",
            "## 四项指标",
            "",
            "| 指标 | 结果 |",
            "|---|---:|",
            *metric_lines,
            "",
            "## 支付对账",
            "",
            "| 状态 | 订单数 |",
            "|---|---:|",
            *reconciliation_lines,
            "",
            "## 口径与限制",
            "",
            "- 商品金额只包含已交付订单的商品 price，不含运费。",
            "- 客单价为已交付订单商品金额除以已交付订单去重数。",
            "- 购买客户数使用 customer_unique_id 去重。",
            "- 支付对账先把商品加运费和支付分别聚合到订单粒度，容差为 0.01。",
            "- 这些分析指标不等同于企业财务收入或利润。",
            "",
            "## 复现命令",
            "",
            "~~~powershell",
            ".\\.venv\\Scripts\\zhishu-week2.exe data/raw/olist data/zhishu.duckdb artifacts/week-02/real",
            "~~~",
            "",
        ]
    )
    (output_dir / "summary.md").write_text(markdown, encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build database and week-two report")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("database_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = build_week2_evidence(args.raw_dir, args.database_path, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register and reinstall the report command**

Add under `[project.scripts]`:

```toml
zhishu-week2 = "zhishu_inspection.week2_report:main"
```

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

- [ ] **Step 5: Run the integration test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_week2_report.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Commit the reporting command**

```powershell
git add pyproject.toml src/zhishu_inspection/week2_report.py tests/test_week2_report.py
git commit -m "feat: generate week two evidence"
```

## Task 5: Run real data and document findings

**Files:**
- Create: `docs/week-02-database-baseline.md`
- Modify: `README.md`

- [ ] **Step 1: Generate the real database and report**

Run:

```powershell
.\.venv\Scripts\zhishu-week2.exe data/raw/olist data/zhishu.duckdb artifacts/week-02/real
```

Expected: `data/zhishu.duckdb`, `artifacts/week-02/real/summary.json`, and `summary.md` are created. The console prints five table counts, four metrics and reconciliation status counts.

- [ ] **Step 2: Save the generated report as project evidence**

Run:

```powershell
Copy-Item -LiteralPath artifacts/week-02/real/summary.md -Destination docs/week-02-database-baseline.md
```

Expected: the committed report contains the actual real-data values, metric definitions, reconciliation tolerance, limitations and reproduction command generated by the tested code.

- [ ] **Step 3: Add README usage**

Add this reproducible command to `README.md`:

```powershell
.\.venv\Scripts\zhishu-week2.exe data/raw/olist data/zhishu.duckdb artifacts/week-02/real
```

Explain that `data/zhishu.duckdb` and `artifacts/` are generated and ignored by Git.

- [ ] **Step 4: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
git diff --check
git status --short
```

Expected: all tests pass, diff check is empty, and status lists only intended week-two source, SQL, test and documentation changes.

- [ ] **Step 5: Commit the week-two evidence**

```powershell
git add README.md docs/week-02-database-baseline.md
git commit -m "docs: record week two database baseline"
```

## Completion gate

- The same command builds the database twice without duplicating rows.
- The persistent database contains exactly five `raw_*` tables.
- The fixture produces amount 230.00, orders 2, average order value 115.00, and unique buyers 1.
- Fixture payment reconciliation produces three matched orders and zero differences.
- Real-data JSON and Markdown reports are generated from the database.
- The report explains table grain, metric denominators and reconciliation tolerance.
- Full tests pass and the feature branch has no uncommitted source changes.
