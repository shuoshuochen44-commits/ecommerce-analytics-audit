"""Prepare a user-readable Windows delivery folder inside work/ (no desktop writes)."""

import hashlib
import json
import shutil
from pathlib import Path

from zhishu_inspection.csv_import import template_csv


project = Path(__file__).resolve().parents[1]
stage = project / "work/practical-package-ready"
stage.mkdir(exist_ok=False)
ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "*.egg-info")
for folder in ("src", "sql", "tests", "docs", ".venv", "scripts"):
    shutil.copytree(project / folder, stage / folder, ignore=ignore)
for filename in ("README.md", "pyproject.toml", "requirements-lock.txt", "打开智数看板.cmd"):
    shutil.copy2(project / filename, stage / filename)
shutil.copytree(project / "data/raw/china_demo", stage / "data/raw/china_demo")
pointer = json.loads((project / "artifacts/china-demo/latest.json").read_text(encoding="utf-8"))
run = pointer["run_id"]
shutil.copytree(project / "artifacts/china-demo/runs" / run, stage / "artifacts/china-demo/runs" / run)
shutil.copy2(project / "artifacts/china-demo/latest.json", stage / "artifacts/china-demo/latest.json")
(stage / "成果文件").mkdir()
for filename in ("增强版使用说明.md", "增强版数据导入.png", "增强版月份对比.png", "中国大陆模拟经营报告.html"):
    shutil.copy2(project / "outputs" / filename, stage / "成果文件" / filename)
entry = (project / "start-dashboard.cmd").read_text(encoding="utf-8")
entry = entry.replace('cd /d "%~dp0"', 'cd /d "%~dp0"\nset "PYTHONPATH=%~dp0src"\nset "PYTHONDONTWRITEBYTECODE=1"')
with (stage / "start-dashboard.cmd").open("w", encoding="utf-8", newline="\r\n") as target:
    target.write(entry)
(stage / "订单导入模板.csv").write_bytes(template_csv())
(stage / "先看这里.txt").write_text(
    "智数经营看板 · 实用增强版\n\n双击“打开智数看板.cmd”，浏览器自动打开。使用时保留启动窗口。\n"
    "新功能：导入订单表格、查询和导出订单、与上月比较、切换演示与自己的数据。\n"
    "导入请先看页面里的步骤，或打开“成果文件/增强版使用说明.md”。模板中的示例行请先删除。\n"
    "本文件夹已包含这台电脑可用的环境，换电脑需配置 Python。\n"
    "如提示地址被占用，请关闭旧版看板启动窗口后再打开。默认演示交易均为虚构。\n", encoding="utf-8-sig")
records = []
for folder in ("src", "sql", "data/raw/china_demo"):
    for path in sorted((stage / folder).rglob("*")):
        if path.is_file():
            records.append({"path": path.relative_to(stage).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
(stage / "文件校验清单.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
print(stage)
