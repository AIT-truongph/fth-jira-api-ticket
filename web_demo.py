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

# ============ DANH MUC API - noi dung "day" cho AI team ============
# try=True: GET an toan, cho phep bam "Goi thu" tren web ({key}/{project} duoc thay bang input)
CATALOG = [
    {"group": "1. Trigger — Webhook (Jira chủ động gọi mình)", "items": [
        {"method": "POST", "path": "/rest/webhooks/1.0/webhook", "try": False,
         "name": "Đăng ký webhook (cần quyền admin)",
         "ai": "Điểm khởi đầu của cả flow: Jira tự báo khi ticket được tạo/sửa/comment, kèm JQL filter để chỉ nhận đúng project. Service KHÔNG cần polling.",
         "how": 'Body: {"name", "url", "events": ["jira:issue_created","jira:issue_updated","comment_created"], "filters": {"issue-related-events-section": "project = SCRUM"}}. Lưu ý: payload event comment chỉ chứa issue rút gọn 6 fields; thứ tự event KHÔNG đảm bảo → chỉ lấy issue.key rồi gọi GET issue.'},
        {"method": "GET", "path": "/rest/webhooks/1.0/webhook", "try": True,
         "name": "Liệt kê webhook đã đăng ký",
         "ai": "Kiểm tra webhook đang trỏ về đâu, còn enabled không.",
         "how": "Không tham số."},
    ]},
    {"group": "2. Đọc hiểu ticket (input chính cho AI)", "items": [
        {"method": "GET", "path": "/rest/api/3/issue/{key}?expand=renderedFields,names,changelog&fields=*all", "try": True,
         "name": "Get issue — API trung tâm",
         "ai": "Một call lấy gần hết: summary, description, status, priority, labels, custom fields, issue links, subtasks, attachment metadata, changelog. 'names' dịch customfield_xxxxx thành tên người hiểu được; 'renderedFields' trả HTML thay vì ADF.",
         "how": "Description mặc định là ADF (JSON) — cần converter sang text cho AI (xem adf_to_text trong jira_client.py)."},
        {"method": "GET", "path": "/rest/api/3/issue/{key}/comment?orderBy=created", "try": True,
         "name": "Get comments",
         "ai": "Thảo luận trong comment thường chứa nguyên nhân gốc và cách fix — phần giá trị nhất khi AI đọc ticket tương tự đã giải quyết.",
         "how": "Phân trang startAt/maxResults; body comment cũng là ADF."},
        {"method": "GET", "path": "/rest/api/3/issue/{key}/changelog", "try": True,
         "name": "Get changelog",
         "ai": "Lịch sử ai đổi gì khi nào — giúp AI hiểu ticket đã đi qua những bước nào, bị trả lại bao nhiêu lần.",
         "how": "Hoặc gộp luôn vào Get issue bằng expand=changelog."},
        {"method": "GET", "path": "/rest/api/3/attachment/content/{id}", "try": False,
         "name": "Tải nội dung attachment",
         "ai": "Đọc log lỗi, config đính kèm — GET issue chỉ trả metadata, muốn AI đọc được nội dung file phải gọi endpoint này (đã test: tải đúng 100%).",
         "how": "id lấy từ fields.attachment[].id; response là binary; có /thumbnail/{id} cho ảnh."},
        {"method": "GET", "path": "/rest/api/3/issue/{key}/remotelink", "try": True,
         "name": "Get remote links",
         "ai": "Link ngoài gắn vào ticket (trang Confluence, PR...) — ngữ cảnh bổ sung.",
         "how": "Không tham số."},
        {"method": "GET", "path": "/rest/api/3/field", "try": True,
         "name": "Danh mục toàn bộ field",
         "ai": "Bảng tra customfield_xxxxx → tên + kiểu dữ liệu. Cache 1 lần dùng mãi.",
         "how": "Không tham số."},
    ]},
    {"group": "3. Tìm ticket tương tự đã giải quyết", "items": [
        {"method": "GET", "path": '/rest/api/3/search/jql?jql=project = {project} AND statusCategory = Done AND text ~ "timeout"&fields=summary,status,resolution&maxResults=10', "try": True,
         "name": "Enhanced JQL search — endpoint hiện hành",
         "ai": "Trái tim của việc tìm ticket tương tự. JQL mẫu: statusCategory = Done AND (text ~ \"keywords\" OR labels in (...)). LƯU Ý: text ~ là keyword search (không semantic) và KHÔNG quét labels.",
         "how": "Endpoint /search cũ đã khai tử. JQL phải bounded (có project=...). Phân trang bằng nextPageToken (không còn startAt)."},
        {"method": "GET", "path": "/rest/api/3/issue/picker?query=timeout", "try": True,
         "name": "Issue picker — gợi ý nhanh theo text",
         "ai": "Bước tìm ứng viên rẻ và nhanh trước khi search JQL đầy đủ.",
         "how": "query = chuỗi tự do; currentJQL để giới hạn phạm vi."},
        {"method": "POST", "path": "/rest/api/3/issue/bulkfetch", "try": False,
         "name": "Bulk fetch — lấy chi tiết hàng loạt",
         "ai": "Sau khi search ra danh sách key, lấy chi tiết tối đa 100 ticket/call thay vì gọi lẻ từng cái.",
         "how": 'Body: {"issueIdsOrKeys": ["SCRUM-5","SCRUM-6"], "fields": [...]}.'},
        {"method": "POST", "path": "/rest/api/3/jql/parse", "try": False,
         "name": "Validate JQL",
         "ai": "Nếu để AI tự sinh JQL: parse trước khi chạy, lỗi thì trả cho AI sửa — tránh request hỏng.",
         "how": 'Body: {"queries": ["project = SCRUM AND ..."]}.'},
        {"method": "GET", "path": "/rest/api/3/jql/autocompletedata", "try": True,
         "name": "Danh mục field/operator JQL",
         "ai": "Đưa vào prompt làm tài liệu tham chiếu để AI sinh JQL đúng cú pháp, đúng tên field của site.",
         "how": "Cache 1 lần."},
    ]},
    {"group": "4. Phán đoán & hành động (AI quyết → service làm)", "items": [
        {"method": "GET", "path": "/rest/api/3/issue/{key}/transitions", "try": True,
         "name": "Các bước chuyển hợp lệ",
         "ai": "AI chỉ được đề xuất chuyển trạng thái trong danh sách này — workflow mỗi project khác nhau, không đoán được.",
         "how": "Lấy transition id ở đây rồi POST cùng đường dẫn để thực hiện."},
        {"method": "GET", "path": "/rest/api/3/user/assignable/search?issueKey={key}", "try": True,
         "name": "Người được phép gán",
         "ai": "AI đề xuất assignee phải nằm trong danh sách này, nếu không PUT assignee sẽ 400.",
         "how": "Trả accountId — Jira Cloud chỉ nhận accountId, không nhận username."},
        {"method": "GET", "path": "/rest/api/3/mypermissions?projectKey={project}&permissions=ASSIGN_ISSUES,TRANSITION_ISSUES,ADD_COMMENTS,EDIT_ISSUES", "try": True,
         "name": "Quyền của tài khoản bot",
         "ai": "Service tự kiểm tra đủ quyền làm hành động AI đề xuất không, trước khi thử và thất bại.",
         "how": "permissions = danh sách permission key cách nhau dấu phẩy."},
        {"method": "GET", "path": "/rest/api/3/project/{project}/components", "try": True,
         "name": "Components + lead",
         "ai": "Mỗi component có 'lead' (người phụ trách) — nguồn cho quy ước 'bug component X → giao lead X'.",
         "how": "Không tham số."},
        {"method": "GET", "path": "/rest/api/3/project/{project}/role", "try": True,
         "name": "Vai trò trong project",
         "ai": "Ai là Developer/Admin của project — gợi ý assignee theo vai trò.",
         "how": "Trả URL từng role, gọi tiếp để lấy thành viên."},
        {"method": "GET", "path": "/rest/api/3/groupuserpicker?query=hai", "try": True,
         "name": "Tìm người theo tên",
         "ai": "Resolve tên người được nhắc trong comment ('giao cho anh Nam') → accountId.",
         "how": "query = tên gần đúng."},
        {"method": "POST", "path": "/rest/api/3/issue/{key}/comment", "try": False,
         "name": "Ghi comment (hành động phổ biến nhất)",
         "ai": "AI ghi kết quả phân tích + link ticket tương tự + gợi ý cách fix vào ticket.",
         "how": "Body comment phải là ADF. An toàn nhất trong các hành động — nên là default."},
        {"method": "PUT", "path": "/rest/api/3/issue/{key}/assignee", "try": False,
         "name": "Gán người xử lý", "ai": "Thực thi đề xuất assignee của AI.",
         "how": 'Body: {"accountId": "..."}.'},
        {"method": "POST", "path": "/rest/api/3/issue/{key}/transitions", "try": False,
         "name": "Chuyển trạng thái", "ai": "Thực thi đề xuất chuyển workflow của AI.",
         "how": 'Body: {"transition": {"id": "41"}}. Response 204 rỗng.'},
        {"method": "PUT", "path": "/rest/api/3/issue/{key}/properties/ai-state", "try": False,
         "name": "Issue property — bộ nhớ ẩn của AI trên ticket",
         "ai": "Lưu 'ticket này AI xử lý chưa, kết quả gì' ngay trên ticket mà không làm bẩn field hiển thị → giải quyết webhook bắn trùng (idempotency).",
         "how": "PUT body JSON bất kỳ; GET cùng đường dẫn để đọc lại."},
    ]},
    {"group": "5. Danh mục ngữ cảnh (cache 1 lần khi khởi động)", "items": [
        {"method": "GET", "path": "/rest/api/3/priority", "try": True,
         "name": "Các mức priority", "ai": "AI đề xuất đổi priority phải dùng giá trị trong này.", "how": ""},
        {"method": "GET", "path": "/rest/api/3/resolution", "try": True,
         "name": "Các loại resolution", "ai": "Hiểu 'Fixed' khác 'Won't Fix' khi đọc ticket đã đóng.", "how": ""},
        {"method": "GET", "path": "/rest/api/3/statuses/search?projectId={projectId}", "try": False,
         "name": "Statuses của site/project", "ai": "Bản đồ trạng thái + statusCategory (new/indeterminate/done).", "how": "Hoặc GET /project/{key}/statuses theo issue type."},
        {"method": "GET", "path": "/rest/api/3/project/{project}/statuses", "try": True,
         "name": "Workflow theo issue type của project", "ai": "Bug và Task có thể đi workflow khác nhau — AI cần biết trước khi đề xuất.", "how": ""},
        {"method": "GET", "path": "/rest/api/3/label", "try": True,
         "name": "Toàn bộ labels", "ai": "AI gắn label nên chọn label có sẵn thay vì sinh mới tùy tiện.", "how": ""},
        {"method": "GET", "path": "/rest/api/3/project/{project}/versions", "try": True,
         "name": "Versions của project", "ai": "Ngữ cảnh affectedVersion/fixVersion khi AI đề xuất gắn bản phát hành.", "how": ""},
    ]},
]

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
