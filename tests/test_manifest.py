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
