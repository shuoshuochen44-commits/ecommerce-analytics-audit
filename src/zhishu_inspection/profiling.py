from pathlib import Path
from typing import Any

import duckdb

from .manifest import EXPECTED_FILES, validate_raw_files


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def profile_dataset(raw_dir: Path) -> dict[str, dict[str, Any]]:
    validate_raw_files(raw_dir)
    connection = duckdb.connect(":memory:")
    profile: dict[str, dict[str, Any]] = {}
    try:
        for filename in EXPECTED_FILES:
            source = _quoted_path(raw_dir / filename)
            relation = f"read_csv('{source}', header=true, all_varchar=true)"
            columns = [
                row[0]
                for row in connection.execute(
                    f"DESCRIBE SELECT * FROM {relation}"
                ).fetchall()
            ]
            row_count = connection.execute(
                f"SELECT count(*) FROM {relation}"
            ).fetchone()[0]
            blank_counts = {}
            for column in columns:
                escaped = column.replace('"', '""')
                blank_counts[column] = connection.execute(
                    f'SELECT count(*) FROM {relation} '
                    f'WHERE "{escaped}" IS NULL OR trim("{escaped}") = \'\''
                ).fetchone()[0]
            result: dict[str, Any] = {
                "row_count": row_count,
                "column_count": len(columns),
                "columns": columns,
                "blank_counts": blank_counts,
            }
            if filename == "olist_orders_dataset.csv":
                date_range = connection.execute(
                    f"SELECT min(order_purchase_timestamp), "
                    f"max(order_purchase_timestamp) FROM {relation}"
                ).fetchone()
                result["purchase_date_min"], result["purchase_date_max"] = date_range
            profile[filename] = result
    finally:
        connection.close()
    return profile


def render_profile_markdown(profile: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# 数据画像",
        "",
        "| 文件 | 行数 | 列数 | 空值单元格 |",
        "|---|---:|---:|---:|",
    ]
    for filename, details in profile.items():
        blank_total = sum(details["blank_counts"].values())
        lines.append(
            f"| {filename} | {details['row_count']} | "
            f"{details['column_count']} | {blank_total} |"
        )
    return "\n".join(lines) + "\n"
