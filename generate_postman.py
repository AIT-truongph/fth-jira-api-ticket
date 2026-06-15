# Sinh Postman collection tu catalog_data.py - luon khop voi danh muc tren web.
# Chay: python generate_postman.py  -> Jira_AI.postman_collection.json
# Import vao Postman -> dien bien apiToken (tab Variables) la goi duoc ngay.
import json
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qsl

sys.path.insert(0, str(Path(__file__).parent))
from catalog_data import CATALOG

OUT = Path(__file__).parent / "Jira_AI.postman_collection.json"

# Placeholder trong catalog -> bien Postman
PLACEHOLDERS = {
    "{key}": "{{issueKey}}",
    "{project}": "{{projectKey}}",
    "{projectId}": "{{projectId}}",
    "{boardId}": "{{boardId}}",
    "{id}": "{{attachmentId}}",
    "{fieldId}": "{{fieldId}}",
}

# Body mau cho cac API ghi (de goi duoc ngay sau khi import)
BODIES = {
    ("POST", "/rest/webhooks/1.0/webhook"): {
        "name": "AI ticket demo",
        "url": "https://<tunnel-cua-ban>.trycloudflare.com/jira-webhook",
        "events": ["jira:issue_created", "jira:issue_updated", "comment_created"],
        "filters": {"issue-related-events-section": "project = {{projectKey}}"},
        "excludeBody": False,
    },
    ("POST", "/rest/api/3/webhook"): {
        "url": "https://example.com/webhook",
        "webhooks": [{"events": ["jira:issue_created"], "jqlFilter": "project = {{projectKey}}"}],
    },
    ("POST", "/rest/api/3/issue/bulkfetch"): {
        "issueIdsOrKeys": ["{{issueKey}}"],
        "fields": ["summary", "status", "resolution", "labels"],
    },
    ("POST", "/rest/api/3/search/approximate-count"): {
        "jql": "project = {{projectKey}} AND statusCategory = Done",
    },
    ("POST", "/rest/api/3/jql/parse"): {
        "queries": ['project = {{projectKey}} AND text ~ "timeout"'],
    },
    ("POST", "/rest/api/3/jql/match"): {
        "jqls": ["project = {{projectKey}} AND statusCategory = Done"],
        "issueIds": [10000],
    },
    ("POST", "/rest/api/3/search/jql"): {
        "jql": 'project = {{projectKey}} AND statusCategory = Done AND text ~ "timeout"',
        "fields": ["summary", "status", "resolution", "labels"],
        "maxResults": 50,
    },
    ("POST", "/rest/api/3/comment/list"): {"ids": [10000, 10001]},
    ("POST", "/rest/api/3/changelog/bulkfetch"): {
        "issueIdsOrKeys": ["{{issueKey}}"],
    },
    ("POST", "/rest/api/3/issue/{key}/comment"): {
        "body": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [
                {"type": "text", "text": "Phan tich tu AI: ticket tuong tu SCRUM-5 da fix bang cach tang pool size."}]}]},
    },
    ("PUT", "/rest/api/3/issue/{key}/assignee"): {"accountId": "{{accountId}}"},
    ("POST", "/rest/api/3/issue/{key}/transitions"): {"transition": {"id": "41"}},
    ("PUT", "/rest/api/3/issue/{key}"): {"fields": {"labels": ["ai-reviewed"]}},
    ("POST", "/rest/api/3/issue/{key}/notify"): {
        "subject": "Ticket can chu y",
        "textBody": "AI phat hien ticket nay nghi trung voi ticket cua ban.",
        "to": {"users": [{"accountId": "{{accountId}}"}]},
    },
    ("POST", "/rest/api/3/issueLink"): {
        "type": {"name": "Duplicate"},
        "inwardIssue": {"key": "{{issueKey}}"},
        "outwardIssue": {"key": "SCRUM-5"},
    },
    ("PUT", "/rest/api/3/issue/{key}/properties/ai-state"): {
        "processed_at": "2026-06-12T15:00:00+07:00",
        "action": "commented",
        "similar": ["SCRUM-5"],
    },
}


import re

# ===== Tra cuu metadata chinh thong (tag = ten folder, summary = ten request) =====
SWAGGER_CANDIDATES = [
    Path(__file__).parent.parent / "Full_APIs" / "swagger-jira-v3.json",
    Path(__file__).parent / "swagger-jira-v3.json",
]


def _canon(p):
    return re.sub(r"\{[^}]+\}", "{}", p.split("?")[0])


def load_official():
    """(method, canon_path) -> (tag, summary, official_path) tu swagger Atlassian."""
    for sw_path in SWAGGER_CANDIDATES:
        if sw_path.exists():
            sw = json.loads(sw_path.read_text(encoding="utf-8"))
            out = {}
            for path, ops in sw["paths"].items():
                for m, op in ops.items():
                    if m not in ("get", "post", "put", "delete"):
                        continue
                    out[(m.upper(), _canon(path))] = (
                        (op.get("tags") or ["?"])[0], op.get("summary", ""), path)
            return out
    print("  (canh bao) khong tim thay swagger -> dung ten trong catalog")
    return {}


OFFICIAL = load_official()

