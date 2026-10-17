import json
from pathlib import Path

import pytest

from zhishu_inspection.analytics import dashboard_data
from zhishu_inspection.pipeline import input_files, load_snapshot, run_pipeline


def test_demo_is_repeatable_chinese_and_refuses_overwrite(tmp_path):
    from zhishu_inspection.china_demo import generate_demo, PROVINCES

    first, second = tmp_path / "first", tmp_path / "second"
    generate_demo(first, order_count=620)
    generate_demo(second, order_count=620)
    assert input_files(first) == input_files(second)
    assert len(PROVINCES) == 31
    import csv
    with (first / "olist_customers_dataset.csv").open(encoding="utf-8", newline="") as source:
        customers = list(csv.DictReader(source))
    assert {row["customer_state"] for row in customers} == set(PROVINCES)
    before = input_files(first)
    with pytest.raises(FileExistsError):
        generate_demo(first)
    assert input_files(first) == before


def test_demo_metadata_filters_and_money_are_consistent(tmp_path):
    from zhishu_inspection.china_demo import generate_demo

    raw, output = tmp_path / "raw", tmp_path / "published"
    generate_demo(raw, order_count=620)
    result = run_pipeline(raw, output)
    snapshot = load_snapshot(output)
    data = dashboard_data(output)
    assert data["dataset"]["id"] == "china_demo"
    assert data["dataset"]["simulated"] is True
    assert data["dataset"]["currency"] == "CNY"
    assert data["metrics"] == result["metrics"]
    assert len(data["available_months"]) == 9
    assert "广东省" in data["states"]
    assert all(not r["failed_count"] for r in data["quality"] if r["blocking"])
    assert "dataset.json" in [r["filename"] for r in snapshot["manifest"]["inputs"]]
    assert snapshot["manifest"]["dataset"] == data["dataset"]
    report = (snapshot["directory"] / "report.md").read_text(encoding="utf-8")
    assert "模拟数据" in report and "人民币" in report
    assert "BRL" not in report and "巴西" not in report
    filtered = dashboard_data(output, start="2026-01-01", end="2026-01-31", state="广东省")
    assert filtered["filters"]["state"] == "广东省"
    assert all(r["month"] == "2026-01" for r in filtered["monthly"])
    assert filtered["available_months"] == data["available_months"]


def test_legacy_dataset_keeps_original_currency(tmp_path):
    run_pipeline(Path("tests/fixtures/olist_mini"), tmp_path)
    data = dashboard_data(tmp_path)
    assert data["dataset"]["currency"] == "BRL"
    assert data["dataset"]["simulated"] is False


def test_invalid_dataset_metadata_does_not_publish(tmp_path):
    import shutil
    raw, output = tmp_path / "raw", tmp_path / "published"
    shutil.copytree("tests/fixtures/olist_mini", raw)
    old = run_pipeline(raw, output)
    (raw / "dataset.json").write_text(json.dumps({"id": "china_demo", "currency": "BRL"}), encoding="utf-8")
    with pytest.raises(ValueError, match="数据集说明"):
        run_pipeline(raw, output)
    assert load_snapshot(output)["run_id"] == old["run_id"]


def test_launcher_prepares_once_and_keeps_other_results(tmp_path):
    from zhishu_inspection.china_demo import generate_demo
    from zhishu_inspection.launcher import prepare_demo
    generate_demo(tmp_path / "data/raw/china_demo", order_count=62)
    old = tmp_path / "artifacts/analytics/latest.json"
    old.parent.mkdir(parents=True)
    old.write_text('{"original": true}')
    output = prepare_demo(tmp_path)
    first = load_snapshot(output)["run_id"]
    assert prepare_demo(tmp_path) == output
    assert load_snapshot(output)["run_id"] == first
    assert old.read_text() == '{"original": true}'


def test_readable_report_matches_filter_and_escapes_data(tmp_path):
    from zhishu_inspection.china_demo import generate_demo
    from zhishu_inspection.reports import user_report
    generate_demo(tmp_path / "raw", order_count=62)
    run_pipeline(tmp_path / "raw", tmp_path / "published")
    data = dashboard_data(tmp_path / "published", state="广东省", start="2026-01-01", end="2026-01-31")
    data["categories"] = [{"category": "<script>alert(1)</script>", "product_amount": "1.00"}]
    report = user_report(data)
    assert "模拟数据" in report and "人民币" in report
    assert "广东省" in report and "2026-01-31" in report
    assert str(data["metrics"]["completed_order_count"]) in report
    assert "<script>" not in report
    assert "&lt;script&gt;" in report


def test_launcher_only_reuses_service_for_its_own_data_directory(tmp_path):
    import threading
    from zhishu_inspection.china_demo import generate_demo
    from zhishu_inspection.launcher import existing_demo
    from zhishu_inspection.server import create_server
    raw, output = tmp_path / "raw", tmp_path / "published"
    generate_demo(raw, order_count=31)
    run_pipeline(raw, output)
    server = create_server(output, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        assert existing_demo(url, output)
        assert not existing_demo(url, tmp_path / "other-project")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
