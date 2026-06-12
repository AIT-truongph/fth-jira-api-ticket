# Dang ky admin webhook vao Jira Cloud (can quyen admin tren site)
# Chay: python register_webhook.py <public_url> [project_key]
#   vd: python register_webhook.py https://abc.trycloudflare.com SCRUM
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import call

if len(sys.argv) < 2:
    raise SystemExit("Cach dung: python register_webhook.py <public_url> [project_key]")

url = sys.argv[1].rstrip("/") + "/jira-webhook"
project = sys.argv[2] if len(sys.argv) > 2 else "SCRUM"

existing = call("GET", "/rest/webhooks/1.0/webhook") or []
for wh in existing:
    print(f"Da co: {wh.get('name')} -> {wh.get('url')} (enabled={wh.get('enabled')}, self={wh.get('self')})")

created = call("POST", "/rest/webhooks/1.0/webhook", body={
    "name": f"AI ticket demo - {project}",
    "url": url,
    "events": ["jira:issue_created", "jira:issue_updated",
               "comment_created", "comment_updated"],
    "filters": {"issue-related-events-section": f"project = {project}"},
    "excludeBody": False,
})
print(f"\nDang ky thanh cong: {created.get('name')}")
print(f"  url    : {created.get('url')}")
print(f"  events : {created.get('events')}")
print(f"  self   : {created.get('self')}  (DELETE vao URL nay de go webhook)")
