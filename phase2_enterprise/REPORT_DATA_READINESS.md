# Data Readiness Assessment — Is Our Jira History Fit for AI Action Recommendation?

**Purpose:** decide, with evidence, whether the historical JSM corpus can support *action recommendation* ("what action worked, with what success rate") — not just *similarity*. This operationalizes the central risk from [REPORT_CRITICAL_REVIEW.md](REPORT_CRITICAL_REVIEW.md) §1.1: **a resolution recommendation is only as trustworthy as the data's ability to show that an action caused an outcome.**

**How to use this document:** run the two-pass assessment (§4), compute the Data Readiness Score (§5), apply the multi-dimensional go/no-go (§6), and set expectations with §7. Every metric below maps to a concrete Jira API/JQL so it is executable, not theoretical.

> **One-line thesis:** the corpus is *probably* good enough for **routing/classification and grounded suggestions**, and the open question — the one this assessment answers — is whether the **fixes are actually written down and reliably labeled** well enough for **autonomous action**. That single question (we call it *actionability* + *label reliability*) carries half the score.

---

## 1. Mandatory fields

"Mandatory" = if absent/unusable, the ticket cannot serve its role. Split by role in the pipeline.

### 1.1 Hard-mandatory (a ticket missing any of these is not a usable case)

| Field | Why | Source |
|---|---|---|
| `summary` | Primary symptom signal for matching. | `GET issue` fields |
| `status` + `status.statusCategory` | Must know it reached a **Done** category to be a candidate case. | fields / `GET /project/{key}/statuses` |
| `issuetype` | Bug/Incident/Service Request behave differently; filters retrieval. | fields |
| `project` (+ JSM `requestType`) | Scope, routing target, retrieval filter. | fields / `GET /servicedeskapi/request/{id}` |
| `created` + `resolutiondate` | Resolution time = key quality + staleness signal. | fields |
| `reporter` | Dedup, customer/org context. | fields |

### 1.2 Resolution-signal fields (define the *outcome* label)

