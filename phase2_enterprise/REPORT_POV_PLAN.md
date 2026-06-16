# Proof of Value (PoV) Plan — Can AI Recommend Useful Actions from Historical Jira Tickets?

**Objective:** decide whether this idea is **worth investing in** — not to build a production system. The PoV answers one question with evidence: *given historical resolved tickets, can an AI produce useful, correct resolution recommendations that beat a naive "find a similar ticket" baseline?*

**Constraints:** no autonomous actions, no workflow changes, **no production risk**, humans in control.

**Relationship to the other reports:** this is the **gate before** the [MVP](REPORT_MVP_DESIGN.md). The MVP is a live suggest-only pilot; the PoV is an **offline experiment** that runs entirely on exported historical data and a human SME panel — nothing is deployed, nothing writes to Jira, no agent ever sees a live AI comment. If the PoV says No-Go, you've saved the MVP's 12 weeks. It builds on [Data Readiness](REPORT_DATA_READINESS.md) (the data gate) and [Critical Review](REPORT_CRITICAL_REVIEW.md) (the "is the 87% real?" problem).

> **The core method — temporal backtest.** For a *resolved* ticket, you already know what actually fixed it. So: hide a held-out ticket's resolution, let the AI recommend an action using only *older* tickets, then compare the recommendation to what really resolved it. This gives a rigorous, scalable quality signal with **zero deployment**. The whole PoV hinges on this.

---

## 1. Hypotheses to validate (falsifiable)

Each hypothesis has a metric (§2) and a threshold (§9). The PoV is designed to be able to **disprove** them cheaply.

| # | Hypothesis | If false → |
|---|---|---|
| **H1 — Retrieval** | For a new ticket, the system retrieves ≥1 genuinely relevant resolved ticket in top-K. | Nothing downstream can work; stop. |
| **H2 — Actionability** | Retrieved tickets' resolutions contain a reproducible action often enough to be useful (data-dependent). | The corpus can't teach actions → No-Go for action recommendation (data problem). |
| **H3 — Recommendation quality** | An LLM, given the ticket + retrieved cases, produces an action an SME judges useful/correct at a useful rate. | Synthesis adds no quality → suggest-only is premature. |
| **H4 — Predictive (backtest)** | The recommended action semantically matches the action that *actually* resolved the held-out ticket above a baseline rate. | The system doesn't predict real resolutions → premise unproven. |
| **H5 — Beyond duplicate detection** | Recommendations beat a naive "most-similar-ticket" baseline by a meaningful margin. | **The core premise fails** — if AI ≈ similarity search, just use search; don't invest. |
| **H6 — Category feasibility** | At least one real ticket category has enough signal to support useful recommendations. | If none, No-Go; if some, scope the MVP to those. |

> **H5 is the decisive one.** The brief explicitly wants *"infer the action, don't just say it looks like ABC-123."* If the AI recommendation is no better than returning the single most similar ticket, the expensive part of the program is unjustified. The PoV must measure this lift directly.

---

## 2. Success metrics

| Metric | Measures | How |
|---|---|---|
| **Hit-rate@K / Recall@K** | Retrieval (H1) | % of held-out tickets whose top-K retrieved set contains ≥1 SME-relevant resolved ticket. |
| **MRR** | Retrieval ranking | Mean reciprocal rank of the first relevant hit. |
| **Actionable-resolution rate** | H2 | % of retrieved resolutions an SME judges to contain a reproducible action. |
| **SME usefulness rate** | H3 | % of AI recommendations rated useful/correct by an SME (blind). |
| **Backtest match rate** | H4 | % where recommended action semantically matches the actual resolving action (LLM-judge, human-audited). |
| **Lift over baselines** | **H5 (decisive)** | usefulness/match of AI recommendation **minus** the same for (a) naive most-similar-ticket, (b) keyword JQL top-1. |
| **Coverage** | H6 | % of sampled tickets where a confident recommendation could be produced (per category). |
| **Confidence calibration** | reliability | When the system is "confident," is it more often correct? (correctness vs self-rated confidence). |

All quality metrics reported **per category** — feasibility is almost always uneven (Readiness §4.1).

---

## 3. Data sampling strategy

1. **Candidate categories:** run **Data Readiness Pass A** first; pick **2–3 categories that pass** (actionability ≥ 40) **plus 1 that fails**, as a deliberate contrast — proving the method correctly says No-Go on a weak category is itself a valuable PoV result.
2. **Temporal split (critical):** to mimic production (you only ever have the past), split by time, not randomly:
   - **Index/knowledge set** = resolved tickets **older** than cut-date T (e.g. months 6–24 ago).
   - **Evaluation set** = resolved tickets **newer** than T (e.g. last 0–6 months), held out of the index so their resolutions are hidden from retrieval.
