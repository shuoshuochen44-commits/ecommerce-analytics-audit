"""Loopback-only HTTP entry point, exposing fixed read-only queries."""

import argparse
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .analytics import dashboard_data
from .pipeline import load_snapshot
from .reports import user_report


def server_identity(output_root):
    return hashlib.sha256(os.path.normcase(str(Path(output_root).resolve())).encode("utf-8")).hexdigest()


def create_server(output_root, port=8765):
    root = Path(output_root).resolve()
    page = Path(__file__).with_name("web") / "dashboard.html"

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

        def do_GET(self):
            if self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1"):
                self.send_json(403, {"error": "仅允许本机访问"})
                return
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/":
                    self.send_content(200, page.read_bytes(), "text/html; charset=utf-8")
                elif parsed.path in ("/api/data", "/report.html"):
                    if len(parsed.query) > 1024:
                        raise ValueError("筛选参数过长")
                    query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=10)
                    allowed = {"start", "end", "state"}
                    if parsed.path == "/report.html":
                        allowed.add("run_id")
                    if set(query) - allowed or any(len(v) != 1 for v in query.values()):
                        raise ValueError("筛选包含不支持的选项或重复值，请重新选择")
                    filters = {key: value[0] or None for key, value in query.items()}
                    data = dashboard_data(root, **filters)
                    if parsed.path == "/report.html":
                        self.send_content(200, user_report(data).encode("utf-8"), "text/html; charset=utf-8", "zhishu-report.html")
                    else:
                        data["server_identity"] = server_identity(root)
                        self.send_json(200, data)
                elif parsed.path in ("/report.md", "/manifest.json"):
                    snapshot = load_snapshot(root)
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
