import argparse
from pathlib import Path

import duckdb

from .manifest import validate_raw_files


TABLE_FILES = {
    "raw_orders": "olist_orders_dataset.csv",
    "raw_order_items": "olist_order_items_dataset.csv",
    "raw_customers": "olist_customers_dataset.csv",
    "raw_products": "olist_products_dataset.csv",
    "raw_payments": "olist_order_payments_dataset.csv",
}


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def build_database(raw_dir: Path, database_path: Path) -> dict[str, int]:
    validate_raw_files(raw_dir)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database_path))
    counts: dict[str, int] = {}
    try:
        connection.execute("BEGIN TRANSACTION")
        for table, filename in TABLE_FILES.items():
            source = _quoted_path(raw_dir / filename)
            connection.execute(
                f"CREATE OR REPLACE TABLE {table} AS "
                f"SELECT * FROM read_csv('{source}', header=true, auto_detect=true)"
            )
            counts[table] = connection.execute(
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0]
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the persistent Zhishu DuckDB")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("database_path", type=Path)
    args = parser.parse_args()
    counts = build_database(args.raw_dir, args.database_path)
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