3. **Sizes (bounded for a PoV):**
   - Index: ≥ ~300–500 resolved cases per category.
   - Eval set: ~100–150 held-out tickets per category (statistical read + per-category signal).
   - **Gold set** (human-labeled, §5): ~200–300 tickets total across categories — the cost-limiting step, kept deliberately small.
4. **Read-only export:** one-time pull via `POST /search/jql` (bounded JQL, token pagination) + `bulkfetch` (100/call), throttled under the rate budget. **No webhooks, no writes.**

---

## 4. Offline evaluation methodology

Two scoring tracks, run on the held-out evaluation set:

**Track A — Automated backtest (cheap, all eval tickets):**
For each held-out ticket: scrub PII → retrieve top-K from the index (older tickets only) → LLM produces a recommended action → an **LLM-judge** scores whether the recommendation semantically matches the ticket's *actual* resolving action. Cheap enough to run on the full eval set for hit-rate, match-rate, and coverage. **Audit ~15% of LLM-judge calls against human labels** to measure judge reliability before trusting it.

**Track B — Human SME panel (authoritative, ~150–200 tickets):**
SMEs rate, **blind and randomized**, the AI recommendation alongside the baselines for: usefulness (would this help an agent?), correctness (any harmful/wrong advice?), actionability. Because it's blind, this yields the **lift over baseline (H5)** cleanly. Measure inter-rater agreement on ~10–20% (two raters + adjudication).

**Baselines to beat (all evaluated identically and blind):**
1. **Naive most-similar-ticket** — retrieval top-1, no synthesis (the "looks like ABC-123" approach).
2. **Keyword JQL top-1** — `text ~` best match.
3. **No recommendation** — the current status quo.

> Track A gives scale and the predictive signal; Track B gives the authoritative quality and lift numbers. The decision (§9) relies primarily on **Track B lift** + **Track A match-rate**, cross-validated.

---

## 5. Ground truth creation process

Ground truth exists in two forms — and the distinction between them *is* the critical-review causation problem made operational:

**(a) Implicit ground truth (free, scalable, noisy):** the resolution actually recorded on a held-out ticket = "what worked." Used for the automated backtest match-rate. **Caveat:** noisy — "resolved" ≠ "this action caused resolution" (Critical Review §1.1). Treated as a *proxy*, never as the final word.

