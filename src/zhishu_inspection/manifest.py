import json
from pathlib import Path
from typing import Any


EXPECTED_FILES = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_order_payments_dataset.csv",
)


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_raw_files(raw_dir: Path) -> None:
    missing = [name for name in EXPECTED_FILES if not (raw_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(missing))
