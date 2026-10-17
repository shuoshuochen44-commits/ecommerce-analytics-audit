from pathlib import Path

import pytest

from zhishu_inspection.pipeline import run_pipeline
from zhishu_inspection.analytics import dashboard_data


@pytest.fixture
def published(tmp_path):
    run_pipeline(Path("tests/fixtures/olist_mini"), tmp_path)
    return tmp_path


def test_totals_and_grouped_amounts_reconcile(published):
    data = dashboard_data(published)
    assert data["metrics"]["completed_unique_customer_count"] == 1
    assert sum(float(r["product_amount"]) for r in data["monthly"]) == 230
    assert sum(float(r["product_amount"]) for r in data["categories"]) == 230
    assert sum(r["customer_count"] for r in data["monthly"]) == 2
    assert data["metrics"]["completed_order_count"] == 2
    assert len(data["quality"]) >= 8


def test_filters_and_empty_scope(published):
    january = dashboard_data(published, start="2018-01-01", end="2018-01-31", state="SP")
    assert january["metrics"]["completed_product_amount"] == "150.00"
    assert january["metrics"]["completed_order_count"] == 1
    empty = dashboard_data(published, state="RJ")
    assert empty["metrics"]["completed_order_count"] == 0
    assert empty["metrics"]["completed_average_order_value"] is None
    assert empty["monthly"] == []
    assert empty["quality"] == january["quality"]


@pytest.mark.parametrize("filters", [
    {"start": "bad"}, {"start": "2018-02-01", "end": "2018-01-01"},
    {"state": "SP' OR 1=1 --"}, {"state": "absent"},
])
def test_invalid_filters_are_rejected(published, filters):
    with pytest.raises(ValueError):
        dashboard_data(published, **filters)