**(b) Curated gold set (human, authoritative, small):** SMEs convert a sample into clean labels. Per ticket they record:
- **Is this a genuine resolvable case?** (filters auto-closed / abandoned / duplicate / "won't fix" — the non-cases).
- **The actual fixing action** (canonical), and **acceptable alternative actions** (so a correct-but-different recommendation isn't unfairly marked wrong).
- A **confidence** in their own label.

**Process:** select stratified sample → SME reviews ticket + full thread + recorded resolution → labels the above → **2 raters on ~15%** + adjudicate disagreements → **freeze** the gold set (versioned). This frozen set is the authoritative benchmark, the calibration data for the LLM-judge, **and** a direct Data-Readiness reading (what fraction were even genuine, actionable cases).

> The gold set is the single most valuable durable artifact the PoV produces — it outlives the PoV and becomes the regression benchmark for any future MVP/build.

---

## 6. PoV architecture (minimal, offline, throwaway)

**No webhooks. No Jira writes. No live deployment. No production surface.** A harness, not a system.

```
   JIRA (read-only, one-time)
        │  POST /search/jql + bulkfetch  (throttled; export only)
        ▼
   ┌──────────────────────────────────────────────────────────┐
   │ LOCAL POV HARNESS (notebook / scripts — disposable)       │
   │                                                            │
   │  export → PII scrub → temporal split (index vs eval)       │
   │                                                            │
   │  INDEX (older tickets):  BM25 + embeddings (pgvector /     │
   │     FAISS — in-proc is fine at PoV scale)                  │
   │                                                            │
   │  PIPELINE per eval ticket:                                 │
   │     retrieve top-K  →  LLM recommend action (cited)        │
   │                                                            │
   │  EVAL:                                                     │
   │     Track A: LLM-judge backtest match (+human audit)      │
   │     Track B: blind SME panel (AI vs 3 baselines)          │
   │     → metrics per category + lift + calibration           │
   └──────────────────────────────────────────────────────────┘
        │
        ▼  Go/No-Go report + frozen gold set
```

Reuse the existing read-only client (`jira_client.py`) for export. Everything else is disposable analysis code — explicitly **not** production-bound, so it carries no maintainability debt.

---

## 7. Timeline (5 weeks + 1 buffer)

| Week | Work | Output |
|---|---|---|
| **1** | Scope; Data Readiness Pass A → pick categories; read-only export; PII scrub; temporal split. | Clean local dataset, categories chosen with evidence. |
| **2** | Build index + hybrid retrieval + recommendation pipeline; implement 3 baselines; LLM-judge + audit harness. | Working offline pipeline + automated metrics on a smoke sample. |
| **3** | SME gold-set creation (~200–300), 2-rater + adjudicate, freeze. | Frozen, versioned gold set (durable asset). |
| **4** | Run Track A on full eval set; run Track B blind SME panel; collect metrics + lift + calibration. | Raw results across categories. |
| **5** | Analysis; lift vs baselines; calibration; **Go/No-Go report**. | Decision package. |
| **6** | Buffer / second category re-run if needed. | — |

Shorter than the MVP's 12 weeks because there is no live deployment, no feedback widget, no service to operate.

---

## 8. Exit criteria (PoV is *complete* — distinct from Go)

The PoV has run **validly** (regardless of outcome) when all hold:
- Gold set created, 2-rater agreement acceptable (e.g. Cohen's κ ≥ ~0.6), and **frozen**.
- Track A run on ≥ ~100 eval tickets per category across ≥ 2 categories.
- Track B blind panel completed on ≥ ~150 tickets covering AI + all 3 baselines.
- LLM-judge audited against human labels (agreement reported).
- Metrics, lift, and calibration documented **per category** with confidence intervals.

If exit criteria aren't met, the result is "inconclusive — extend," not Go/No-Go.

---

## 9. Go / No-Go decision framework

Multi-dimensional (no single number — Critical Review §0, Readiness §6). **Lift over the naive-similar baseline (H5) is the gate** — it directly tests the premise.

| Decision | Conditions (per best category) |
|---|---|
| 🟢 **GO — invest in the MVP** | Retrieval hit-rate@5 ≥ **70%** · SME usefulness ≥ **60%** · **lift over naive-similar ≥ +15pp** · backtest match-rate clearly above keyword baseline · ≥ 1 category passes cleanly. |
| 🟡 **CONDITIONAL — narrow MVP** | Retrieval strong but usefulness borderline (~45–60%), **or** only one narrow category passes, **or** lift positive but small (+5–15pp). → Proceed to a suggest-only MVP **scoped to the winning category only**, with explicit quality targets. |
| 🔴 **NO-GO — do not invest (yet)** | Usefulness < **45%**, **or** lift over naive-similar **≤ +5pp** (AI adds nothing over similarity search), **or** no category passes readiness/actionability. → Remediate data / invest in curated KB first (Build-vs-Buy §6.4, Readiness §6), then re-PoV. |

**Override rules:**
- **Lift ≤ +5pp over naive-similar → cannot be GO**, regardless of absolute scores. (If similarity search alone matches the AI, the premise is disproven — use search, skip the agent.)
- **No category passes data readiness → automatic No-Go** for ticket-mining; pivot to KB-based grounding.
- Strong native option (Build-vs-Buy): if JSM **Draft Replies / AI Suggestions Panel / Service Request Helper** can be A/B'd in the PoV, include them as a fourth "baseline" — if native already meets the bar, the GO is *"buy, don't build."* Note Draft Replies only fires when similar tickets are already **Resolved**, so its coverage is itself a readiness signal. Detail: [../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md).

---

## What the PoV deterministically delivers (whatever the verdict)

1. An **evidence-based Go/No-Go** on the core question — useful AI recommendations from history, or not.
2. The **decisive lift number** — does AI beat similarity search, the premise of the whole program.
3. A **frozen gold set** — the durable benchmark every later phase reuses.
4. A **per-category readiness map** — which parts of the business this can work for.
5. All of the above for **~5 weeks of effort and zero production risk** — the cheapest possible way to decide whether to invest further.

---

### Related
[Architecture](REPORT_AI_TICKET_ARCHITECTURE.md) · [Critical Review](REPORT_CRITICAL_REVIEW.md) · [Data Readiness](REPORT_DATA_READINESS.md) · [Build vs Buy](REPORT_BUILD_VS_BUY.md) · [MVP Design](REPORT_MVP_DESIGN.md) · [Native JSM AI eval](../DANH_GIA_NATIVE_JSM_AI.md)
