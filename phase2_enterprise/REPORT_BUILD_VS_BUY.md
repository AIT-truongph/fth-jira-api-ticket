# Build vs Buy Analysis — AI Ticket-Action Recommendation on JSM

**Why this report exists:** [REPORT_CRITICAL_REVIEW.md](REPORT_CRITICAL_REVIEW.md) §0.2 flagged that the original architecture ([REPORT_AI_TICKET_ARCHITECTURE.md](REPORT_AI_TICKET_ARCHITECTURE.md)) jumped straight to "build" without evaluating buy. This corrects that, against the stated priorities: **hundreds of thousands of tickets, Jira as source of truth, eventual autonomous actions, and reliability over automation.**

**Headline finding:** for a Jira-native, reliability-first shop, **buy-led wins decisively**. The two native options score ~85/100; the custom build scores ~50 — and it loses precisely on the dimensions the brief prioritizes (security, permission model, maintainability, time-to-market), winning only on raw feature coverage, which is the one thing you can safely defer. The native **Smart Resolution Suggestions** feature already delivers the agent-facing version of the core use case today.

---

## 1. The four options (and an important overlap)

> **Clarification:** options 1 and 2 are both Atlassian-native and **complementary, not mutually exclusive**. JSM AI is the *packaged feature set*; Rovo is the *agent platform* (search + custom agents via Studio). In practice "buy native" means adopting both. They're scored separately because they cover different parts of the requirement.

### Option 1 — Atlassian Rovo (incl. Rovo Agents / Studio)
Atlassian's AI platform: enterprise search over the **Teamwork Graph** (GraphRAG), ~20 out-of-the-box agents, and **custom agents built no-code in Studio** that can *organize, create, and edit Jira work items with permission*. Autonomy is achieved by wiring agents into **Automation rules** (admin-configured). Pricing: core Rovo included in Jira/JSM plans; advanced features + custom-agent usage draw on a **credit pool** (≈25 credits/user/mo standard), with a $20/user/mo add-on for higher tiers. ([Rovo agents](https://support.atlassian.com/rovo/docs/agents/), [agents in automations](https://support.atlassian.com/rovo/docs/agents-in-automations/), [pricing](https://bestagenthub.com/tools/atlassian-rovo))

