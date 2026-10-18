"""One-click startup with an empty workspace; data is always user-selected."""

import argparse
import json
import urllib.request
import webbrowser
from pathlib import Path

from .china_demo import generate_demo
from .dataset import CHINA_DATASET, read_dataset
from .pipeline import load_snapshot, run_pipeline
from .server import create_server, server_identity
from .resources import project_directory


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


def prepare_workspace(project):
    output=Path(project)/'workspace'
    output.mkdir(parents=True,exist_ok=True)
    return output


def existing_workspace(url,output_root):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url+'api/health',timeout=1) as response:
            data=json.load(response)
        return data.get('server_identity')==server_identity(output_root)
    except (OSError,ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="智数巡检")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument('--data-dir',type=Path)
    args = parser.parse_args(argv)
    project=project_directory()
    output=args.data_dir or prepare_workspace(project)
    ports=[args.port] if args.port is not None else range(8765,8775)
    for port in ports:
        url=f'http://127.0.0.1:{port}/'
        if existing_workspace(url,output):
            if not args.no_browser:webbrowser.open(url)
            return
    server=None
    try:
        for port in ports:
            try:
                server=create_server(output,port)
                break
            except OSError:
                continue
        if server is None:
            parser.exit(1,'端口暂时不可用，请关闭旧程序后重试。\n')
    except Exception as error:
        parser.exit(1, f"启动未完成：{error}\n")
    url=f'http://127.0.0.1:{server.server_address[1]}/'
    print(f'智数巡检：{url}',flush=True)
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
