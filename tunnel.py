# tunnel.py - tu dong: chay cloudflared quick tunnel + cap nhat webhook Jira tro ve URL moi.
# web_demo.py goi start_tunnel() roi update_webhook() luc khoi dong, nen chi can `python web_demo.py`.
import atexit
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

from jira_client import EMAIL, call

# --- Cau hinh rieng theo tung dev (qua bien moi truong, deu co mac dinh hop ly) ---
# Project de loc su kien webhook. Moi site Jira co the dung project key khac nhau.
PROJECT = os.environ.get("JIRA_PROJECT", "SCRUM")

# Ten webhook RIENG theo tung dev -> nhieu dev dung chung 1 site khong giam len nhau.
# Mac dinh lay theo email da cau hinh (phan truoc @); khong co thi lay theo ten may.
_ident = EMAIL.split("@")[0] if EMAIL and "@" in EMAIL else socket.gethostname()
WEBHOOK_NAME = os.environ.get("JIRA_WEBHOOK_NAME") or f"AI ticket demo - {_ident}"

EVENTS = ["jira:issue_created", "jira:issue_updated", "comment_created", "comment_updated"]

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_PROC = None  # giu tham chieu de process khong bi thu gom + de terminate luc thoat


def _find_cloudflared():
    exe = shutil.which("cloudflared")
    if exe:
        return exe
    for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe"):
        if Path(p).exists():
            return p
    raise RuntimeError("Khong tim thay cloudflared (khong co trong PATH va thu muc mac dinh).")


def _drain(proc):
    # Tiep tuc doc log cloudflared o nen de buffer khong bi day lam treo tunnel.
    for _ in iter(proc.stdout.readline, ""):
        pass


def start_tunnel(port, timeout=40):
    """Chay cloudflared quick tunnel tro ve localhost:{port}; tra ve public URL."""
    global _PROC
    exe = _find_cloudflared()
    _PROC = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    atexit.register(stop_tunnel)
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = _PROC.stdout.readline()
        if not line:
            if _PROC.poll() is not None:
                raise RuntimeError("cloudflared thoat som truoc khi cap URL.")
            continue
        m = _URL_RE.search(line)
        if m:
            threading.Thread(target=_drain, args=(_PROC,), daemon=True).start()
            return m.group(0)
    stop_tunnel()
    raise RuntimeError(f"Het {timeout}s cho ma cloudflared chua cap URL.")


def stop_tunnel():
    global _PROC
    if _PROC and _PROC.poll() is None:
        _PROC.terminate()
    _PROC = None


def update_webhook(public_url):
    """Cap nhat (hoac tao moi) webhook tro ve {public_url}/jira-webhook. Tra ve mo ta hanh dong."""
    target = public_url.rstrip("/") + "/jira-webhook"
    body = {
        "name": WEBHOOK_NAME,
        "url": target,
        "events": EVENTS,
        "filters": {"issue-related-events-section": f"project = {PROJECT}"},
        "excludeBody": False,
    }
    for wh in call("GET", "/rest/webhooks/1.0/webhook") or []:
        if wh.get("name") == WEBHOOK_NAME:
            wid = wh.get("self", "").rstrip("/").split("/")[-1]
            call("PUT", f"/rest/webhooks/1.0/webhook/{wid}", body=body)
            return f"cap nhat webhook #{wid}"
    created = call("POST", "/rest/webhooks/1.0/webhook", body=body)
    return f"tao webhook moi ({created.get('self')})"