| Field | Why | Source |
|---|---|---|
| `resolution` (Fixed / Won't Fix / Duplicate / Cannot Reproduce / Done) | **Critical:** only *Fixed-class* resolutions are positive cases. "Won't Fix/Duplicate/Cannot Reproduce" are **non-cases** and must be excluded, not counted as successes. | fields |
| changelog status transitions | The transition into a Done category = the moment of resolution; reopen = transition back out. | `GET issue/{key}/changelog` |
| `assignee` at resolution | The resolver → routing target + "who knows this." | fields + changelog |

### 1.3 Action-signal sources (define *what was done* — the hardest part)

| Source | Why | Source |
|---|---|---|
| **Resolution narrative** — a comment/work-note describing the fix, or a dedicated "resolution"/"root cause" custom field | **The single most important data element for action recommendation.** If the fix is not written down here, there is no action to learn. | `GET issue/{key}/comment` (JSM: respect `public` flag) / `GET field` |
| changelog (assignee/status path) | Reveals the *process* (escalations, reassignments, reopens). | `GET issue/{key}/changelog` |

### 1.4 Categorization & JSM context (routing / filtering / prioritization)

`components` (+ component `lead`), `labels`, JSM `requestType`, `sla` (breach signal), `priority`. Useful, not hard-mandatory.

> **The pivotal finding most assessments miss:** structural completeness (§1.1) is almost always fine — Jira enforces it. The corpus lives or dies on §1.3: **is the fix actually captured in text?** A huge fraction of real tickets are "Resolved / Done" with the fix done verbally, in a chat, or in another tool. Those tickets are structurally perfect and **useless for action recommendation.**

---

## 2. Quality indicators that PREDICT success (positive signals)

A ticket is a *good case* when it exhibits these. Each is measurable.

| Indicator | Signal | How to measure |
|---|---|---|
| **Has a substantive resolution narrative** | The fix is reproducible from text. | Comment exists near resolution time, length > N chars, judged actionable (human/LLM). |
| **Fixed-class resolution** | Genuine positive outcome. | `resolution IN (Fixed, Done-with-fix)` — *not* Won't Fix/Duplicate/CNR. |
| **Single resolution, no reopen** | Reliable success label. | changelog: exactly one entry into Done category, none leaving it. |
| **Plausible resolution time** | Real human work, not auto-close or abandonment. | `1h ≤ (resolutiondate − created) ≤ ~90d` (tune per team). |
| **Diagnosis→action→confirmation thread** | Causality is legible. | comment-thread shape (≥2 comments incl. a fix + a confirmation). |
| **Clear symptom in description** | Matchable input. | description non-empty, not attachment-only, > N chars. |
| **Consistent categorization** | Reliable routing/filtering. | component/label/requestType present and from a controlled set. |
| **Recent** | Knowledge still valid. | `resolutiondate >= -18..24 months` weighted higher. |

---

## 3. Quality issues that CAUSE failure (red flags)

| Issue | Why it breaks action recommendation | Detection |
|---|---|---|
| **Resolved with no fix narrative** | Nothing to learn; the action is invisible. | resolved + zero substantive comments + empty resolution field. |
| **Auto-close / bulk-close** | Fake "successes" — resolution_time≈0, or many issues closed at the identical timestamp by an automation actor. | `resolution_time < ~few min` OR same-timestamp batch OR resolver = automation account. |
| **High reopen rate** | The success label is unreliable → fabricated success rates. | changelog: >1 entry into Done, or Done→not-Done transitions. |
| **"Done" used for everything** | Can't distinguish Fixed from Won't-Fix/Duplicate. | resolution distribution heavily skewed to a single generic value. |
| **Empty / attachment-only / forwarded-email descriptions** | No matchable symptom; extraction fails. | description length, "see attached", quoted-email patterns. |
| **Fix lives in another system** | Action references a KB/Slack/external tool, not in Jira. | comments dominated by external links, "fixed, see <url>". |
| **Inconsistent / free-text labels** | Routing & filtering unreliable. | label cardinality explosion, near-duplicate labels. |
| **Duplicates & noise** | Inflate apparent frequency; pollute patterns. | "+1", "any update?", near-identical tickets. |
| **Mixed languages** | Extraction & embedding quality drops. | language detection across sample. |
| **PII / secrets in body** | Readiness/compliance blocker for egress (review §5.3). | secret/PII scan. |

---

## 4. Sampling & scoring 1,000 historical tickets

### 4.1 Sampling design — stratified, not uniform-random

Uniform-random over the whole history over-weights the noisiest/highest-volume project and the oldest (stalest) data. Instead:

1. **Population:** resolved tickets (Done statusCategory) in the **last 24 months** (staleness cut), since only resolved tickets can be cases. *Also* draw a small control set of unresolved/old tickets to estimate exclusion rates.
2. **Strata:** `project × requestType(or issuetype) × recency-bucket(0–6m, 6–12m, 12–24m)`. Cap each stratum (e.g. ≤ 80) so no single category dominates; allocate proportionally to volume with a floor for minor categories.
3. **Size:** 1,000 stratified ≈ ±3% margin overall and enough (≥30–50) per major request type to read per-category readiness — which matters because **readiness is usually uneven** (one team documents fixes well; another doesn't).
4. **Selection:** random within stratum, seed-fixed for reproducibility.

> JQL to enumerate a stratum: `project = X AND issuetype = Incident AND statusCategory = Done AND resolved >= -6m ORDER BY resolved DESC` → page with `nextPageToken`, then `bulkfetch` (100/call) to hydrate. Respect the rate budget (critical review §2.1).

### 4.2 Two-pass scoring

**Pass A — automated (all 1,000, cheap, from API fields):** computes the objective dimensions directly:
`has_resolution_field`, `resolution_class` (Fixed vs non-case), `reopen_count` (changelog), `resolution_time`, `comment_count`, `description_length`, `categorized?`, `recency`, `language`, `auto_close_suspected`.

**Pass B — judged (the same 1,000, or a ≥300 subset if budget-bound; human + LLM-assisted):** the qualitative dimensions automation can't decide:
- **Actionability (0/1/2):** is the fix reproducible from the text? (0 none, 1 vague, 2 clear/actionable).
- **Causality legibility (0/1):** does the thread show the action led to the outcome (vs closed-and-moved-on)?
- **Symptom clarity (0/1/2).**
- **Genuine-case vs noise (0/1):** real resolvable issue vs duplicate/chitchat/non-case.

Use a 2-rater check on ~10% to measure inter-rater agreement; an LLM can pre-label and humans adjudicate disagreements to cut cost.

### 4.3 Per-ticket → corpus aggregation

Each ticket yields sub-scores; aggregate to **corpus-level rates** (e.g. "62% of resolved tickets have actionability ≥ 1; 34% have actionability = 2"). Those rates feed the DRS.

---

## 5. Data Readiness Score (0–100)

Weighted across seven dimensions. Weights reflect what matters for **action recommendation specifically** — actionability and label reliability dominate because they are what separate "recommend an action" from "find a similar ticket."

| # | Dimension | Weight | What it measures | Corpus metric → sub-score (0–100) |
|---|---|---|---|---|
| 1 | **Resolution actionability** | **30** | Are fixes written down & reproducible? | % of resolved tickets with judged actionability = 2 (full), partial credit for =1. |
| 2 | **Success-label reliability** | **20** | Can we trust "this resolved it"? | blend of (1 − reopen_rate), (1 − auto_close_rate), Fixed-class share, causality-legible share. |
| 3 | **Symptom clarity (input side)** | **15** | Can we match new tickets to cases? | % with symptom clarity ≥ 1 and non-empty/non-attachment-only description. |
| 4 | **Categorization consistency** | **10** | Reliable routing/filtering. | % consistently categorized; penalize label-cardinality explosion. |
| 5 | **Coverage & freshness** | **10** | Enough recent cases per category. | % of request types with ≥ K recent good cases; recency-weighted. |
| 6 | **Structural completeness** | **10** | Mandatory fields present. | % passing §1.1 checks (usually high). |
| 7 | **Cleanliness / noise** | **5** | Dedup, language, PII. | (1 − duplicate_rate) × (single-language share) × (1 − unscrubbed-PII blocker). |

**DRS = Σ (dimension_subscore × weight) / 100.**

> Design choices, deliberately: dimensions 1+2 = **50%** of the score, because the critical review showed they are the project's make-or-break. Structural completeness is only 10% precisely because it is almost always fine and is the least informative signal. PII appears as a *multiplier-style* penalty in dimension 7 because unscrubbed secrets are a hard compliance blocker, not a gradual quality issue.

### Worked example
Resolved-ticket sample shows: actionability=2 in 30%, =1 in 30% (→ dim1 ≈ 30 + 0.5×30 = 45); reopen 12%, auto-close 18%, Fixed-class 70%, causality-legible 55% (→ dim2 ≈ 100×(0.88+0.82+0.70+0.55)/4 ≈ 74); symptom-clear 68% (dim3≈68); categorized 80% (dim4≈80); coverage 60% (dim5≈60); structural 95% (dim6≈95); cleanliness 0.9×0.85×1 ≈ 0.77 (dim7≈77).
**DRS = (45×30 + 74×20 + 68×15 + 80×10 + 60×10 + 95×10 + 77×5)/100 ≈ 64** → **Conditional** (see §6): start routing + suggestions, defer the case layer.

---

## 6. Go / No-Go criteria (multi-dimensional — not a single number)

A single threshold is exactly the trap the critical review warned against. Gate on the **overall score AND two critical sub-dimensions**, because a high average can hide a fatal actionability gap.

| Decision | Overall DRS | AND Actionability (dim 1) | AND Label reliability (dim 2) | Meaning |
|---|---|---|---|---|
| 🟢 **GO — full CBR action recommendation** | ≥ 75 | ≥ 60 | ≥ 60 | Fixes are documented and labels trustworthy → build the case layer, pursue graduated autonomy. |
| 🟡 **CONDITIONAL — suggestions + routing only** | 55–74 | 40–59 | ≥ 50 | Enough to ground suggestions and route, **not** to auto-act on inferred fixes. Defer the case layer (review §6.3); fix data discipline in parallel. |
| 🔴 **NO-GO — remediate first** | < 55 | < 40 | < 50 | The fix is too often not written down or the success label is unreliable. Building CBR here produces confident-wrong advice. Invest in KB curation + resolution-note discipline first (review §6.4), then re-assess. |

**Override rules (any one forces a downgrade):**
- Actionability < 40 → **cannot** be GO regardless of overall score (no fixes to learn).
- Unscrubbed PII/secrets present and no scrubbing pipeline → **blocked** for any external-LLM egress until remediated (compliance, not quality).
- A request type with high volume but < K good cases → that *category* is no-go even if the corpus overall passes (readiness is per-category).

---

## 7. Expected recommendation quality by data-quality level

Honest ranges, framed as **hypotheses to validate against a held-out labeled set**, not promises — consistent with the critical review's stance on unvalidated metrics. "Quality" here ≈ useful-action precision (proposed action a human would accept).

| DRS tier | Realistic capability | Expected useful-action precision* | Safe operating mode |
|---|---|---|---|
| **80–100** | Documented fixes, reliable labels, good coverage. | ~70–85% on common categories; lower on long-tail. | Graduated autonomy on **proven** low-risk action classes; approve-to-act elsewhere. |
| **65–79** | Decent fixes, some label noise, uneven coverage. | ~55–70% common; weak long-tail. | Suggestions + routing; human-approve for any state change. |
| **55–64** | Fixes often vague; notable noise. | ~40–55%; unreliable success rates. | Grounded **suggestions only** (cite source ticket); deterministic routing separately. |
| **< 55** | Fixes mostly not captured / labels unreliable. | < 40%; success rates meaningless. | Do **not** ship action recommendation. Remediate data / build KB first. |

\* Estimates assume retrieval and model are competent; they bound quality from the **data** side. Real numbers must come from offline replay on a labeled gold set (critical review §4.1) — this table sets expectations, it does not replace measurement.

**Read this table together with §6:** notice that even an 80+ corpus does **not** authorize blanket autonomy — it authorizes autonomy *on action classes you have measured*. The data readiness sets the ceiling; the eval harness earns the autonomy.

---

## Appendix — automatable metric cheat-sheet (Pass A)

| Metric | Computation |
|---|---|
| `resolution_class` | `fields.resolution.name` ∈ Fixed-set? |
| `reopen_count` | changelog: count of transitions where `to.statusCategory` leaves "Done". |
| `resolution_time_h` | `resolutiondate − created`. |
| `auto_close_suspected` | `resolution_time_h < ε` OR resolver ∈ automation accounts OR same-timestamp batch. |
| `comment_count` / narrative len | `GET issue/{key}/comment` (exclude bot/automation authors via `myself`). |
| `description_usable` | length ≥ N AND not attachment-only/quoted-email. |
| `categorized` | components ∨ labels ∨ requestType present & in controlled set. |
| `recency_weight` | decay on `resolutiondate`. |
| `language` | detector over summary+description. |

Pass A is cheap enough to run over the **entire corpus** (via JQL aggregation + `bulkfetch`), giving a free first-read before committing to the 1,000-ticket judged sample. If Pass A alone shows, e.g., 70% of "resolved" tickets have zero non-bot comments, you already know the answer is **No-Go for CBR** without Pass B.
