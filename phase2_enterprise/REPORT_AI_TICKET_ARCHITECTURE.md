# Technical Report — AI-Driven Action Inference over Jira Service Management at Enterprise Scale

**Scope:** Jira Cloud + Jira Service Management (JSM) APIs, data retrieval, synchronization strategy, and AI integration architecture for inferring *next best action* from historical resolutions. Model selection is intentionally out of scope.

**Context:** Hundreds of thousands of historical JSM tickets; Jira is the system of record; the system must evolve toward autonomous action; **reliability outranks automation**.

> ⚠️ **Read first:** this report is the **build** option. JSM already ships native AI that covers ~80% of this use case (Draft Replies, Service Request Helper, AI Suggestions Panel) — **evaluate native before building** ([../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md), [Build vs Buy](REPORT_BUILD_VS_BUY.md)). Use this design only for the slice native cannot deliver.

---

## 0. Executive summary

The core reframing that drives every architectural decision: this is **not** a duplicate-detection problem, it is a **case-based reasoning (CBR)** problem. The unit of knowledge is not "ticket ABC-123" — it is a distilled *resolution case*:

```
{ symptom, root_cause, action_taken, outcome, resolver, resolution_time, success_signal }
```

Jira is excellent as a **system of record and action surface**, but it is a poor **retrieval engine** for this use case: its `text ~` operator is lexical (Lucene keyword matching), there is no semantic search in the REST API, and deep pagination over hundreds of thousands of issues is rate-limited and slow. Therefore the recommended design is:

> **Jira = source of truth + action API.**
> **A separate, derived knowledge store (structured cases + hybrid search: BM25 + vector + metadata filter) = retrieval brain.**
> **An agentic reasoning layer with tool-calling = decision maker, operating inside a hard "allowed-actions" envelope returned by Jira itself.**
> **A human-approval gate governed by confidence thresholds and a full audit trail = the reliability guarantee.**

The rest of this report justifies and details that design.

---

## 1. Jira API inventory

Two API families live on the same site and share the same authentication:

- **Platform API** — `/rest/api/3/…` — issues, comments, changelog, search, transitions, users.
- **Jira Service Management API** — `/rest/servicedeskapi/…` — requests, SLAs, approvals, queues, organizations, public vs internal comments.

> **Authentication for backend services:** Basic auth with `email:api_token` (token from id.atlassian.com) for a dedicated **bot/service account**, or OAuth 2.0 (3LO) scopes `read:jira-work` / `write:jira-work` / `read:servicedesk-request` / `write:servicedesk-request` for distributed apps. Never use a personal token in production; provision a least-privilege service account scoped to the relevant projects.

> **Global cross-cutting constraints** (apply to nearly every call below):
> - **Rate limiting is cost-budget based per tenant.** There is no fixed RPS; you receive `429` with `Retry-After`. At enterprise scale this is the dominant scalability constraint — design for backpressure, queuing, and exponential backoff from day one.
> - **`accountId` only.** Username/email were removed for GDPR. Every people-related field/parameter uses `accountId`.
> - **ADF (Atlassian Document Format, JSON) bodies.** `description` and comment bodies are ADF in API v3; webhook payloads deliver them as plain text. Parse both.
> - **Empty `204` responses** on several write endpoints (transitions, assignee). Don't blindly `JSON.parse`.

### 1.1 Issue retrieval

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/issue/{key}` | Full issue: fields, custom fields, links, subtasks, attachment metadata, (optional) changelog. Central read. | *Browse projects* | `expand=renderedFields,names,changelog`; not paginated but a huge issue can be large. | 1 call/issue. Cache; request only needed `fields=` to cut payload. |
| `POST /rest/api/3/issue/bulkfetch` | Up to **100** issues in one call. | *Browse projects* | Hard cap 100 ids/call. | The right tool for hydrating search results; batches of 100. |
| `GET /rest/api/3/issue/createmeta/{projectIdOrKey}/issuetypes[/{id}]` | Creatable issue types + required fields. | *Create issues* | Paginated. | Only if AI creates issues. |

### 1.2 Comments

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/issue/{key}/comment` | All comments (the richest resolution signal). | *Browse projects* | `startAt`/`maxResults`; `orderBy=created`. | Paginate per issue; comments are where root-cause/fix live. |
| `POST /rest/api/3/comment/list` | Comments by ID, bulk. | *Browse projects* | Paginated. | Bulk hydrate when comment IDs already known. |
| `POST /rest/api/3/issue/{key}/comment` | **Add comment** (primary AI action). ADF body. `visibility` can restrict to a role/group. | *Add comments* | — | The safest write action; make it the default. |

