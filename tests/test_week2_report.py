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
    assert result["reconciliation_details"] == {
        "mismatch_absolute_difference_sum": "0.00",
        "mismatch_max_absolute_difference": "0.00",
        "missing_items_by_order_status": {},
        "missing_payment_orders": [],
    }
    assert json.loads(
        (output_dir / "summary.json").read_text(encoding="utf-8")
    ) == result
    markdown = (output_dir / "summary.md").read_text(encoding="utf-8")
    assert "230.00" in markdown
    assert "matched" in markdown
    assert "一个订单" in markdown
    assert "order_id + order_item_id" in markdown


def test_week2_evidence_resolves_sql_outside_project_directory(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = Path.cwd()
    raw_dir = (project_root / "tests/fixtures/olist_mini").resolve()
    monkeypatch.chdir(tmp_path)

    result = build_week2_evidence(
        raw_dir,
        tmp_path / "zhishu.duckdb",
        tmp_path / "report",
    )

    assert result["metrics"]["completed_order_count"] == 2
