# Ghep chuoi API Jira thanh "AI context" hoan chinh cho 1 ticket.
# Day la CONTRACT giua service Jira va AI team:
#   input  = issue key (lay tu webhook)
#   output = JSON: het thong tin ticket + ticket tuong tu da giai quyet + hanh dong kha dung
# Chay doc lap: python ai_context.py SCRUM-7
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from jira_client import adf_to_text, call

STOPWORDS = {"when", "with", "for", "the", "a", "an", "of", "to", "in", "on",
             "fails", "occurs", "error", "errors", "after", "during", "too", "is", "not"}


def simplify_custom(value):
    """Rut gon gia tri custom field phuc tap (object/list) thanh dang AI doc duoc."""
    if isinstance(value, dict):
        return value.get("value") or value.get("name") or value
    if isinstance(value, list):
        return [simplify_custom(v) for v in value]
    return value


def normalize_issue(key, with_comments=True):
    """GET issue + comments -> dict gon, ADF da chuyen thanh text, custom field da dich ten."""
    issue = call("GET", f"/rest/api/3/issue/{key}",
                 params={"expand": "names,changelog", "fields": "*all"})
    f = issue["fields"]
    names = issue.get("names", {})

    custom = {}
    for k, v in f.items():
        if k.startswith("customfield_") and v not in (None, [], ""):
            custom[names.get(k, k)] = simplify_custom(v)

    out = {
        "key": issue["key"],
        "type": f["issuetype"]["name"],
        "summary": f.get("summary"),
        "description": adf_to_text(f.get("description")).strip() or None,
        "status": f["status"]["name"],
        "status_category": f["status"]["statusCategory"]["key"],
        "resolution": (f.get("resolution") or {}).get("name"),
        "priority": (f.get("priority") or {}).get("name"),
        "labels": f.get("labels", []),
        "components": [c["name"] for c in f.get("components", [])],
        "assignee": (f.get("assignee") or {}).get("displayName"),
        "reporter": (f.get("reporter") or {}).get("displayName"),
        "created": f.get("created"),
        "updated": f.get("updated"),
        "custom_fields": custom,
        "attachments": [{"id": a["id"], "filename": a["filename"],
                         "mimeType": a["mimeType"], "size": a["size"]}
                        for a in f.get("attachment", [])],
        "linked_issues": [
            {"type": l["type"]["name"],
             "key": (l.get("inwardIssue") or l.get("outwardIssue", {})).get("key")}
            for l in f.get("issuelinks", [])
        ],
        "recent_changes": [
            {"by": h.get("author", {}).get("displayName"),
             "at": h.get("created"),
             "items": [f"{i['field']}: {i.get('fromString')} -> {i.get('toString')}"
                       for i in h.get("items", [])]}
            for h in issue.get("changelog", {}).get("histories", [])[-5:]
        ],
    }
    if with_comments:
        cm = call("GET", f"/rest/api/3/issue/{key}/comment", params={"orderBy": "created"})
        out["comments"] = [
            {"by": c["author"]["displayName"], "at": c["created"],
             "text": adf_to_text(c["body"]).strip()}
            for c in cm.get("comments", [])
        ]
    return out


def find_similar_resolved(ticket, max_results=5):
    """Tim ticket DA GIAI QUYET tuong tu: khop label HOAC khop text tu summary.
    Luu y: text ~ la keyword search (khong semantic) va KHONG quet labels."""
    kw = " ".join(w for w in (ticket["summary"] or "").lower().split()
                  if w not in STOPWORDS)
    conds = f'text ~ "{kw}"'
    if ticket["labels"]:
        conds = f"({conds} OR labels in ({', '.join(ticket['labels'])}))"
    project = ticket["key"].split("-")[0]
    found = call("POST", "/rest/api/3/search/jql", body={
        "jql": f"project = {project} AND statusCategory = Done AND {conds} "
               f"AND key != {ticket['key']} ORDER BY created DESC",
        "maxResults": max_results,
        "fields": ["summary"],
    })
    return [normalize_issue(i["key"]) for i in found.get("issues", [])]


def get_allowed_actions(key):
    """Pham vi hanh dong hop le - AI chi duoc de xuat trong day."""
    trans = call("GET", f"/rest/api/3/issue/{key}/transitions")
    assignable = call("GET", "/rest/api/3/user/assignable/search",
                      params={"issueKey": key, "maxResults": 20})
    return {
        "transitions": [{"id": t["id"], "name": t["name"], "to": t["to"]["name"]}
                        for t in trans.get("transitions", [])],
        "assignable_users": [{"accountId": u["accountId"], "name": u["displayName"]}
                             for u in assignable],
    }


def build_context(key):
    ticket = normalize_issue(key)
    return {
        "ticket": ticket,
        "similar_resolved": find_similar_resolved(ticket),
        "allowed_actions": get_allowed_actions(key),
    }


if __name__ == "__main__":
    print(json.dumps(build_context(sys.argv[1] if len(sys.argv) > 1 else "SCRUM-7"),
                     indent=2, ensure_ascii=False))
