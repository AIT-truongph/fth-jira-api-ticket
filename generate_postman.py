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
    req = {
        "method": item["method"],
        "header": [{"key": "Accept", "value": "application/json"}],
        "url": to_postman_url(item["path"]),
        "description": f"GIUP GI CHO AI: {item['ai']}" + (f"\n\nCACH DUNG: {item['how']}" if item.get("how") else ""),
    }
    body = BODIES.get((item["method"], bare_path))
    if body is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2, ensure_ascii=False),
                       "options": {"raw": {"language": "json"}}}
    return {"name": f"{item['name']}", "request": req}


collection = {
    "info": {
        "name": "Jira API cho AI - 45 endpoints (sinh tu catalog_data.py)",
        "description": (
            "Danh muc API phuc vu flow: webhook -> AI doc ticket -> tim ticket tuong tu -> phan doan.\n"
            "Khop 100% voi tab 'Danh muc API' tren web demo.\n\n"
            "CACH DUNG: vao tab Variables cua collection, dien apiToken "
            "(tao tai id.atlassian.com/manage-profile/security/api-tokens), "
            "sua baseUrl/username/issueKey neu can -> Send.\n"
            "Mo ta moi request ghi ro API do GIUP GI CHO AI."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "basic", "basic": [
        {"key": "username", "value": "{{username}}", "type": "string"},
        {"key": "password", "value": "{{apiToken}}", "type": "string"},
    ]},
    "variable": [
        {"key": "baseUrl", "value": "https://haitruong.atlassian.net"},
        {"key": "username", "value": "haitruong7592@gmail.com"},
        {"key": "apiToken", "value": ""},
        {"key": "issueKey", "value": "SCRUM-7"},
        {"key": "projectKey", "value": "SCRUM"},
        {"key": "projectId", "value": "10000"},
        {"key": "boardId", "value": "1"},
        {"key": "attachmentId", "value": "10000"},
        {"key": "accountId", "value": ""},
    ],
    "item": [
        {"name": g["group"], "item": [build_request(i) for i in g["items"]]}
        for g in CATALOG
    ],
}

OUT.write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")
n = sum(len(g["item"]) for g in collection["item"])
print(f"Da sinh {OUT.name}: {len(collection['item'])} folder, {n} request")
