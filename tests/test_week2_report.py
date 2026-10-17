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
    assert json.loads(
        (output_dir / "summary.json").read_text(encoding="utf-8")
    ) == result
    markdown = (output_dir / "summary.md").read_text(encoding="utf-8")
    assert "230.00" in markdown
    assert "matched" in markdown
