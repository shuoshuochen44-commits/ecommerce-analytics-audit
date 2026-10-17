"""One-click startup for the independent domestic demo."""

import argparse
import json
import urllib.request
import webbrowser
from pathlib import Path

from .china_demo import generate_demo
from .dataset import CHINA_DATASET, read_dataset
from .pipeline import load_snapshot, run_pipeline
from .server import create_server, server_identity


def prepare_demo(project):
    project = Path(project)
    raw, output = project / "data/raw/china_demo", project / "artifacts/china-demo"
    if (output / "latest.json").exists():
        if load_snapshot(output)["manifest"].get("dataset") != CHINA_DATASET:
            raise ValueError("演示目录里已有其他来源的数据，请检查 artifacts/china-demo；原数据未修改。")
        return output
    if not raw.exists():
        print("首次使用：正在准备中国大陆模拟数据，请稍等…", flush=True)
        generate_demo(raw)
    if read_dataset(raw) != CHINA_DATASET:
        raise ValueError("模拟数据目录说明不匹配，请检查 data/raw/china_demo。")
    print("正在计算结果并检查数据…", flush=True)
    run_pipeline(raw, output)
    return output


def existing_demo(url, output_root):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url + "api/data", timeout=2) as response:
            data = json.load(response)
        return (isinstance(data, dict) and data.get("dataset") == CHINA_DATASET
                and bool(data.get("run_id")) and data.get("server_identity") == server_identity(output_root))
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description="一键打开中国大陆模拟经营看板")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}/"
    project = Path(__file__).resolve().parents[2]
    if existing_demo(url, project / "artifacts/china-demo"):
        print("看板已经启动，正在为你打开。", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return
    try:
        output = prepare_demo(project)
        server = create_server(output, args.port)
    except OSError as error:
        parser.exit(1, f"暂时无法启动：{error}\n若地址被占用，请关闭旧看板的启动窗口，再双击一次。\n")
    except Exception as error:
        parser.exit(1, f"准备数据时遇到问题：{error}\n请把这条提示发给我处理。\n")
    print(f"看板已就绪：{url}\n浏览器会自动打开；没有打开时可复制上面的网址。\n使用期间请保留此窗口，退出时关闭窗口即可。", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
