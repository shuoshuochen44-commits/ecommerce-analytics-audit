import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from zhishu_inspection.pipeline import run_pipeline
from zhishu_inspection.server import create_server


@pytest.fixture
def live_server(tmp_path):
    run_pipeline(Path("tests/fixtures/olist_mini"), tmp_path)
    server = create_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_http_page_api_filters_and_report(live_server):
    with urllib.request.urlopen(live_server) as response:
        assert "智数" in response.read().decode("utf-8")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
    with urllib.request.urlopen(live_server + "/api/data?state=SP&end=2018-01-31") as response:
        data = json.load(response)
        assert data["metrics"]["completed_product_amount"] == "150.00"
    with urllib.request.urlopen(live_server + "/report.md") as response:
        assert "验收报告" in response.read().decode("utf-8")


def test_downloadable_report_uses_the_selected_scope(live_server):
    with urllib.request.urlopen(live_server + "/report.html?state=SP&end=2018-01-31") as response:
        report = response.read().decode("utf-8")
        assert "text/html" in response.headers["Content-Type"]
        assert "attachment" in response.headers["Content-Disposition"]
        assert "2018-01-31" in report and "SP" in report
        assert "150.00" in report and "巴西雷亚尔" in report


def test_report_stays_on_displayed_snapshot_after_rebuild(live_server, tmp_path):
    import shutil
    with urllib.request.urlopen(live_server + "/api/data") as response:
        original = json.load(response)
    raw = tmp_path / "changed"
    shutil.copytree("tests/fixtures/olist_mini", raw)
    items = raw / "olist_order_items_dataset.csv"
    items.write_text(items.read_text().replace("100.00", "200.00"), encoding="utf-8")
    newer = run_pipeline(raw, tmp_path)
    assert newer["metrics"] != original["metrics"]
    with urllib.request.urlopen(live_server + "/report.html?run_id=" + original["run_id"]) as response:
        report = response.read().decode("utf-8")
        assert original["run_id"] in report
        assert newer["run_id"] not in report
        assert original["metrics"]["completed_product_amount"] in report


@pytest.mark.parametrize("path,status", [
    ("/api/data?start=oops", 400),
    ("/api/data?state=SP&state=RJ", 400),
    ("/api/data?sql=DROP", 400),
    ("/report.html?state=SP&state=RJ", 400),
    ("/report.html?run_id=../../invalid", 400),
    ("/../../pyproject.toml", 404),
])
def test_http_invalid_requests(live_server, path, status):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(live_server + path)
    assert exc.value.code == status


def test_unpublished_server_returns_helpful_error(tmp_path):
    server = create_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/api/data")
        assert exc.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