# Map tay 6 API ngoai swagger Platform: (method, canon_path) -> (tag, summary, doc_url)
MANUAL = {
    ("POST", "/rest/webhooks/1.0/webhook"): (
        "Webhooks (legacy admin)", "Register webhook",
        "https://developer.atlassian.com/cloud/jira/platform/webhooks/#registering-a-webhook-using-the-jira-rest-api"),
    ("GET", "/rest/webhooks/1.0/webhook"): (
        "Webhooks (legacy admin)", "Get registered webhooks",
        "https://developer.atlassian.com/cloud/jira/platform/webhooks/"),
    ("PUT", "/rest/api/3/issue/{}/properties/ai-state"): (
        "Issue properties", "Set issue property",
        "https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-properties/#api-rest-api-3-issue-issueidorkey-properties-propertykey-put"),
    ("GET", "/rest/agile/1.0/board"): (
        "Agile: Board", "Get all boards",
        "https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/#api-rest-agile-1-0-board-get"),
    ("GET", "/rest/agile/1.0/board/{}/sprint"): (
        "Agile: Board", "Get all sprints (by board)",
        "https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/#api-rest-agile-1-0-board-boardid-sprint-get"),
    ("GET", "/rest/servicedeskapi/request/{}"): (
        "Service Desk: Request", "Get customer request",
        "https://developer.atlassian.com/cloud/jira/service-desk/rest/api-group-request/#api-rest-servicedeskapi-request-issueidorkey-get"),
}


def doc_url(tag, official_path, method):
    slug = tag.lower().replace(" ", "-")
    anchor = "api-" + official_path.lower().replace("{", "").replace("}", "").strip("/").replace("/", "-") + "-" + method.lower()
    return f"https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-{slug}/#{anchor}"


def resolve_meta(item):
    """Tra ve (tag, summary, doc_url) chinh thong cho 1 catalog item."""
    key = (item["method"], _canon(item["path"]))
    if key in OFFICIAL:
        tag, summ, official_path = OFFICIAL[key]
        return tag, summ, doc_url(tag, official_path, item["method"])
    if key in MANUAL:
        return MANUAL[key]
    return "Khac", item["name"], ""  # fallback


def to_postman_url(path_tpl):
    """'/rest/api/3/issue/{key}?expand=...' -> postman url object voi bien."""
    for ph, var in PLACEHOLDERS.items():
        path_tpl = path_tpl.replace(ph, var)
    raw = "{{baseUrl}}" + path_tpl
    parsed = urlparse(path_tpl)
    url = {
        "raw": raw,
        "host": ["{{baseUrl}}"],
        "path": [seg for seg in parsed.path.split("/") if seg],
    }
    if parsed.query:
        url["query"] = [{"key": k, "value": v} for k, v in parse_qsl(parsed.query)]
    return url


def build_request(item):
    bare_path = item["path"].split("?")[0]
    tag, summ, doc = resolve_meta(item)
    # Mo ta: khoi chinh thong (de doi chieu tai lieu Jira) + khoi giup gi cho AI
    desc = f"== JIRA DOC ==\nFolder: {tag}\nOperation: {summ}"
    if doc:
        desc += f"\nTai lieu: {doc}"
    desc += f"\n\n== GIUP GI CHO AI ==\n{item['ai']}"
    if item.get("how"):
        desc += f"\n\nCACH DUNG: {item['how']}"
    req = {
        "method": item["method"],
        "header": [{"key": "Accept", "value": "application/json"}],
        "url": to_postman_url(item["path"]),
        "description": desc,
    }
    body = BODIES.get((item["method"], bare_path))
    if body is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2, ensure_ascii=False),
                       "options": {"raw": {"language": "json"}}}
    # Ten request = ten operation chinh thong cua Jira (de khop doc)
    return {"name": summ or item["name"], "request": req}, tag


# Gom request vao folder theo TAG chinh thong, giu thu tu xuat hien
folders = {}
order = []
for g in CATALOG:
    for item in g["items"]:
        entry, tag = build_request(item)
        if tag not in folders:
            folders[tag] = []
            order.append(tag)
        folders[tag].append(entry)

collection = {
    "info": {
        "name": "Jira API cho AI (52 endpoints, folder & ten theo Jira doc)",
        "description": (
            "Danh muc API phuc vu flow: webhook -> AI doc ticket -> tim ticket tuong tu -> phan doan.\n"
            "Folder va ten request DAT THEO tai lieu chinh thong Jira (tag + operation summary) "
            "de doi chieu truc tiep voi developer.atlassian.com. Moi request co link tai lieu "
            "trong phan Description, kem ghi chu 'GIUP GI CHO AI'.\n\n"
            "CACH DUNG: tab Variables -> dien apiToken "
            "(id.atlassian.com/manage-profile/security/api-tokens), sua baseUrl/username/issueKey -> Send."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "basic", "basic": [
        {"key": "username", "value": "{{username}}", "type": "string"},
        {"key": "password", "value": "{{apiToken}}", "type": "string"},
    ]},
    "variable": [
        {"key": "baseUrl", "value": "https://your-site.atlassian.net"},
        {"key": "username", "value": "your-email@example.com"},
        {"key": "apiToken", "value": ""},
        {"key": "issueKey", "value": "SCRUM-7"},
        {"key": "projectKey", "value": "SCRUM"},
        {"key": "projectId", "value": "10000"},
        {"key": "boardId", "value": "1"},
        {"key": "attachmentId", "value": "10000"},
        {"key": "fieldId", "value": "customfield_10020"},
        {"key": "accountId", "value": ""},
    ],
    "item": [{"name": tag, "item": folders[tag]} for tag in order],
}

OUT.write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")
n = sum(len(f["item"]) for f in collection["item"])
print(f"Da sinh {OUT.name}: {len(collection['item'])} folder (theo Jira doc), {n} request")
