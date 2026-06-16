# Lowest-Risk MVP — AI Resolution Assistant (Suggest-Only)

**Mandate:** deliver measurable business value in 2–3 months with **no autonomous actions, no auto-resolution, no workflow changes, human always in control.** Prioritize simplicity and reliability.

**Design stance synthesized from the prior reports:**
- Buy-led ([Build vs Buy](REPORT_BUILD_VS_BUY.md)): prefer native if available.
- Defer the expensive structured case/CBR pipeline ([Critical Review](REPORT_CRITICAL_REVIEW.md) §6.3) — prove grounded retrieval helps *before* building it.
- Gate the pilot on data that actually passes ([Data Readiness](REPORT_DATA_READINESS.md)).
- The MVP's job is not to act — it is to **assist humans and generate the evidence** (labeled feedback) that tells you whether to invest further.

> **What the MVP is:** on a new ticket in **one scoped category**, the assistant retrieves how *similar resolved tickets* were handled and posts a single, clearly-labeled, **internal** suggestion comment with **citations** and a **feedback widget**. A human reads it and decides everything. Nothing is transitioned, assigned, or resolved by the system.

---

## 0. Two ways to build it — pick the lower-risk one available to you

| | **Option A — Native (buy)** | **Option B — Thin custom (build)** |
|---|---|---|
| What | Turn on JSM **Draft Replies + AI Suggestions Panel + Service Request Helper** (+ Intelligent Triage for routing), agent-facing, suggest-only. *(Draft Replies only generates when similar tickets are already **Resolved** → also a free data-readiness probe.)* | A small read-only service that retrieves similar resolved tickets and posts an internal suggestion comment. |
| Risk | **Lowest** — in permission model, no data egress, no infra. | Low, but you own retrieval, egress, and a service. |
| Time | Days–weeks (config). | 8–10 weeks. |
| When to choose | You're on JSM Premium/Enterprise (or can be). | Native unavailable, or you need control over retrieval/grounding the native black box won't give. |

**Recommendation:** if Option A is available, **start there** — it satisfies every MVP constraint with near-zero build risk, and you can run the data-readiness and KPI measurement *around* it. Build Option B only if native is off the table or proves insufficient. The rest of this document specifies **Option B** (the harder case); everything in §3–§7 applies to Option A too, just with the build phases removed. *(Detailed native evaluation + cheap eval plan for Option A: [../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md).)*

---

## 1. Architecture (Option B, deliberately minimal)

```
   ┌──────────── JIRA / JSM (source of truth) ────────────┐
   │  webhook: issue_created (one scoped request type)     │
   │  the ONLY write back: add INTERNAL comment            │◄─────────────┐
   └───────────────┬───────────────────────────────────────┘              │
                   │ (issue.key only — re-fetch for fresh data)            │ internal
                   ▼                                                       │ suggestion
   ┌───────────────────────────────────────────────────────────────────┐  │ + feedback
   │ MVP SERVICE (single small app + one datastore)                     │  │ widget links
   │                                                                     │  │
   │  1. Ingest: verify webhook → dedupe → GET issue + comments         │  │
   │  2. Scrub: strip secrets/PII BEFORE any egress                     │  │
   │  3. Retrieve: top-K similar RESOLVED tickets from index            │──┘
   │     (Postgres FTS + pgvector rerank; ACL-filtered to pilot scope)  │
   │  4. Draft: LLM writes a grounded suggestion w/ CITATIONS only      │
   │     from retrieved tickets (no ungrounded claims, no success %)    │
   │  5. Post: ONE internal comment + 👍/👎 + "used it?" feedback links  │
   │  6. Log: inputs, retrieved IDs, suggestion, feedback → eval store  │
   └───────────────────────────────────────────────────────────────────┘
                   ▲                         │
                   │ nightly backfill        ▼
   ┌───────────────────────────┐   ┌──────────────────────────────────┐
   │ KNOWLEDGE INDEX            │   │ EVAL / FEEDBACK STORE             │
   │ evidence layer ONLY:       │   │ every suggestion + human rating;  │
   │ resolved tickets in scope, │   │ powers KPIs + the go/no-go for    │
   │ last 12–18 mo, embedded.   │   │ any Phase-2 investment.           │
   │ NO case/CBR layer (yet).   │   └──────────────────────────────────┘
   └───────────────────────────┘
```

