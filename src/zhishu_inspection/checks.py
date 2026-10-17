from pathlib import Path

import duckdb

from .manifest import validate_raw_files


def _path(raw_dir: Path, filename: str) -> str:
    return str((raw_dir / filename).resolve()).replace("'", "''")


def run_relationship_checks(raw_dir: Path) -> dict[str, int]:
    validate_raw_files(raw_dir)
    connection = duckdb.connect(":memory:")
    try:
        sources = {
            "orders": "olist_orders_dataset.csv",
            "items": "olist_order_items_dataset.csv",
            "customers": "olist_customers_dataset.csv",
            "products": "olist_products_dataset.csv",
        }
        for view, filename in sources.items():
            connection.execute(
                f"CREATE VIEW {view} AS SELECT * FROM "
                f"read_csv('{_path(raw_dir, filename)}', "
                f"header=true, all_varchar=true)"
            )
        queries = {
            "duplicate_order_ids": (
                "SELECT count(*) FROM (SELECT order_id FROM orders "
                "GROUP BY 1 HAVING count(*) > 1)"
            ),
            "duplicate_order_item_keys": (
                "SELECT count(*) FROM (SELECT order_id, order_item_id FROM items "
                "GROUP BY 1, 2 HAVING count(*) > 1)"
            ),
            "orphan_item_orders": (
                "SELECT count(*) FROM items i LEFT JOIN orders o USING(order_id) "
                "WHERE o.order_id IS NULL"
            ),
            "orphan_item_products": (
                "SELECT count(*) FROM items i LEFT JOIN products p USING(product_id) "
                "WHERE p.product_id IS NULL"
            ),
            "orphan_order_customers": (
                "SELECT count(*) FROM orders o LEFT JOIN customers c "
                "USING(customer_id) WHERE c.customer_id IS NULL"
            ),
        }
        return {
            name: connection.execute(sql).fetchone()[0]
            for name, sql in queries.items()
        }
    finally:
        connection.close()
