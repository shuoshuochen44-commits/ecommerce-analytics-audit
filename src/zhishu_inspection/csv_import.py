"""Validate an order-level Chinese CSV before building an isolated user snapshot."""

import csv
import io
import json
import re
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

from .china_demo import PROVINCES
from .dataset import CUSTOMER_DATASET
from .pipeline import run_pipeline

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000
COLUMNS = ("订单号", "下单日期", "省份", "买家编号", "商品分类", "商品金额", "运费", "支付金额", "订单状态")
STATUSES = {"已完成": "delivered", "已发货": "shipped", "处理中": "processing", "已取消": "canceled"}


def template_csv():
    target = io.StringIO(newline="")
    writer = csv.writer(target)
    writer.writerow(COLUMNS)
    writer.writerows((
        ("示例订单001", "2026-01-01", "广东省", "示例买家001", "食品饮料", "100.00", "5.00", "105.00", "已完成"),
        ("示例订单002", "2026-02-28", "浙江省", "示例买家002", "家居日用", "200.00", "0.00", "200.00", "已完成"),
    ))
    return target.getvalue().encode("utf-8-sig")


def parse_csv(content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError("请选择非空 CSV 文件，大小不能超过 5 MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("gb18030")
        except UnicodeDecodeError:
            raise ValueError("文件编码无法识别，请在 Excel 中另存为 CSV UTF-8") from None
    try:
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, [])
        if tuple(header) != COLUMNS:
            raise ValueError("表头不匹配，请下载模板，保留九列名称与顺序")
        records, seen = [], set()
        for line, cells in enumerate(reader, 2):
            if not cells or all(not value.strip() for value in cells):
                continue
            if len(records) >= MAX_ROWS:
                raise ValueError("最多导入 20,000 笔订单，请缩小文件")
            if len(cells) != len(COLUMNS):
                raise ValueError(f"第 {line} 行列数不对，应为九列")
            row = dict(zip(COLUMNS, (v.strip() for v in cells)))
            for column, value in row.items():
                if not value or len(value) > 80 or any(ord(char) < 32 for char in value):
                    raise ValueError(f"第 {line} 行“{column}”为空、过长或含换行，请修改")
            if row["订单号"] in seen:
                raise ValueError(f"第 {line} 行订单号重复：每行应是一笔完整订单，请先合并商品明细")
            seen.add(row["订单号"])
            try:
                parsed = date.fromisoformat(row["下单日期"])
                if parsed.isoformat() != row["下单日期"]:
                    raise ValueError()
            except ValueError:
                raise ValueError(f"第 {line} 行下单日期请写成 YYYY-MM-DD，例如 2026-01-01") from None
            if row["省份"] not in PROVINCES:
                raise ValueError(f"第 {line} 行省份请填写完整名称，例如广东省、北京市")
            if row["订单状态"] not in STATUSES:
                raise ValueError(f"第 {line} 行订单状态仅支持：" + "、".join(STATUSES))
            for column in ("商品金额", "运费", "支付金额"):
                value = row[column]
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value) or Decimal(value) > Decimal("999999999.99"):
                    raise ValueError(f"第 {line} 行{column}应为不超过 999999999.99 的非负数字，最多两位小数，不带货币符号")
                row[column] = f"{Decimal(value):.2f}"
            records.append(row)
    except csv.Error:
        raise ValueError("CSV 格式损坏，请用 Excel 重新另存为 CSV UTF-8") from None
    if not records:
        raise ValueError("文件没有订单，请填写数据后再导入")
    return records


def preview_csv(content):
    records = parse_csv(content)
    return {"order_count": len(records), "date_min": min(r["下单日期"] for r in records),
            "date_max": max(r["下单日期"] for r in records), "samples": records[:5],
            "completed_amount": f"{sum((Decimal(r['商品金额']) for r in records if r['订单状态']=='已完成'), Decimal(0)):.2f}"}


def import_csv(content, output_root):
    records = parse_csv(content)
    raw = Path(output_root) / "raw" / uuid.uuid4().hex
    raw.mkdir(parents=True, exist_ok=False)
    orders, items, customers, products, payments = [], [], [], [], []
    for index, row in enumerate(records, 1):
        oid, cid, pid = row["订单号"], f"客户映射{index}", f"商品汇总{index}"
        purchased = row["下单日期"] + " 00:00:00"
        orders.append((oid, cid, STATUSES[row["订单状态"]], purchased, "", ""))
        customers.append((cid, row["买家编号"], "", "", row["省份"]))
        products.append((pid, row["商品分类"]))
        items.append((oid, 1, pid, "用户导入", "", row["商品金额"], row["运费"]))
        payments.append((oid, 1, "用户导入", 1, row["支付金额"]))
    tables = {
        "orders": (("order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"), orders),
        "customers": (("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"), customers),
        "products": (("product_id", "product_category_name"), products),
        "order_items": (("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"), items),
        "order_payments": (("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"), payments),
    }
    for name, (header, rows) in tables.items():
        with (raw / f"olist_{name}_dataset.csv").open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(header)
            writer.writerows(rows)
    (raw / "dataset.json").write_text(json.dumps(CUSTOMER_DATASET, ensure_ascii=False, indent=2), encoding="utf-8")
    (raw / "source.csv").write_bytes(content)
    return run_pipeline(raw, output_root)