**Deliberate simplifications (each removes a risk class):**
- **Evidence layer only — no case extraction.** Removes the most error-prone, expensive component and the "fabricated success-rate" risk (critical review §1.1). The suggestion says *"3 similar resolved tickets; here's how they were handled [cited]"* — never *"87% success."*
- **One scoped category, one pilot team.** Bounds blast radius, backfill cost, and ACL complexity. Pick a category that **passes data readiness**.
- **Exactly one write: an internal comment.** Reversible, non-customer-facing, no workflow touch. (If even that is too much, a read-only side panel/dashboard is the zero-write variant.)
- **Single app + Postgres (FTS + pgvector).** No cluster, no vector-DB ops at MVP scale (readiness/build-vs-buy both favor this for ≤100k in scope).

---

## 2. Data requirements

**Gate before building:** run **Data Readiness Pass A** (automated scan, [readiness §4.2](REPORT_DATA_READINESS.md)) over candidate categories and **pick a pilot category that scores CONDITIONAL-or-better with actionability ≥ 40**. Do not pilot on a category where fixes aren't written down — the MVP would just generate noise.

**Corpus for the pilot:**
- Resolved tickets (Done statusCategory, Fixed-class resolution) in the pilot category, **last 12–18 months** (freshness).
- Minimum viable: **≥ ~300–500 good resolved cases** in the category (enough for retrieval to find relevant neighbors).
- Each indexed doc needs the §1 mandatory fields + a **resolution narrative** (comment/work-note). Tickets without a narrative are indexed as weak/excluded.

**Must-do data handling:**
- **Secret/PII scrubbing before egress** (passwords/tokens/PII pasted in tickets) — mandatory (critical review §5.3).
- **ACL scoping:** index only tickets visible to the pilot audience; respect JSM **internal vs public**; never surface a restricted ticket as a citation. Single-project pilot keeps this simple (critical review §5.1).
- Exclude the bot's own comments from retrieval (avoid feedback loops).

---

## 3. Evaluation methodology

Three layers, built **before** launch — this is what turns the MVP from an experiment into a measurable system (closes critical review §4.1).

1. **Offline replay (pre-launch):** take ~200 recently-resolved pilot-category tickets held out of the index; for each, generate the suggestion it *would* have produced; have 2 reviewers rate **actionability** (would this have helped?) and **correctness** (any harmful/wrong advice?). Establishes a quality baseline and a **gold set** for regression-testing prompt/model changes.
2. **Shadow mode (live, no posting):** for 1–2 weeks, generate suggestions on real new tickets but **don't post them**; log + sample-review. Confirms live quality matches offline before any human sees output.
3. **Online feedback (pilot):** the in-comment 👍/👎 + "did you use it?" widget captures human judgment on every real suggestion. This is the primary, continuous quality signal **and** the labeled data for any future Phase-2 decision.

**Baselines to capture in Week 1** (without these, "value" is unprovable — critical review §3): current median handle time and MTTR for the pilot category, current mis-route/reassignment rate, current agent-reported time spent searching for precedents.

---

## 4. KPIs

| KPI | Definition | Why |
|---|---|---|
| **Coverage** | % of in-scope new tickets that get a suggestion above the relevance floor. | Is the assistant present often enough to matter? |
| **Helpful rate** | 👍 / (👍+👎). | Direct usefulness signal. |
| **Adoption / "used it" rate** | % of suggestions the agent marks as used (or where they clicked a citation). | Real behavioral value, not just opinion. |
| **Actionability (review)** | % of a sampled set rated actionable by reviewers. | Precision proxy independent of mood. |
| **Noise / harmful rate** | % flagged irrelevant or wrong. | **Reliability guardrail** — must stay low. |
| **Handle-time / MTTR delta** | pilot vs control team (or pre/post). | Business value — treat as **directional**, attribution is imperfect. |
| **Time-to-precedent** | time for agent to find relevant past resolution, with vs without. | Cleanest "time saved" signal. |

> Run the pilot as **pilot-team vs control-team** (or staggered) so the handle-time/MTTR delta has a comparison baseline. Without a control, business-value claims are weak.

---

## 5. Success criteria (end of 2–3 months)

The MVP succeeds if it is **useful, not noisy, measurable, and decision-enabling**. Targets are starting points — calibrate to the Week-1 baseline:

