# Web demo: tai lieu API song cho AI team
#   Tab 1 "Demo truc tiep": webhook realtime -> bam event -> AI context + trace API call thuc te
#   Tab 2 "Danh muc API": toan bo API can dung, moi cai ghi ro "giup gi cho AI", bam Goi thu -> response that
# Chay: python web_demo.py  -> mo http://localhost:8765
import json
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import jira_client
from ai_context import build_context
from jira_client import call

PORT = 8765
OUT_DIR = Path(__file__).parent / "webhook_payloads"
OUT_DIR.mkdir(exist_ok=True)

EVENTS = []
EVENTS_LOCK = threading.Lock()
BUILD_LOCK = threading.Lock()  # serialize build_context de trace khong lan nhau

from catalog_data import CATALOG, NOTES

# Ghi chu tu dong cho trace: prefix path -> vai tro trong flow
TRACE_NOTES = [
    ("/rest/api/3/issue/", "đọc dữ liệu ticket"),
    ("/rest/api/3/search/jql", "tìm ticket tương tự đã Done"),
    ("/rest/api/3/user/assignable", "ai được phép gán"),
]


def trace_note(path):
    if "/comment" in path:
        return "đọc thảo luận (nguyên nhân/cách fix)"
    if "/transitions" in path:
        return "các bước chuyển hợp lệ"
    for prefix, note in TRACE_NOTES:
        if path.startswith(prefix):
            return note
    return ""


HTML_FILE = Path(__file__).parent / "index.html"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, HTML_FILE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/events":
            with EVENTS_LOCK:
                self._send(200, json.dumps(EVENTS[:50], ensure_ascii=False))
        elif self.path == "/api/catalog":
            self._send(200, json.dumps(CATALOG, ensure_ascii=False))
        elif self.path == "/api/notes":
            self._send(200, json.dumps(NOTES, ensure_ascii=False))
        elif self.path.startswith("/api/try?"):
            self._handle_try()
        elif self.path.startswith("/api/context/"):
            self._handle_context()
        else:
            self._send(404, '{"error": "not found"}')

    def _handle_try(self):
        """Proxy goi thu API Jira - CHI cho phep GET de an toan."""
        import urllib.parse as up
        qs = up.parse_qs(up.urlparse(self.path).query)
        target = qs.get("path", [""])[0]
        if not target.startswith("/rest/") or ".." in target:
            self._send(400, '{"error": "path khong hop le"}')
            return
        parsed = up.urlparse(target)
        params = {k: v[0] for k, v in up.parse_qs(parsed.query).items()} or None
        try:
            result = call("GET", parsed.path, params=params)
            raw = json.dumps(result, indent=2, ensure_ascii=False)
            self._send(200, json.dumps({"ok": True, "bytes": len(raw),
                                        "preview": raw[:8000]}, ensure_ascii=False))
        except Exception as e:
            self._send(200, json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))

    def _handle_context(self):
        key = self.path.split("/api/context/")[1].split("?")[0].upper()
        trace = []
        def hook(method, path, params, ms, nbytes):
            trace.append({"method": method, "path": path,
                          "params": json.dumps(params, ensure_ascii=False)[:200] if params else "",
                          "ms": ms, "bytes": nbytes, "note": trace_note(path)})
        try:
            with BUILD_LOCK:
                jira_client.TRACE_HOOK = hook
                try:
                    ctx = build_context(key)
                finally:
                    jira_client.TRACE_HOOK = None
            ctx["api_trace"] = trace
            self._send(200, json.dumps(ctx, ensure_ascii=False))
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False))

    def do_POST(self):
        if not self.path.startswith("/jira-webhook"):
            self._send(404, '{"error": "not found"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        self._send(200, '{"ok": true}')
        try:
            p = json.loads(raw.decode("utf-8"))
        except Exception:
            return
        event = p.get("webhookEvent", "unknown")
        issue = p.get("issue", {})
        key = issue.get("key", "-")
        now = datetime.now()
        fname = OUT_DIR / f"{now.strftime('%Y%m%d_%H%M%S_%f')}__{event.replace(':', '_')}__{key}.json"
        fname.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
        entry = {
            "time": now.strftime("%H:%M:%S"),
            "event": event,
            "key": key,
            "summary": issue.get("fields", {}).get("summary", ""),
            "changes": [f"{i.get('field')}: {i.get('fromString')} -> {i.get('toString')}"
                        for i in (p.get("changelog") or {}).get("items", [])],
        }
        with EVENTS_LOCK:
            EVENTS.insert(0, entry)
            del EVENTS[100:]
        print(f"[{entry['time']}] {event} {key} {entry['summary']}")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Web demo: http://localhost:{PORT}")
    print(f"Webhook endpoint: POST /jira-webhook (tunnel tro vao day)")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