### Option 2 — Jira Service Management AI (native features)
Packaged JSM capabilities (Premium/Enterprise, ≈$47–51/agent/mo):
- **Intelligent Triage** — auto-categorize, route, and prioritize incoming tickets by need/sentiment/language. *(Covers the routing/assignment actions.)*
- **Draft Replies** — drafts a reply from how agents resolved **similar past tickets** — the closest native match to the brief ("VPN failure → past restart-service replies → suggested reply"). *(Hard dependency: only generates when similar tickets are already in **Resolved** status — see §6.)*
- **Service Request Helper (Rovo agent)** — composes responses from previous requests, finds SMEs, recommends next steps.
- **Smart Resolution Suggestions / AI Suggestions Panel** — agent-facing recommendations (assignees, escalation paths, troubleshooting steps) from similar historical tickets + KB. *(Agent-facing version of the exact use case in the brief.)*
- **Virtual Service Agent** — KB-grounded deflection/self-service, hands off to humans.
Forrester TEI cites ~30% deflection and ~55 min saved/incident. ([JSM AI review](https://www.eesel.ai/blog/a-review-of-jira-service-managements-ai)) Caveat: agent-facing **suggest-only**; not turnkey autonomous action with confidence gating. Full native evaluation + cheap eval plan: **[../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md)**.

### Option 3 — Marketplace solutions
Third-party apps (AI triage, auto-reply, automation, ticket-mining assistants) installed against your Jira. Vendor-managed; configure-and-go. Trade-off: data typically **egresses to the vendor's cloud + their LLM**, broad OAuth scopes, and **vendor-longevity/lock-in risk**.

### Option 4 — Custom architecture
The bespoke design from the architecture report: ingestion → two-layer knowledge store (evidence + structured CBR cases) → hybrid retrieval → agentic reasoning → governed action layer. Maximum fit; maximum ownership burden and risk (see critical review §4–5).

---

## 2. Evaluation across the seven dimensions

### Feature coverage (vs the requirement)
- **Custom — highest by definition:** only option that natively delivers *structured, success-rate-weighted action inference* **and** *governed autonomous execution* exactly as specified.
- **Rovo — high:** read/retrieve/suggest + take actions via custom agents; autonomy via automation. Not natively "87%-success-rate CBR," but extensible and close.
- **JSM AI — moderate:** triage/routing + suggestions + deflection out of the box (covers most "actions"), but **suggest-only** and no structured success-rate engine or turnkey autonomous fix-execution.
- **Marketplace — varies (moderate–high):** some do strong triage/reply/automation; few do governed autonomous action with auditability.

### Security
- **Rovo / JSM AI — strongest:** data stays inside Atlassian's trust boundary under their DPA, with **Data Residency support and zero-day retention** (no persistent storage/logging of AI data); **no derived store you must secure**, no external-LLM egress you contract, no PII-scrubbing pipeline to build. Neutralizes critical-review §5.3 by construction.
- **Marketplace — weakest-to-moderate:** content egresses to a third party + their model; expands attack surface; depends on the vendor's SOC2/DPA.
- **Custom — most control, weakest by default:** every §5 risk (ACL replication, PII egress, prompt-injection fencing, webhook auth, over-privileged bot) becomes your build-and-own problem.

### Permission model
- **Rovo / JSM AI — native:** agents act *with the user's/role's permissions*, inheriting issue-level security and JSM **public/internal** comment boundaries automatically.
- **Custom — hardest:** the derived store must **re-implement Jira's permission model** or it leaks restricted tickets into recommendations (critical-review §5.1).
- **Marketplace — middling:** acts under granted scopes/service account; whether its own index honors issue-level security varies by vendor.

### Scalability (100k+ tickets)
- **Rovo / JSM AI / Marketplace — vendor-managed:** retrieval/index scaling is their problem; scales with your instance. Watch: Rovo's **credit consumption** scales with usage (cost-scaling, not capacity).
- **Custom — you own it:** unbounded ceiling, but the **backfill fights the shared rate budget** (critical-review §2.1) and you run the infra.

### Cost
- **JSM AI:** plan upgrade (Premium/Enterprise) — effectively "free" if already there, otherwise per-agent uplift.
- **Rovo:** core included; advanced/custom-agent usage is **credit-metered** (variable, can surprise at high inflow) + optional $20/user add-on.
- **Marketplace:** per-agent/tier subscription on top.
- **Custom — highest and most uncertain TCO:** months of build + **forever** per-ticket inference (scales with inflow) + infra + a standing data-engineering team (critical-review §3, §4.2).

### Time to market
- **JSM AI / Rovo:** days–weeks (toggle features; build a Studio agent no-code).
- **Marketplace:** days–weeks (install + configure).
- **Custom:** months (~18–25 weeks to graduated autonomy per the roadmap).

### Long-term maintainability
- **JSM AI — lowest burden:** Atlassian maintains the feature; you maintain config.
- **Rovo — low:** Atlassian maintains the platform; you maintain agents/automations. Caveat: subject to their roadmap + credit-pricing changes.
- **Marketplace — moderate:** vendor maintains, but lock-in + app-deprecation/longevity risk.
- **Custom — highest:** you own a data product (drift, re-extraction, re-embedding, eval harness) indefinitely.

---

## 3. Decision matrix

Scores 1 (poor) – 5 (excellent). Weights sum to 100 and are tilted toward the brief's priorities — **security, permission model, and maintainability (reliability) are weighted above feature coverage and time-to-market.**

| Dimension | Weight | Rovo | JSM AI | Marketplace | Custom |
|---|---:|:--:|:--:|:--:|:--:|
| Feature coverage | 18 | 4 | 3 | 3.5 | **5** |
| Security | 18 | **5** | **5** | 2 | 2 |
| Permission model | 14 | **5** | **5** | 3 | 2 |
| Scalability | 12 | 4 | 4 | 4 | 3 |
| Cost | 14 | 3 | 3 | 3 | 1.5 |
| Time to market | 9 | **5** | **5** | 4 | 1 |
| Long-term maintainability | 15 | 4 | **5** | 3 | 2 |
| **Weighted total (/100)** | | **85** | **85** | **62** | **50** |

*(Weighted totals: Rovo 85.4, JSM AI 84.8, Marketplace 62.4, Custom 50.0.)*

**Sensitivity:** the result is robust. Even if you raise *feature coverage* to the single highest weight, native options still lead, because Custom's coverage edge is offset by its 2/2/1.5/1/2 across security, permissions, cost, time, and maintainability. Custom only overtakes if you weight feature coverage above **everything else combined** — which directly contradicts "reliability over automation."

---

## 4. Recommendation — buy-led hybrid, phased

**Do not build the bespoke platform first. Buy the native layer now; build only the differentiated delta, later, and only if justified.**

### Phase 1 (now, weeks) — Buy native, capture value immediately
Adopt **JSM AI** (Intelligent Triage for routing/priority; **Smart Resolution Suggestions** for agent-facing recommendations from historical resolutions; Virtual Service Agent for deflection) **+ Rovo Search**. This delivers ~70% of the brief — read, retrieve, similar-resolution suggestions, routing — **inside the permission model, with no data egress, in weeks, at low maintenance.** It is the reliability-first move.
> Run the **Data Readiness Assessment** ([REPORT_DATA_READINESS.md](REPORT_DATA_READINESS.md)) in parallel. Native suggestions also surface, in production, how good your historical data actually is — free signal for the readiness verdict.

### Phase 2 (months) — Extend with Rovo custom agents (low-code), still no build
For gaps native features don't cover (specific routing logic, SME mentions, escalation rules), build **Rovo custom agents in Studio** wired to **Automation** for bounded autonomous actions. Still Atlassian-maintained, still in the permission model. Curate the **Confluence KB** in parallel — it is the grounding source native AI uses, and (per readiness §6.4) a higher-precision knowledge source than raw ticket mining.

### Phase 3 (conditional) — Build the thin differentiated layer, only if all hold:
1. Data Readiness = **GO** for CBR (actionability + label-reliability pass), **and**
2. Native Smart Resolution Suggestions proves **insufficient** for your action-quality bar (measured, not assumed), **and**
3. You require **structured success-rate-weighted autonomous execution** that native automation cannot express.

If so, build a **narrow** custom layer — the structured case/success-rate engine + a governed autonomous-action service — **on top of**, not instead of, the native stack, reusing Rovo/JSM for retrieval and acting through Jira's allowed-actions envelope. This confines the costly, high-risk build (critical-review §3–5) to the one capability that genuinely differentiates, after its prerequisites are proven.

### Where each option lands
- **Rovo + JSM AI:** the foundation. Adopt.
- **Marketplace:** consider only for a *specific* gap native + custom-agents can't fill, after a security/data-egress review; avoid as the core of an autonomous-action system (data-egress + longevity risk conflict with reliability-first).
- **Custom:** reserve for the Phase-3 differentiated delta — never as the starting point.

**Bottom line:** building first optimizes for capability you may not need at the expense of the reliability, security, and speed you definitely need. Buy the native stack now, let it prove your data and earn its keep, and build only the slice that remains genuinely yours to own.

---

### Sources
- Atlassian Rovo — [Agents](https://support.atlassian.com/rovo/docs/agents/), [Agents in automations](https://support.atlassian.com/rovo/docs/agents-in-automations/), [pricing/credits overview](https://bestagenthub.com/tools/atlassian-rovo)
- JSM AI — [review of JSM's AI](https://www.eesel.ai/blog/a-review-of-jira-service-managements-ai), [is JSM AI worth it (2026)](https://www.eesel.ai/blog/is-jira-service-management-ai-worth-it), [Jira AI agents: native/custom/layered](https://www.eesel.ai/blog/jira-ai-agent)
- **Native deep-dive: [../DANH_GIA_NATIVE_JSM_AI.md](../DANH_GIA_NATIVE_JSM_AI.md)** (detailed evaluation of the buy option + cheap eval plan)
- Companion reports: [Architecture](REPORT_AI_TICKET_ARCHITECTURE.md), [Critical Review](REPORT_CRITICAL_REVIEW.md), [Data Readiness](REPORT_DATA_READINESS.md)