- **Helpful rate ≥ 60%** and **noise/harmful rate ≤ 10%** (reliability gate — a noisy assistant fails even if occasionally brilliant).
- **Adoption ("used it") ≥ 30%** on covered tickets.
- **Coverage ≥ 50%** of in-scope tickets.
- **Directional improvement** in time-to-precedent and/or handle time vs control (even ~10–20% is a strong MVP signal).
- **Enough labeled feedback (≥ a few hundred rated suggestions)** to make an evidence-based **go/no-go** on Phase 2.
- **Zero** customer-facing leaks, zero unintended writes, zero workflow disruptions (constraint compliance).

> Note the design intent: even "failure" is valuable — if helpful rate is low, you've learned **cheaply** that the data/approach isn't ready (likely a readiness problem), having spent weeks not months and risked nothing in production.

---

## 6. Risks

The suggest-only, single-write design **eliminates** the highest-severity risks from the critical review (autonomous wrong actions, auto-resolution, workflow corruption). What remains:

| Risk | Severity | Mitigation |
|---|---|---|
| **Irrelevant/noisy suggestions → agents ignore it** | 🟠 | Relevance floor (no suggestion if weak match); shadow-mode tuning before launch; noise-rate KPI as a kill metric. |
| **PII/secret egress to LLM** | 🟠 | Scrub before egress; DPA with provider; pilot-scope data minimization. |
| **ACL/visibility leak in citations** | 🟠 | Index only pilot-visible tickets; honor internal/public; single-project scope. |
| **Hallucinated advice** | 🟡 | Grounded-only generation with mandatory citations; no claim without a cited source; reviewers rate correctness. |
| **Prompt injection via ticket text** | 🟡 (low, suggest-only) | No actions to hijack; still sanitize; human reviews every suggestion. |
| **Adoption failure** | 🟠 | Co-design comment format with the pilot team; make it genuinely useful (citations agents can click); measure and iterate. |
| **Cost overrun** | 🟢 | Bounded by single-category scope + relevance floor; per-ticket inference only on in-scope tickets. |
| **Misattributed business value** | 🟡 | Control-group design; treat MTTR delta as directional, lead with time-to-precedent + adoption. |

A one-flag **kill switch** (stop posting, fall back to logging-only) is mandatory and trivial here.

---

## 7. Rollout plan (12 weeks)

| Weeks | Phase | Deliverable | Exit gate |
|---|---|---|---|
| **1–2** | **0. Decide & baseline** | Option A vs B decision; Data Readiness Pass A → pick pilot category (must pass actionability ≥ 40); capture baselines (handle time, MTTR, mis-route, time-to-precedent); read-only service account (+ add-internal-comment scope); secret-scrubber. | Pilot category chosen with evidence; baselines recorded. |
| **3–5** | **1. Index & retrieve** | Scoped backfill (12–18 mo, throttled under rate budget); Postgres FTS + pgvector; ACL-filtered retrieval; relevance floor tuned. | Retrieval returns relevant resolved tickets for sample queries. |
| **5–6** | **2. Eval harness** | Offline replay on 200 held-out tickets; gold set; 2-rater actionability/correctness baseline. | Offline helpful-rate ≥ target on the gold set. |
| **6–8** | **3. Shadow mode** | Generate-but-don't-post on live tickets; daily sample review; tune prompt/grounding/floor. | Live quality matches offline; noise rate ≤ target. |
| **9–10** | **4. Limited launch** | Post internal suggestions + feedback widget to the **pilot team only**; control team unchanged. | Suggestions posting cleanly; feedback flowing; zero leaks/writes-out-of-scope. |
| **11–12** | **5. Measure & decide** | KPI report vs baseline/control; labeled-feedback corpus; **go/no-go for Phase 2** (expand categories / native adoption / build CBR per readiness). | Evidence-based recommendation delivered. |

**Guiding principle:** the MVP risks nothing in production (read + one reversible internal comment), proves or disproves value cheaply, and — whatever the outcome — produces the **labeled data and baselines** that every later decision (expand, adopt native deeper, or build the CBR layer) depends on. That is the lowest-risk way to learn whether this program deserves more investment.

---

### Related
[Architecture](REPORT_AI_TICKET_ARCHITECTURE.md) · [Critical Review](REPORT_CRITICAL_REVIEW.md) · [Data Readiness](REPORT_DATA_READINESS.md) · [Build vs Buy](REPORT_BUILD_VS_BUY.md) · [Native JSM AI eval](../DANH_GIA_NATIVE_JSM_AI.md)
