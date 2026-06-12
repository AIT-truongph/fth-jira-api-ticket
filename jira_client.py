# Jira Cloud REST API client toi gian - Python thuan, khong can thu vien ngoai.
# Cau hinh qua bien moi truong:
#   JIRA_SITE      vd: https://your-site.atlassian.net
#   JIRA_EMAIL     email tai khoan Atlassian
#   JIRA_API_TOKEN token tao tai id.atlassian.com (hoac de trong file API_token.txt canh repo)
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

SITE = os.environ.get("JIRA_SITE", "https://haitruong.atlassian.net").rstrip("/")
EMAIL = os.environ.get("JIRA_EMAIL", "haitruong7592@gmail.com")


def _load_token():
    if os.environ.get("JIRA_API_TOKEN"):
        return os.environ["JIRA_API_TOKEN"]
    for p in (Path(__file__).parent / "API_token.txt",
              Path(__file__).parent.parent / "API_token.txt"):
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    raise RuntimeError("Thieu token: set JIRA_API_TOKEN hoac tao file API_token.txt (da gitignore)")


import base64
AUTH = base64.b64encode(f"{EMAIL}:{_load_token()}".encode()).decode()

TRACE_HOOK = None  # web_demo gan ham (method, path, params, ms, bytes) vao day de ghi trace


def call(method, path, params=None, body=None):
    """Goi 1 REST API cua Jira, tra ve JSON (hoac None neu response rong)."""
    url = f"{SITE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Basic {AUTH}")
    req.add_header("Accept", "application/json")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    t0 = time.time()
    with urllib.request.urlopen(req, data, timeout=30) as resp:
        raw = resp.read().decode()
        if TRACE_HOOK:
            TRACE_HOOK(method, path, params or body, int((time.time() - t0) * 1000), len(raw))
        return json.loads(raw) if raw.strip() else None


def adf_to_text(node):
    """Trich text thuan tu Atlassian Document Format (description/comment cua API v3)."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    parts = []
    if node.get("type") == "text":
        parts.append(node.get("text", ""))
    for child in node.get("content", []) or []:
        parts.append(adf_to_text(child))
    return "".join(parts) + ("\n" if node.get("type") == "paragraph" else "")
