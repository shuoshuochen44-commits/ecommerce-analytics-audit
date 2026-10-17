"""Dataset identity travels with a snapshot, never inferred from UI labels."""

import json


OLIST_DATASET = {
    "id": "olist", "name": "巴西电商公开历史数据", "simulated": False,
    "currency": "BRL", "currency_label": "巴西雷亚尔", "region_label": "州",
    "description": "来源：Olist 公开历史数据；不代表实时经营。",
}
CHINA_DATASET = {
    "id": "china_demo", "name": "中国大陆电商模拟数据", "simulated": True,
    "currency": "CNY", "currency_label": "人民币", "region_label": "省级地区",
    "description": "模拟数据：由程序独立生成，仅供学习和功能演示，不代表真实交易或市场表现；金额直接以人民币生成。",
    "generator_version": "1.0", "seed": 20261017,
    "period": "2026年1—9月",
}


def read_dataset(raw_dir):
    path = raw_dir / "dataset.json"
    if not path.exists():
        return dict(OLIST_DATASET)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise ValueError("数据集说明无法读取") from error
    if value not in (CHINA_DATASET, OLIST_DATASET):
        raise ValueError("数据集说明与支持的来源、币种或生成版本不一致")
    return value
