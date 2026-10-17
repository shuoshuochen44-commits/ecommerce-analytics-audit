"""Rebuild a complete immutable snapshot; publish only after all checks pass."""

import argparse
import hashlib
import json
import os
import platform
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .database import build_database
from .manifest import EXPECTED_FILES, validate_raw_files
from .modeling import build_models, json_value
from .quality import evaluate_quality


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def input_files(raw_dir):
    validate_raw_files(raw_dir)
    records = []
    for name in EXPECTED_FILES:
        path = raw_dir / name
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        records.append({"filename": name, "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    return records


def load_snapshot(output_root):
    output_root = Path(output_root).resolve()
    pointer = output_root / "latest.json"
    if not pointer.is_file():
        raise FileNotFoundError("No published snapshot. Run zhishu-build first.")
    latest = json.loads(pointer.read_text(encoding="utf-8"))
    run_id = latest["run_id"]
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", run_id):
        raise ValueError("Invalid published run identifier")
    directory = output_root / "runs" / run_id
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "success" or manifest["run_id"] != run_id:
        raise ValueError("Published run is not successful")
    return {"run_id": run_id, "directory": directory, "manifest": manifest,
            "quality": json.loads((directory / "quality.json").read_text(encoding="utf-8")),
            "summary": json.loads((directory / "summary.json").read_text(encoding="utf-8"))}


def render_report(manifest, result):
    lines = ["# 电商经营分析与质量验收报告", "",
             f"批次：`{manifest['run_id']}`", "",
             f"输入指纹：`{manifest['input_fingerprint']}`", "",
             "## 核心指标", "", "| 指标 | 结果 |", "|---|---:|"]
    labels = ("完成订单商品金额（BRL，不含运费）", "完成订单数", "商品金额客单价（BRL）", "唯一购买客户数")
    for label, value in zip(labels, result["metrics"].values()):
        lines.append(f"| {label} | {value if value is not None else '无可用值'} |")
    lines += ["", "## 数据质量", "", "| 规则 | 检查 | 失败/总记录 | 策略 |", "|---|---|---:|---|"]
    for row in result["quality"]:
        lines.append(f"| {row['rule_id']} | {row['label']} | {row['failed_count']}/{row['total_count']} | {'阻止发布' if row['blocking'] else '展示警告'} |")
    lines += ["", "## 支付对账", "", "| 状态 | 订单数 |", "|---|---:|"]
    for status, count in result["reconciliation"].items():
        lines.append(f"| {status} | {count} |")
    lines += ["", "对账覆盖所有源订单，包括同时缺商品与支付的订单。不存在源订单的孤儿记录单独报告：",
              f"商品行 {result['orphan_summary']['item_rows']} 条，支付行 {result['orphan_summary']['payment_rows']} 条，涉及 {result['orphan_summary']['order_ids']} 个订单标识。"]
    lines += ["", "## 模型与核对", "", "| 表 | 行数 |", "|---|---:|"]
    for name, count in result["table_counts"].items():
        lines.append(f"| {name} | {count} |")
    lines += ["", "四项明细层指标已与独立原始层 SQL 逐项对照通过。商品与支付分别聚合到订单后关联。", "",
              "## 口径与限制", "",
              "- 金额只包含已交付订单商品价格，以购买日期归属；按快照最终状态回看历史，币种为巴西雷亚尔 BRL。",
              "- 客户数在每个查询范围内独立去重；各月或各州的客户数不能直接相加。",
              "- 品类订单数不可跨品类相加；无商品明细的订单保留在订单数分母中。",
              "- 支付差异是待核查记录，不能直接当作损失；分析金额不代表财务收入或利润。",
              "- 日期边界月份可能不完整，且以已交付状态回看会产生近期订单状态偏差。",
              "- 质量结果覆盖整个批次，不随网页日期和地区筛选改变。",
              "", "## 来源与运行环境", "",
              f"Python {manifest['python_version']}；DuckDB {manifest['duckdb_version']}；规则/模型版本 {manifest['model_version']}。", "",
              "| 输入文件 | 字节 | SHA256 |", "|---|---:|---|"]
    for row in manifest["inputs"]:
        lines.append(f"| {row['filename']} | {row['size_bytes']} | `{row['sha256']}` |")
    return "\n".join(lines) + "\n"


def run_pipeline(raw_dir: Path, output_root: Path):
    raw_dir, output_root = Path(raw_dir).resolve(), Path(output_root).resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    directory = output_root / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"run_id": run_id, "started_at": now(), "status": "running",
                "model_version": "1.0", "python_version": platform.python_version(),
                "duckdb_version": duckdb.__version__, "raw_directory": str(raw_dir)}
    write_json(directory / "manifest.json", manifest)
    try:
        files = input_files(raw_dir)
        fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        manifest.update(inputs=files, input_fingerprint=fingerprint)
        raw_counts = build_database(raw_dir, directory / "data.duckdb")
        connection = duckdb.connect(str(directory / "data.duckdb"))
        try:
            quality = evaluate_quality(connection)
            for rule in quality:
                rule["run_id"] = run_id
            write_json(directory / "quality.json", quality)
            result = build_models(connection)
            reconciliation = dict(connection.execute(
                "SELECT reconciliation_status, count(*) FROM dwd_orders GROUP BY 1 ORDER BY 1"
            ).fetchall())
            samples_cursor = connection.execute(
                "SELECT order_id, product_amount+freight_amount AS item_and_freight_total, "
                "payment_amount AS payment_total, payment_difference AS difference, reconciliation_status "
                "FROM dwd_orders WHERE reconciliation_status!='matched' ORDER BY order_id LIMIT 20"
            )
            columns = [col[0] for col in samples_cursor.description]
            samples = [dict(zip(columns, map(json_value, row))) for row in samples_cursor.fetchall()]
            orphan_summary = {
                "item_rows": connection.execute("SELECT count(*) FROM dwd_order_items WHERE missing_order").fetchone()[0],
                "payment_rows": next(r["failed_count"] for r in quality if r["rule_id"] == "Q18"),
                "order_ids": connection.execute(
                    "SELECT count(*) FROM (SELECT order_id FROM raw_order_items UNION SELECT order_id FROM raw_payments) r "
                    "WHERE NOT EXISTS (SELECT 1 FROM raw_orders o WHERE o.order_id=r.order_id)"
                ).fetchone()[0],
            }
            result.update(quality=quality, raw_counts=raw_counts, reconciliation=reconciliation,
                          reconciliation_samples=samples, orphan_summary=orphan_summary,
                          run_id=run_id, input_fingerprint=fingerprint)
        finally:
            connection.close()
        if input_files(raw_dir) != files:
            raise ValueError("Source files changed during processing; snapshot not published")
        manifest.update(status="success", finished_at=now())
        write_json(directory / "summary.json", result)
        (directory / "report.md").write_text(render_report(manifest, result), encoding="utf-8")
        write_json(directory / "manifest.json", manifest)
        temporary = output_root / f".latest-{uuid.uuid4().hex}.tmp"
        write_json(temporary, {"run_id": run_id})
        os.replace(temporary, output_root / "latest.json")
        return result
    except Exception as error:
        manifest.update(status="failed", finished_at=now(), error=f"{type(error).__name__}: {error}")
        write_json(directory / "manifest.json", manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description="重建、核验并发布本地经营分析快照")
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("output_root", type=Path, nargs="?", default=Path("artifacts/analytics"))
    args = parser.parse_args()
    try:
        result = run_pipeline(args.raw_dir, args.output_root)
    except Exception as error:
        parser.exit(1, f"本次未发布：{error}\n旧成功批次保持不变；请查看 runs 中的失败日志。\n")
    print(json.dumps({"run_id": result["run_id"], "metrics": result["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
