"""Loopback-only HTTP entry point, exposing fixed read-only queries."""

import argparse
import hashlib
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .analytics import dashboard_data
from .pipeline import load_snapshot
from .reports import user_report
from .csv_import import MAX_BYTES, preview_csv, import_csv, template_csv
from .order_queries import order_data, export_orders


def server_identity(output_root):
    return hashlib.sha256(os.path.normcase(str(Path(output_root).resolve())).encode("utf-8")).hexdigest()


def create_server(output_root, port=8765):
    root = Path(output_root).resolve()
    page = Path(__file__).with_name("web") / "dashboard.html"
    import_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send_content(self, status, body, content_type, download=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, value):
            self.send_content(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

        def read_query(self, parsed, allowed):
            if len(parsed.query) > 2048:
                raise ValueError("筛选参数过长")
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
            if set(query) - allowed - {"source"} or any(len(v) != 1 for v in query.values()):
                raise ValueError("筛选包含不支持的选项或重复值，请重新选择")
            values = {key: value[0] for key, value in query.items()}
            source = values.pop("source", "demo")
            if source not in ("demo", "customer"):
                raise ValueError("数据来源无效，请重新选择")
            return (root / "customer-data" if source == "customer" else root), values

        def do_POST(self):
            host = self.headers.get("Host", "")
            if (host.split(":")[0] not in ("localhost", "127.0.0.1")
                    or self.headers.get("X-Zhishu-Local") != "1"
                    or self.headers.get("Origin", "http://" + host) != "http://" + host):
                self.send_json(403, {"error": "只能从本机看板提交数据"})
                return
            if self.path not in ("/api/import/preview", "/api/import/confirm"):
                self.send_json(404, {"error": "页面不存在"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BYTES:
                    # Drain a bounded small overrun so Windows can deliver the 413
                    # instead of resetting a client still sending its request body.
                    if size > MAX_BYTES:
                        self.connection.settimeout(3)
                        remaining = min(size, MAX_BYTES + 1)
                        try:
                            while remaining:
                                block = self.rfile.read(min(remaining, 65536))
                                if not block:
                                    break
                                remaining -= len(block)
                        except OSError:
                            pass
                    self.send_json(413, {"error": "文件不能为空或超过 5 MB"})
                    return
                self.connection.settimeout(15)
                content = self.rfile.read(size)
                if len(content) != size:
                    raise ValueError("文件未完整上传，请重新选择")
                if self.path.endswith("preview"):
                    self.send_json(200, preview_csv(content))
                else:
                    if not import_lock.acquire(blocking=False):
                        self.send_json(409, {"error": "已有导入正在处理，请稍后再试"})
                        return
                    try:
                        result = import_csv(content, root / "customer-data")
                    finally:
                        import_lock.release()
                    self.send_json(200, {"run_id": result["run_id"], "metrics": result["metrics"]})
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.log_error("import failed: %s", error)
                self.send_json(500, {"error": "本次导入未完成，之前的数据仍保留。请检查启动窗口提示。"})

        def do_GET(self):
            if self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1"):
                self.send_json(403, {"error": "仅允许本机访问"})
                return
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/":
                    self.send_content(200, page.read_bytes(), "text/html; charset=utf-8")
                elif parsed.path in ("/tools.js", "/tools.css"):
                    content_type = "text/javascript; charset=utf-8" if parsed.path.endswith('.js') else "text/css; charset=utf-8"
                    self.send_content(200, (page.parent / parsed.path[1:]).read_bytes(), content_type)
                elif parsed.path in ("/api/data", "/report.html"):
                    allowed = {"start", "end", "state"}
                    if parsed.path == "/report.html":
                        allowed.add("run_id")
                    selected_root, filters = self.read_query(parsed, allowed)
                    data = dashboard_data(selected_root, **{k: v or None for k,v in filters.items()})
                    if parsed.path == "/report.html":
                        self.send_content(200, user_report(data).encode("utf-8"), "text/html; charset=utf-8", "zhishu-report.html")
                    else:
                        data["server_identity"] = server_identity(root)
                        data["customer_available"] = (root / "customer-data/latest.json").exists()
                        self.send_json(200, data)
                elif parsed.path in ("/api/orders", "/orders.csv"):
                    selected_root, filters = self.read_query(parsed, {"start", "end", "state", "search", "status", "page", "run_id"})
                    if parsed.path == "/orders.csv":
                        filters.pop("page", None)
                        self.send_content(200, export_orders(selected_root, **filters), "text/csv; charset=utf-8", "zhishu-orders.csv")
                    else:
                        self.send_json(200, order_data(selected_root, **filters))
                elif parsed.path == "/template.csv":
                    self.send_content(200, template_csv(), "text/csv; charset=utf-8", "zhishu-template.csv")
                elif parsed.path in ("/report.md", "/manifest.json"):
                    selected_root, filters = self.read_query(parsed, {"run_id"})
                    snapshot = load_snapshot(selected_root, filters.get("run_id") or None)
                    filename = parsed.path.removeprefix("/")
                    content_type = "text/markdown; charset=utf-8" if filename.endswith(".md") else "application/json; charset=utf-8"
                    self.send_content(200, (snapshot["directory"] / filename).read_bytes(), content_type)
                elif parsed.path == "/favicon.ico":
                    self.send_content(204, b"", "image/x-icon")
                else:
                    self.send_json(404, {"error": "页面不存在"})
            except FileNotFoundError:
                self.send_json(503, {"error": "数据还没准备好。请双击项目里的“打开智数看板.cmd”，等待提示看板已就绪后再试。"})
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.log_error("query failed: %s", error)
                self.send_json(500, {"error": "暂时无法读取数据。请重新打开看板；仍有问题时，把启动窗口的提示发给我。"})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description="启动智数本地经营看板")
    parser.add_argument("output_root", nargs="?", type=Path, default=Path("artifacts/analytics"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.output_root, args.port)
    print(f"智数已启动：http://127.0.0.1:{server.server_address[1]} （Ctrl+C 停止）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