### 1.3 Changelog / history

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/issue/{key}/changelog` | Full field-change history (status flow, reassignments, reopens). | *Browse projects* | Paginated, oldest-first. | Or `expand=changelog` on Get issue to save a call. |
| `POST /rest/api/3/changelog/bulkfetch` | Changelogs for many issues. | *Browse projects* | Paginated. | Use during bulk historical ingestion. |

> History is **load-bearing for case extraction**: the transition from `In Progress → Resolved` plus the comment near that timestamp is the "action_taken / outcome" signal. Reopen counts indicate failed resolutions (negative training signal).

### 1.4 Attachments

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/attachment/content/{id}` | **Download file bytes** (logs, screenshots). Get issue returns metadata only. | *Browse projects* | Supports `Range`. | Fetch lazily; can be large. Gate by mime/size. |
| `GET /rest/api/3/attachment/thumbnail/{id}` | Thumbnail for images. | *Browse projects* | — | Cheaper for vision pre-screen. |
| `GET /rest/api/3/attachment/{id}/expand/human` | List files inside a zip without downloading. | *Browse projects* | — | Avoids pulling large archives. |

### 1.5 Linked issues

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/issue/{key}` (`fields=issuelinks`) | Existing links (duplicates/relates/blocks) come inline. | *Browse projects* | Inline array. | No extra call needed for reads. |
| `GET /rest/api/3/issueLinkType` | Valid link types on the site. | *Browse projects* | Small. | Cache. |
| `POST /rest/api/3/issueLink` | Create a link (AI marks "duplicates"/"relates to"). | *Link issues* | — | Write action. |

### 1.6 User information

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/user/assignable/search?issueKey=` | Users who **can** be assigned. | *Browse projects* | Paginated. | **Mandatory before proposing assignee** — assigning outside this list is `400`. |
| `GET /rest/api/3/groupuserpicker?query=` | Resolve a name mentioned in a comment → `accountId`. | *Browse users* | Paginated. | For "@mention the SME" actions. |
| `GET /rest/api/3/myself` | Bot's own `accountId`. | Access Jira | — | Use to filter out the bot's own comments (avoid self-feedback loops). |

### 1.7 Search (JQL)

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `POST /rest/api/3/search/jql` | **Enhanced JQL search** (current). | *Browse projects* | **JQL must be bounded**; token pagination via `nextPageToken` (no `startAt`/`total`); page `maxResults` ≈ 50–100, fewer if many fields requested. | The old `GET/POST /rest/api/3/search` (offset-based, 10k cap) **is removed**. Token pagination scales but you cannot random-access a page; `text ~` is lexical only. |
| `POST /rest/api/3/search/approximate-count` | Estimated count for a JQL. | *Browse projects* | Bounded JQL. | Cheap pre-check before fetching. |
| `GET /rest/api/3/issue/picker?query=` | Fast typeahead candidates. | *Browse projects* | Small. | Cheap first-pass candidate finder. |
| `POST /rest/api/3/jql/parse`, `GET /rest/api/3/jql/autocompletedata` | Validate AI-generated JQL; field/operator reference. | None / Access Jira | — | Guardrail when the LLM writes JQL. |

> **Key limitation for this project:** JQL is the right tool for the **initial bulk export** and for **bounded metadata filtering** ("project = X AND statusCategory = Done AND created >= -2y"), but it is **not** the similarity engine. Relevance ranking must happen in the external search layer (§3).

