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
