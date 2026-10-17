import json
import shutil
from pathlib import Path

import duckdb
import pytest

from zhishu_inspection.pipeline import run_pipeline, load_snapshot


@pytest.fixture
def raw_dir(tmp_path):
    target = tmp_path / "raw"
    shutil.copytree("tests/fixtures/olist_mini", target)
    return target


def test_snapshot_publication_and_repeat_results(raw_dir, tmp_path):
    root = tmp_path / "published"
    first = run_pipeline(raw_dir, root)
    second = run_pipeline(raw_dir, root)
    assert first["run_id"] != second["run_id"]
    assert first["input_fingerprint"] == second["input_fingerprint"]
    assert first["metrics"] == second["metrics"]
    snapshot = load_snapshot(root)
    assert snapshot["run_id"] == second["run_id"]
    assert snapshot["manifest"]["status"] == "success"
    assert len(snapshot["manifest"]["inputs"]) == 5
    assert (snapshot["directory"] / "report.md").is_file()
    assert all(row["run_id"] == second["run_id"] for row in snapshot["quality"])


def test_failed_run_keeps_prior_success_and_failure_evidence(raw_dir, tmp_path):
    root = tmp_path / "published"
    good = run_pipeline(raw_dir, root)
    items = raw_dir / "olist_order_items_dataset.csv"
    items.write_text(items.read_text().replace("100.00", "bad"), encoding="utf-8")
    with pytest.raises(ValueError, match="Q07"):
        run_pipeline(raw_dir, root)
    assert load_snapshot(root)["run_id"] == good["run_id"]
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in (root / "runs").glob("*/manifest.json")]
    failed = [row for row in manifests if row["status"] == "failed"]
    assert len(failed) == 1
    assert "Q07" in failed[0]["error"]
    assert (root / "runs" / failed[0]["run_id"] / "quality.json").is_file()


def test_snapshot_state_update_changes_history_without_changing_old_run(raw_dir, tmp_path):
    root = tmp_path / "published"
    first = run_pipeline(raw_dir, root)
    orders = raw_dir / "olist_orders_dataset.csv"
    orders.write_text(orders.read_text().replace("o2,c2,canceled", "o2,c2,delivered"), encoding="utf-8")
    second = run_pipeline(raw_dir, root)
    assert second["metrics"]["completed_product_amount"] == "430.00"
    assert second["metrics"]["completed_order_count"] == 3
    assert first["input_fingerprint"] != second["input_fingerprint"]
    old = duckdb.connect(str(root / "runs" / first["run_id"] / "data.duckdb"), read_only=True)
    try:
        assert old.execute("SELECT sum(order_count) FROM dws_daily_state").fetchone()[0] == 2
    finally:
        old.close()


def test_no_snapshot_is_readable_failure(tmp_path):
    with pytest.raises(FileNotFoundError, match="published"):
        load_snapshot(tmp_path)


def test_reconciliation_covers_all_source_orders_and_separates_orphans(raw_dir, tmp_path):
    orders = raw_dir / "olist_orders_dataset.csv"
    orders.write_text(orders.read_text().rstrip() + "\no4,c1,delivered,2018-02-01 09:00:00,,2018-02-07 00:00:00\n", encoding="utf-8")
    items = raw_dir / "olist_order_items_dataset.csv"
    items.write_text(items.read_text().rstrip() + "\norphan,1,p1,s1,2018-02-01 00:00:00,5.00,1.00\n", encoding="utf-8")
    result = run_pipeline(raw_dir, tmp_path / "published")
    assert sum(result["reconciliation"].values()) == 4
    assert result["reconciliation"]["missing_both"] == 1
    assert result["orphan_summary"] == {"item_rows": 1, "payment_rows": 0, "order_ids": 1}