### 1.8 Workflow transitions

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/issue/{key}/transitions` | **Allowed** transitions from the current status. | *Transition issues* | Inline. | Defines the legal action envelope; workflow differs per project. |
| `POST /rest/api/3/issue/{key}/transitions` | Execute a transition (optionally set fields/resolution). | *Transition issues* | `204` empty body. | The "move status"/"auto-resolve" action. |

### 1.9 Assignment

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `PUT /rest/api/3/issue/{key}/assignee` | Assign by `accountId` (`-1` = default, `null` = unassign). | *Assign issues* | `204`. | Pair with assignable/search. |

### 1.10 Watchers

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `GET /rest/api/3/issue/{key}/watchers` | Who's watching (interest signal). | *Browse projects* | Inline. | Minor context signal. |
| `POST /rest/api/3/issue/{key}/watchers` | Add a watcher (pull an SME in quietly). | *Manage watchers* | Body = `accountId` string. | Softer than reassigning. |

### 1.11 Resolution updates & notification

| API | Purpose | Permission | Limits / Pagination | Scalability |
|---|---|---|---|---|
| `PUT /rest/api/3/issue/{key}` | Edit fields (labels, priority, components, fixVersion, resolution via screen). `?notifyUsers=false` to avoid email spam on bulk edits. | *Edit issues* | — | Resolution is usually set **through a transition screen**, not a bare field edit. |
| `POST /rest/api/3/issue/{key}/notify` | Targeted email notification. | *Browse projects* | — | "Escalate / notify SME" action. |
| `PUT /rest/api/3/issue/{key}/properties/{key}` | **Issue properties** — hidden key/value store on the issue. | *Edit issues* | — | **Idempotency + audit:** store `{processed_at, action, confidence, model_version}` so retried webhooks don't double-act. |

### 1.12 Jira Service Management surface (JSM-specific)

JSM requests *are* Jira issues, so everything above applies. But JSM adds first-class concepts the Platform API doesn't expose well — critical for a **service desk** use case:

| API | Purpose | Permission | Notes / Scalability |
|---|---|---|---|
| `GET /rest/servicedeskapi/request/{id}` | Customer request view (request type, reporter, current status). | Agent on the service desk | Reporter-facing model. |
| `GET /rest/servicedeskapi/request/{id}/comment` | Comments **with `public` flag** (customer-visible vs internal). | Agent | **Essential:** an internal note ≠ a customer reply. AI must respect this boundary. |
| `POST /rest/servicedeskapi/request/{id}/comment` | Add public or internal comment. | Agent | Control `public: true/false` explicitly. |
| `GET /rest/servicedeskapi/request/{id}/sla` | SLA timers (time-to-first-response, time-to-resolution) + breach state. | Agent | **Prioritization signal**: near-breach tickets should jump the queue / escalate. |
| `GET /rest/servicedeskapi/request/{id}/approval`, `POST …/approval/{aid}` | Read/answer approvals. | Agent | Some auto-actions require an approval step. |
| `POST /rest/servicedeskapi/request/{id}/transition` | Transition with the customer-request semantics. | Agent | Reporter-facing transition names. |
| `GET /rest/servicedeskapi/servicedesk/{sdId}/queue/{qId}/issue` | Issues in a queue. | Agent | **Backfill source** for "what the team actually works." |
| `GET /rest/servicedeskapi/servicedesk/{sdId}/requesttype` | Request type catalog. | Agent | Maps to "team / category" — a routing target. |
| `GET /rest/servicedeskapi/organization` | Customer organizations. | Agent | Tenant/customer segmentation in retrieval. |

> Find `serviceDeskId` via `GET /rest/servicedeskapi/servicedesk` or `…/servicedesk/{projectKey}`.

### 1.13 Ingestion-relevant Platform endpoints (bulk/backfill)

| API | Purpose | Notes |
|---|---|---|
| `GET /rest/api/3/field` | Map `customfield_xxxxx` → name + type. | Cache once; required to interpret custom fields during ingestion. |
| `GET /rest/api/3/project/{key}/statuses`, `GET /rest/api/3/statuscategory` | Workflow + status→category map. | Distinguish "Done" (resolved) from "Closed without fix". |
| `GET /rest/api/3/project/{key}/components` | Component → `lead`. | Routing target ("component X → its lead"). |
| `GET /rest/api/3/priority`, `/resolution`, `/label` | Valid context values. | Constrain AI proposals to legal values. |

---

## 2. Historical knowledge extraction

The single most important design choice. Two ends of a spectrum, plus the recommended middle.

### Option A — Raw ticket storage (index everything as-is)

Concatenate summary + description + comments per ticket; chunk; embed; index.

- **Pros:** trivial pipeline; nothing is lost; fast to stand up; good recall.
- **Cons:** retrieves *tickets*, not *actions*. The LLM must re-derive "what worked" at inference time from noisy threads (chit-chat, dead ends, "any update?"). No success signal, no aggregation ("87% success"). Token-heavy. Exactly the "this looks like ABC-123" failure mode the brief rejects.

### Option B — Structured case extraction (CBR)

Run an **offline extraction pipeline** that distills each resolved ticket into a case:

```json
{
  "case_id": "PROJ-1234",
  "symptom": "VPN connection drops after ~30s on Windows clients",
  "root_cause": "vpnagent service hung after suspend/resume",
  "action_taken": "Restart vpnagent service; if persists, reinstall client 4.10+",
  "outcome": "resolved",            // derived from final status/resolution
  "reopened": false,                // negative signal if true
  "resolver": "accountId:...",
  "team": "Network Ops",
  "resolution_time_h": 2.5,
  "request_type": "VPN access",
  "components": ["VPN"],
  "evidence_refs": ["PROJ-1234#comment-55"],   // traceability back to Jira
  "confidence_extraction": 0.82
}
```

Then aggregate cases into **resolution patterns**:

```
symptom_cluster: "VPN connection failure"
→ action: "Restart vpnagent service"  | n=141 | success_rate=0.87 | median_time=1.2h
→ action: "Reinstall VPN client"      | n=38  | success_rate=0.71 | median_time=3.4h
```

- **Pros:** directly answers "what action, with what success rate." Aggregation yields the 87% statistic. Far smaller, cleaner context for the LLM. Negative signals (reopens) downweight bad actions. Each case is **traceable** back to Jira evidence (auditability).
- **Cons:** the extraction pipeline is itself an AI/NLP task with its own error rate; needs validation, schema evolution, and re-extraction when prompts improve; "success" is a heuristic (resolution + not reopened + SLA met).

### Recommended: **two-layer store** (raw + structured), built together

Keep **both**, derived from the same ingestion pass:

1. **Evidence layer (raw):** normalized ticket text/comments/changelog → chunked + embedded. Guarantees recall and grounding; nothing is lost.
2. **Case layer (structured):** extracted cases + aggregated patterns, each linking back to evidence chunks.

Retrieval queries the **case layer** for "what action worked" and uses the **evidence layer** to ground/cite. This is the configuration that produces *action recommendations with success rates* rather than *similar tickets*, while remaining fully auditable.

**Extraction quality controls:** human-spot-check a sample; store `confidence_extraction`; treat low-confidence cases as evidence-only (not pattern-eligible); version the extraction prompt and re-run incrementally.

---

## 3. Similarity retrieval — comparison and recommendation

| Approach | What it's good at | Weakness for this use case |
|---|---|---|
| **JQL `text ~`** | Bounded metadata filters; bulk export; live "is this still open?" checks. | Lexical only (no semantics, no synonyms); no relevance ranking; not for "find similar symptom." |
| **Full-text (DB / Lucene)** | Exact/keyword recall; cheap; good for IDs, error codes, stack-trace lines. | Misses paraphrase ("can't connect to VPN" vs "vpn keeps dropping"). |
| **OpenSearch / Elasticsearch** | Mature BM25 + filters + aggregations at scale; now also native **kNN vector**. Ops-friendly, hybrid in one engine. | You run/scale a cluster; embeddings still needed for vectors. |
| **Vector DB (pgvector / Qdrant / Pinecone / Weaviate)** | Semantic similarity; ANN at large scale; metadata filtering. | Pure vector misses exact tokens (error codes, host names); recency/quality need re-ranking; another system. |
| **Hybrid (BM25 + vector + metadata filter, then re-rank)** | Best of both: semantic recall **and** exact-token precision, filtered by project/type/recency, re-ranked by relevance × success-rate. | Most moving parts; needs a fusion/re-rank step (RRF or cross-encoder). |

### Recommendation by volume

- **100k+ tickets:** **PostgreSQL + `pgvector` + Postgres full-text**, fused in app code. One database, hybrid retrieval, minimal ops. Strongly preferred unless you already run OpenSearch.
- **500k+ tickets:** **OpenSearch/Elasticsearch with BM25 + dense vector (kNN)** in a single index, hybrid query + RRF fusion, plus a lightweight cross-encoder re-ranker. Best balance of scale, hybrid quality, and operational maturity.
- **1M+ tickets:** Same as 500k but with a **dedicated ANN tier** (Qdrant/Vespa, or OpenSearch with quantized vectors), sharding, and an explicit re-ranking stage. Vespa is worth evaluating where ranking sophistication matters.

> **Cross-cutting:** retrieve over the **case layer** (compact, deduplicated patterns) for action inference, and over the **evidence layer** for grounding. Always **filter then rank**: constrain by project/request-type/recency/resolved-only first, then semantic rank, then boost by `success_rate × n` and recency. Atlassian's own Rovo moved much of this into a **knowledge-graph (GraphRAG)** model rather than pure vector RAG — a relevant signal that structure + relationships beat naive chunk-and-embed at enterprise scale ([Atlassian semantic search](https://www.atlassian.com/blog/atlassian-engineering/advancing-rovo-semantic-search), [GraphRAG analysis](https://www.mindstudio.ai/blog/atlassian-rovo-knowledge-graph-vs-rag-arr-growth)).

---

## 4. Modern AI architecture — industry landscape & concepts

### What the leaders do (grounded)

- **Atlassian Rovo** — queries the **Teamwork Graph (knowledge graph / GraphRAG)** instead of token-heavy RAG over raw docs, with **hierarchical multi-agent orchestration** (an orchestrator routes to specialist sub-agents) and an enhanced multi-path RAG for deep research ([multi-agent orchestration](https://www.atlassian.com/blog/atlassian-engineering/how-rovo-embraces-multi-agent-orchestration), [deep research](https://www.atlassian.com/blog/atlassian-engineering/how-rovo-deep-research-works)). Takeaway: structure your knowledge and decompose the agent.
- **ServiceNow Now Assist** — AI agents operate **inside workflow records** (incident/case/change) wired to CMDB and ITIL processes; an issue can trigger downstream automated workflows. Takeaway: actions live inside the platform's workflow/permission model, not beside it ([comparison](https://www.eesel.ai/blog/salesforce-agentforce-vs-servicenow-ai)).
- **Salesforce Agentforce** — agents grounded in CRM objects + Data Cloud; deployment is a substantial data-ingestion/identity-resolution project. Takeaway: grounding data plumbing is the hard part, not the agent.
- **Zendesk AI** — single native platform, fast time-to-value; AI + ticketing + QA + WFM integrated. Takeaway: tight integration beats bolt-on for reliability.
- **Microsoft Copilot for Service** — overlays Dynamics/M365, retrieves from existing knowledge bases, drafts replies/actions with human-in-the-loop. Takeaway: assistive-first, autonomy earned over time.

**Convergent pattern:** ground in structured/enterprise knowledge → retrieve → reason with an agent that calls tools → keep a human gate → expand autonomy as confidence is proven.

### The concepts, mapped to this system

- **RAG** — retrieve relevant **cases + evidence** from the knowledge store and put them in context so the model reasons over *facts*, not memory. Here: hybrid retrieval over case/evidence layers, returning candidate actions with success rates and citations.
- **Agentic workflow** — not a single prompt but a **loop**: perceive (read ticket) → retrieve → plan → act → observe → repeat/stop. Enables multi-step handling (e.g., gather attachment, then search, then decide).
- **Tool calling** — the LLM doesn't touch Jira directly; it emits structured calls to a **constrained tool layer** (`get_ticket`, `search_cases`, `add_comment`, `propose_transition`, `assign`). Tools validate against Jira's allowed-actions envelope and permissions before executing.
- **Planning** — for non-trivial tickets, decompose: "classify → retrieve precedents → check SLA/approvals → choose action → check confidence → route to human or execute." Mirrors Rovo's multi-path decomposition.
- **Action execution** — the only place state changes. Every action goes through the tool layer, is checked against `transitions`/`assignable`/`permissions`/confidence policy, is written idempotently (issue property guard), and is logged for audit.

---

## 5. Production architecture

### 5.1 Component view

```
                          ┌──────────────────────────────────────────────┐
                          │                 JIRA CLOUD / JSM              │
                          │   (system of record + action API surface)    │
                          └───────┬───────────────────────────────▲──────┘
                       webhooks   │ (trigger: issue.key only)      │ actions (tool layer)
                                  ▼                                │
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ A. EVENT INGRESS                                                                    │
   │   Webhook receiver → verify/dedupe → enqueue (Kafka/SQS).  Idempotency via         │
   │   issue-property guard. Webhooks are a BELL, not data (order not guaranteed,        │
   │   comment payload is reduced) → always re-fetch via GET issue.                      │
   └───────────────┬────────────────────────────────────────────────────────────────────┘
                   ▼
   ┌──────────────────────────────────────────────┐     ┌──────────────────────────────┐
   │ B. INGESTION / SYNC                            │     │ B'. BACKFILL (one-time + CDC)│
   │   Live: per-event hydrate (issue, comments,    │     │   Bulk export historical via │
   │   changelog, attachments, JSM sla/approval).   │     │   POST /search/jql (token    │
   │   Normalize ADF→text, resolve accountIds &     │     │   pagination) + bulkfetch     │
   │   customfields. Emit normalized ticket doc.    │     │   (100/call). Respect 429.    │
   └───────────────┬───────────────────────────────┘     └───────────────┬──────────────┘
                   ▼                                                       ▼
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ C. KNOWLEDGE STORE (derived; Jira stays source of truth)                           │
   │   • Evidence layer: normalized text/comments/changelog → chunks + embeddings        │
   │   • Case layer: extracted {symptom, root_cause, action, outcome, resolver, time}    │
   │     + aggregated resolution patterns (action, n, success_rate, median_time)         │
   │   • Each case → evidence_refs back to Jira (traceability)                            │
   └───────────────┬───────────────────────────────────────────────────────────────────┘
                   ▼
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ D. SEARCH / RETRIEVAL LAYER (hybrid)                                                │
   │   BM25 (exact: error codes/hosts) ⊕ vector (semantic) ⊕ metadata filter            │
   │   (project/request-type/resolved/recency) → RRF fusion → re-rank by                 │
   │   relevance × success_rate × recency.  100k:pgvector | 500k+:OpenSearch | 1M+:+ANN  │
   └───────────────┬───────────────────────────────────────────────────────────────────┘
                   ▼
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ E. AI REASONING LAYER (agentic, tool-calling)                                       │
   │   Plan → retrieve precedents → assemble candidate actions w/ success rates →        │
   │   score confidence → decide. LLM emits TOOL CALLS only; never touches Jira direct.  │
   └───────────────┬───────────────────────────────────────────────────────────────────┘
                   ▼
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ F. ACTION / GOVERNANCE LAYER (the reliability gate)                                 │
   │   Validate proposed action ⊂ {transitions, assignable_users, permissions}.          │
   │   Confidence policy → AUTO | HUMAN-APPROVE | SUGGEST-ONLY.                           │
   │   Execute via tool layer (idempotent, issue-property guard). Full audit log.        │
   └───────────────┬───────────────────────────────────────────────────────────────────┘
                   └────────────────────► back to JIRA (comment / assign / transition / notify)
