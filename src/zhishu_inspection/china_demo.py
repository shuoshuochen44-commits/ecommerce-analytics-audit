"""Deterministic, entirely fictional mainland China e-commerce inputs."""

import argparse
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from .dataset import CHINA_DATASET


PROVINCES = (
    "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省",
    "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省", "湖北省",
    "湖南省", "广东省", "广西壮族自治区", "海南省", "重庆市", "四川省", "贵州省", "云南省",
    "西藏自治区", "陕西省", "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区",
)
CATEGORIES = ("食品饮料", "家居日用", "服装鞋包", "数码配件", "美妆个护", "运动户外", "母婴用品", "图书文具")


def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def generate_demo(directory: Path, order_count=12000):
    if order_count < 31:
        raise ValueError("模拟订单数至少为 31，以覆盖所有省级地区")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    rng = random.Random(CHINA_DATASET["seed"])
    products = [(f"模拟商品{i:03d}", CATEGORIES[i % len(CATEGORIES)]) for i in range(80)]
    orders, items, customers, payments = [], [], [], []
    for i in range(order_count):
        order_id, customer_id = f"模拟订单{i+1:06d}", f"模拟客户映射{i+1:06d}"
        # A repeat buyer keeps the same province. The first 31 ensure full coverage.
        buyer = i if i < 31 else rng.randrange(max(31, order_count * 3 // 5))
        province = PROVINCES[buyer % len(PROVINCES)]
        customers.append((customer_id, f"模拟买家{buyer:06d}", "000000", "模拟城市", province))
        day = i % 273 if i < 273 else rng.randrange(273)
        purchased = datetime(2026, 1, 1) + timedelta(days=day, hours=rng.randrange(8, 23), minutes=rng.randrange(60))
        status = "canceled" if i % 25 == 24 else "shipped" if i % 37 == 36 else "delivered"
        delivered = purchased + timedelta(days=rng.randrange(1, 6))
        # Explicit synthetic exceptions allow learners to inspect warnings.
        delivered_text = str(delivered) if status == "delivered" and i % 997 != 996 else ""
        orders.append((order_id, customer_id, status, str(purchased), delivered_text, str(purchased + timedelta(days=7))))
        total = 0
        for sequence in range(1, rng.randrange(1, 4) + 1):
            product = rng.choice(products)
            price, freight = rng.randrange(990, 69901), rng.choice((0, 0, 500, 800, 1200))
            total += price + freight
            items.append((order_id, sequence, product[0], "模拟商家", str(purchased + timedelta(days=2)), money(price), money(freight)))
        if i % 333 == 332:
            total += 500  # A fictional 5-yuan discrepancy, not a real loss.
        if i % 7 == 0:
            payments.extend(((order_id, 1, "模拟微信支付", 1, money(total // 2)),
                             (order_id, 2, "模拟余额支付", 1, money(total - total // 2))))
        else:
            payments.append((order_id, 1, rng.choice(("模拟微信支付", "模拟支付宝", "模拟银行卡")), 1, money(total)))
    tables = {
        "orders": (("order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_delivered_customer_date", "order_estimated_delivery_date"), orders),
        "order_items": (("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"), items),
        "customers": (("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"), customers),
        "products": (("product_id", "product_category_name"), products),
        "order_payments": (("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"), payments),
    }
    for name, (header, records) in tables.items():
        with (directory / f"olist_{name}_dataset.csv").open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(header)
            writer.writerows(records)
    (directory / "dataset.json").write_text(json.dumps(CHINA_DATASET, ensure_ascii=False, indent=2), encoding="utf-8")
    return directory


def main():
    parser = argparse.ArgumentParser(description="生成独立的中国大陆模拟经营数据（不会覆盖已有目录）")
    parser.add_argument("directory", type=Path, nargs="?", default=Path("data/raw/china_demo"))
    args = parser.parse_args()
    generate_demo(args.directory)
    print(f"已生成模拟数据：{args.directory}")


if __name__ == "__main__":
    main()
