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