```

### 5.2 Action decision flow

```
new ticket ──► hydrate (GET issue + comments + changelog + JSM sla)
            ──► retrieve cases (hybrid) ──► candidate actions [{action, success_rate, n, citations}]
            ──► reason: best action + confidence + rationale + evidence
            ──► confidence gate:
                   ≥ τ_auto  AND action ∈ allow-list (e.g. comment, label) ──► AUTO-EXECUTE + log
                   ≥ τ_human                                                ──► CREATE APPROVAL (comment w/ proposal) + wait
                   <  τ_human                                               ──► SUGGEST-ONLY (internal note) / route to triage
            ──► write outcome to issue property (idempotency + audit)
```

### 5.3 Data synchronization strategy

- **Backfill (once):** bulk export resolved tickets via `POST /search/jql` (bounded JQL by project + date windows to stay within token pagination), hydrate with `bulkfetch` (100/call), throttled under the rate budget. Run extraction → populate both layers.
- **Incremental (steady state):** webhooks for create/update/comment → re-fetch → upsert. For safety against missed webhooks, a **reconciliation sweep** (`updated >= -1d` JQL) nightly catches gaps.
- **Re-extraction:** when the extraction prompt/schema improves, re-run over affected windows; version every case (`extraction_version`).
- **Jira remains source of truth** — the store is fully rebuildable from Jira; never the authority.

---

## 6. Governance & risk

| Risk | Mitigation |
|---|---|
| **Hallucinated solutions** | Ground every recommendation in retrieved cases with **citations** (`evidence_refs`); if retrieval returns nothing above a relevance floor → no auto-action, route to human. Show success-rate + n; suppress patterns with small n. |
| **Incorrect auto-resolution** | Auto-resolve is the **highest-risk** action — gate behind the **strictest** threshold, an allow-list of eligible request types, and ideally an SLA "undo window" before customer notification. Start with auto-resolve **disabled**. |
| **Wrong routing/assignment** | Constrain to `assignable_users`; prefer "add watcher / suggest assignee in comment" over hard reassignment until trusted. |
| **Acting outside permissions/workflow** | Tool layer validates against `transitions` + `mypermissions` + `assignable` **before** executing; least-privilege bot account. |
| **Duplicate actions (webhook retries/ordering)** | Idempotency key in **issue property** (`ai-state`); check-before-act. |
| **Feedback loops** | Filter out the bot's own comments (via `myself` accountId) from future retrieval/extraction. |
| **Customer-facing leakage (JSM)** | Respect `public` flag; default AI comments to **internal**; explicit policy to ever go public. |

**Human-approval patterns (graduated autonomy):**

1. **Suggest-only** — AI posts an internal note; humans act. (Launch here.)
2. **Approve-to-act** — AI prepares the action; a human clicks approve (e.g., via the proposal comment or a side UI).
3. **Auto-act-with-undo** — low-risk actions auto-execute with an undo window + alerting.
4. **Autonomous** — only for action classes with proven, measured high success and low blast radius.

**Confidence thresholds:** per **action class** (commenting tolerates far lower confidence than transitioning/resolving) and ideally per **request type**. Calibrate empirically against the suggest-only phase; require both model confidence **and** retrieval support (`success_rate × n`).

**Auditability:** every decision logs inputs (ticket snapshot), retrieved case IDs, candidate actions + scores, chosen action, confidence, model/prompt versions, and outcome — written to an append-only store **and** summarized into the issue property/comment. This is what makes "reliability > automation" enforceable and reviewable.

**Rollback:** prefer reversible actions (comment, label, watcher) early; for transitions/assignments keep prior state in the audit log to script reversal; a global **kill switch** (disable auto-execution, fall back to suggest-only) must be one config flag.

---

## 7. Recommendation & roadmap

### Recommended architecture (given: 100k+ volume, Jira = source of truth, eventual autonomy, reliability > automation)

1. **Jira = source of truth + action surface.** Never the retrieval engine. All writes flow through a **constrained tool layer** validated against Jira's own allowed-actions envelope.
2. **Two-layer derived knowledge store** — evidence (raw, embedded) + **case layer** (structured CBR cases + aggregated resolution patterns with success rates). This is what turns "similar ticket" into "action with 87% success."
3. **Hybrid retrieval** — start on **PostgreSQL + pgvector + full-text** (single system, hybrid, low ops) for the current volume; plan the migration path to **OpenSearch hybrid + re-ranker** as volume crosses ~500k. Consider a **knowledge-graph** overlay (à la Rovo) for entity relationships at the high end.
4. **Agentic reasoning with tool calling** — plan → retrieve → propose → confidence-gate → act, emitting tool calls only.
5. **Governance-first rollout** — suggest-only → approve-to-act → narrow autonomy, gated by per-action-class confidence thresholds, full audit, and a kill switch.

### Implementation roadmap

| Phase | Duration | Deliverable | Exit criterion |
|---|---|---|---|
| **0. Foundations** | 2–3 wks | Service account + scopes; webhook ingress with idempotency; normalization (ADF→text, accountId/customfield resolution); audit store. | Live tickets reliably captured & normalized. |
| **1. Backfill + evidence layer** | 3–4 wks | Bulk export (JQL + bulkfetch, throttled); chunk + embed; hybrid retrieval (pgvector) over evidence. | Retrieve relevant historical tickets for a new ticket. |
| **2. Case extraction + patterns** | 4–6 wks | Offline extraction → case layer; aggregation → resolution patterns w/ success rates; quality spot-checks. | "For symptom X, top actions + success rates" returns sensibly. |
| **3. Reasoning (suggest-only)** | 3–4 wks | Agentic loop + tool layer (read-only + add **internal** comment); proposals with citations + confidence. | Agents post useful, grounded suggestions; humans rate them. |
| **4. Approve-to-act** | 3–4 wks | Assignment/transition/notify behind human approval; allowed-actions validation; idempotency. | Approved actions execute correctly, fully audited. |
| **5. Graduated autonomy** | ongoing | Per-action-class thresholds; auto-execute low-risk classes with undo + monitoring; dashboards (precision, reopen rate, time-saved). | Measured high precision on a class → promote it; kill switch proven. |

**Guiding principle for every phase:** autonomy is *earned per action class* by measured precision and low blast radius — never switched on globally. That is how "reliability is more important than automation" becomes an operating reality rather than a slogan.

---

### Sources
- Atlassian — [Advancing Rovo semantic search](https://www.atlassian.com/blog/atlassian-engineering/advancing-rovo-semantic-search), [Rovo multi-agent orchestration](https://www.atlassian.com/blog/atlassian-engineering/how-rovo-embraces-multi-agent-orchestration), [Rovo Deep Research](https://www.atlassian.com/blog/atlassian-engineering/how-rovo-deep-research-works)
- [Rovo knowledge-graph vs RAG analysis (MindStudio)](https://www.mindstudio.ai/blog/atlassian-rovo-knowledge-graph-vs-rag-arr-growth)
- [Agentforce vs ServiceNow AI comparison (eesel)](https://www.eesel.ai/blog/salesforce-agentforce-vs-servicenow-ai)
- Atlassian Developer — [Jira Platform REST v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/), [JSM REST API](https://developer.atlassian.com/cloud/jira/service-desk/rest/api-group-servicedesk/), [Webhooks](https://developer.atlassian.com/cloud/jira/platform/webhooks/)
- Verified live this engagement against a Jira Cloud site (API inventory in `catalog_data.py` / `API_GUIDE.md`).
