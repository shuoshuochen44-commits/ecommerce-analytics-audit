"""Reject invalid import filters before a new workspace is reserved."""

from .csv_import import parse_csv
from .question_catalog import validate_filter_values


def validate_category_filter(category: str | None) -> None:
    if category is not None and (
        not isinstance(category, str) or not category or len(category) > 80
        or any(ord(char) < 32 for char in category)
    ):
        raise ValueError('品类必须是非空且不含控制字符的文本，最长 80 字符')


def validate_anomaly_filter_values(*, start: str | None = None, end: str | None = None,
                                   state: str | None = None, category: str | None = None) -> None:
    validate_filter_values(start=start, end=end, state=state)
    validate_category_filter(category)


def validate_csv_filter_membership(content: bytes, *, state: str | None = None,
                                   category: str | None = None) -> None:
    """Use canonical CSV values and the same full-snapshot existence semantics.

    State and category must each exist somewhere, including cancelled orders
    and dates outside the requested range. Their intersection can be empty.
    The reserved unknown-state value is accepted even if it matches no orders.
    """
    if state in (None, '__unknown__') and category is None:
        return
    records = parse_csv(content)
    if state not in (None, '__unknown__') and not any(row['省份'] == state for row in records):
        raise ValueError('请选择数据中存在的地区')
    if category is not None and not any(row['商品分类'] == category for row in records):
        raise ValueError('请选择数据中存在的品类')
