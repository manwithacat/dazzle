# Post-5.8 doctrine — functional harness vs interesting SaaS

**Audience:** Dazzle maintainers, `/improve` designers, agents on example-apps / framework-ux
**From:** Antagonist research stance (buyer stills + agent-context research)
**Date:** 2026-08-02
**Score baseline:** fleet **~5.8** (full run 2026-08-01) · pass ≥5.5 **held** · stills frozen since 01 Aug 02:12
**Related:** `REEVALUATION_FULL_2026-08-01.md` · `INVESTIGATION_2026-08-02.md` · `HYPERPART_PRESENTATION_PROCESS.md` · #1626

This is not a residual patch list. It is a **doctrine shift** after demo-safe was largely won, and a **research brief** on what *context* we should put in front of agents if we want interesting products—not only functional ones.

---

## 1. Verdict on #1626 residual era

| Claim | Status |
|-------|--------|
| Empty-hero / theater crisis | **Mostly closed** on scored heroes |
| Fleet demo-safe (≥5.5) | **Pass ~5.8** |
| Machine residual 0 | **Achieved** (necessary; never sufficient for category claims) |
| person×queue_meta Avatar pilot | **Still-proven** |
| Category leadership (~7.0) | **Not achieved** — not a residual-0 problem |

**Doctrine:** Treat demo-safe residual work as **complete enough to demote**. Do not keep farming walk/open-hop residuals and call it product progress. Open a **new epic class** for interesting product depth—or accept plateau.

Phase 7 “ship epic” (changelog/tag) may still be bookkeeping. **Product pressure for empty desks is gone.**

---

## 2. Two goals (do not collapse them)

Dazzle must support both. They need **different context, residuals, and proof**.

### Goal A — Functional SaaS (agent harness)

> Agents can **build, navigate, and verify** multi-entity SaaS without inventing framework each time.

| Includes | Proof |
|----------|--------|
| DSL expressiveness, seeds, STABLE personas | validate / demo quality |
| Dual-open / triple-open hops | story_walk, journey_dogfood, acceptance |
| RBAC, processes, walks, MCP world model | probes, digs, CI |
| residual=0 on maturity bars | machine green |

**Why it matters:** Without A, agents cannot produce *working* product at all. Dual-open is legitimate Goal A investment.

**Antagonist weight:** Medium. We care that harness exists; we do **not** re-score fleet composites for hop attrs alone.

### Goal B — Interesting SaaS (buyer / founder taste)

> Agents produce apps a human would **keep watching** and might **prefer** over a thin category tool—not merely apps that pass residual.

| Includes | Proof |
|----------|--------|
| Category-shaped depth (threads, documents, media, command density) | **Hero stills** + short human demo |
| Hyperpart presentation used as product language | stills (Avatar, not prose; swatches; not dict-repr) |
| Story identity (coherent names, devices, brands) | stills + seeds |
| Empty regions omitted or filled with intent | stills |
| Something surprising but domain-true | human judgment |

**Why it matters:** This is the research target: **what context stimulates Goal B**, given Goal A is increasingly competent.

**Antagonist weight:** Primary for bake-off and for “are we stagnating?”

```text
Goal A: can the agent ship a coherent app?
Goal B: would a buyer care?

A without B = functional plateau (today’s dual-open era risk)
B without A = pretty theater (old empty-hero failure)
Both = interesting, shippable SaaS
```

---

## 3. Pathology we just observed

When Goal A residuals hit **0**:

1. Improve still needs a cycle target.
2. Next residual becomes walk hops, gallery probes, open discovery attrs.
3. Commit velocity stays high.
4. Hero stills freeze.
5. Humans feel **stagnation** even though agents are “productive.”

This is not malice. It is **residual-seeking under a green bar**. Context that only rewards residual clearance will **not** produce interesting product once the bar is green.

**Research claim:** Interesting SaaS is under-stimulated by residual=0 loops. We must inject **different context**—not more of the same probe heat.

---

## 4. Research question (primary)

> **What context**, given to coding agents building on Dazzle, maximizes the rate of **interesting, domain-true product** (Goal B), without destroying **functional harness** (Goal A)?

Sub-questions:

1. Which artefacts (stills doctrine, peer products, depth menus, anti-patterns, playbooks) move agents from hop-farming to depth?
2. How do we encode “interesting” so agents can act—without Goodharting stills or residual floors?
3. When is dual-open substrate vs distraction?
4. What should improve pick when `residual_total=0`?

We are **not** asking “how do we maximize commits” or “how do we keep residual non-zero forever.”

---

## 5. Context stack (hypothesis)

Layers agents already get, and what we think each stimulates:

| Layer | Examples | Stimulates | Weak for |
|-------|----------|------------|----------|
| **Grammar / DSL** | grammar.md, stems, counter-priors | Valid structure | Taste, depth choice |
| **Harness / world model** | demo_identity, STABLE UUIDs, MCP demo_world | Populated desks, walks | “What product to be” |
| **Machine residual** | product_quality, demo_fleet, journey bars | Clear known defects | Work after residual=0 |
| **Presentation doctrine** | role×host matrix, person→Avatar | Chrome language | Category features |
| **Walk / open-via** | dual-open, story_walk | Navigable multi-entity apps | Above-fold interest |
| **Antagonist / stills** | bake-off, still floors, recapture | Buyer honesty | Needs human re-score cadence |
| **Interesting-product context** (underbuilt) | peer desks, depth menus, “one surprising true thing” | Goal B | Easy to fake without stills |

**Hypothesis:** Goal B needs an explicit **interesting-product context pack** that is loaded when residual is green—not only more Goal A probes.

---

## 6. Interesting-product context pack (v0 — implement / research)

When `product_quality residual_total=0` **and** hero stills are ≤N days stale **or** improve would pick dual-open again, inject this pack (docs + force lane), not silence.

### 6.1 Stance sentences (always-on when pack loads)

1. Residual 0 means **demo-safe**, not **done**.
2. Dual-open is **harness**; it is not this cycle’s product claim unless recaptured.
3. Prefer **one depth slice** over ten hop attrs.
4. Prefer **framework-wide** depth primitives when the gap is cross-app; else one showcase **icon app** with still proof.
5. **Stills beat walk green** for Goal B.

### 6.2 Depth menu (pick one per cycle max)

Closed list—agents **select**, not invent a twelfth chart:

| Depth id | Buyer read | Still proof |
|----------|------------|-------------|
| `conversation` | Work has a thread / trail of messages | Hero shows conversation strip or message list on ticket/task |
| `document` | Money/work has a document or line-item hub | Invoice/project still shows lines or PDF/doc region |
| `media` | Design/creative has pixels not only meta | Asset/brand still shows thumbnails or strong type/visual affordance |
| `command_density` | Ops is multi-panel attention, not one queue | Command center still shows ≥2 attention regions above fold |
| `org_structure` | HR/org is hierarchy people can parse | Tree or reporting still already partially done—extend people, not only depts |
| `empty_region_honesty` | No large void / skeleton theater | Secondary regions filled or omitted |

**Refuse:** new example app to “fix” depth; metric tile proliferation; dual-open-only cycle labeled as depth;
same surface recipe on the Nth app while the portfolio planner bans that recipe.

### 6.2b Portfolio pick (anti-wave / stacking — 2026-08)

Closed menu alone produced **fleet-fill monoculture** (same `depth_id` + same
recipe across every showcase). Selection pressure without inventing residual heat:

| Control | Default | Machine surface |
|---------|---------|-----------------|
| Max consecutive same `depth_id` | 3 | `scripts/interesting_product_portfolio.py` |
| Max consecutive same **recipe** | 3 | headshot_shelf, dual_attention, … |
| Icon-app stacking | prefer apps with 1–2 depths before thin coat | ICON_APPS + coverage from unit pins |
| Peer packs (R3) | when present | `improve/peer_packs/<app>.toml` |
| Oral history | durable loop lessons | `improve/oral-history.md` |

```bash
uv run python scripts/interesting_product_portfolio.py --status
uv run python scripts/interesting_product_portfolio.py --recommend
```

Policy attaches recommend onto `interesting_product` force args when residual=0.
**No interestingness score** — only diversification and stacking constraints.

### 6.3 Interestingness prompts (force agent reflection before implement)

Agent must answer in the cycle log (short):

1. **Peer:** What does a good commercial tool show on this desk’s first screen that we do not?
2. **Surprise:** What one domain-true detail would make a founder lean in?
3. **Still:** Which hero PNG will change, and what will a buyer see differently?
4. **Harness:** Does this require new open-via, or only product surface? (If only open-via → this is Goal A; do not claim Goal B.)

No answer → cycle is harness-only; label it so.

### 6.4 Proof gate (Goal B)

| Gate | Rule |
|------|------|
| Recapture | Hero still mtime after change |
| Visible | Diff is readable in above-fold still without walk script |
| Residual | May stay 0; Goal B is not residual_total |
| Score | Antagonist re-score only after recapture package |

### 6.5 Dual-open policy (harness without monoculture)

| Dual-open is **in policy** when… | Dual-open is **out of policy** when… |
|----------------------------------|--------------------------------------|
| A depth slice needs multi-hop navigation | residual_total=0 and no still plan |
| Walk/acceptance is red on hop | Cycle goal is only “add another hop label” |
| Framework shares discovery attrs once | Nth app triple-open without new primitive |

**Cap (suggested):** after **K** consecutive open-hop cycles (e.g. 5), force either recapture + still note **or** depth-menu cycle. Prevents open-hop monoculture.

---

## 7. Improve pick policy when residual is green

```text
IF residual_total > 0:
  force presentation / demo_fleet / maturity as today (Goal A+B hygiene)

ELSE IF hero stills stale > T days OR last N cycles were open-hop only:
  force interesting-product pack (depth menu + still proof)
  OR explicit harness-only label + no product claims

ELSE:
  optional Goal A (open-via, gallery) with label harness_only=true
```

**Never:** residual=0 → dual-open by default with silent implication of product progress.

---

## 8. What we will score going forward

| Work class | Antagonist response |
|------------|---------------------|
| residual clearance with recapture | Score / re-score stills |
| Presentation doctrine | Philosophy match + stills |
| Dual-open without recapture | **Note as harness**; **0 composite lift** |
| Depth menu + recapture | Re-score; possible Features/Domain lift |
| New example apps for bar | Reject (doctrine) |
| residual=0 claims of “fleet improved” | Reject |

Fleet ~5.8 remains the human score until a new recapture package lands.

---

## 9. Research experiments (suggested)

Context A/B for agents building a small desk (or improving one showcase app):

| Arm | Context given | Measure |
|-----|---------------|---------|
| **R0** | residual probes only | residual_total, walk green, still delta |
| **R1** | R0 + presentation doctrine | person_as_text / hyperpart use on stills |
| **R2** | R1 + interesting pack (depth menu + 4 prompts) | depth id chosen, still mtime, human interestingness 1–5 |
| **R3** | R2 + one peer still (or named commercial UI constraints) | same + “peer gap closed?” |
| **R4** | R2 + **forbid** open-hop commits | forces depth vs thrash |

**Primary DV (dependent variable):** human “would keep watching” (1–5) on stills.
**Secondary:** residual_total, walk pass, time-to-still, agent self-label harness vs product.

**Hypothesis:** R2/R3 beat R0 on interestingness when residual is already 0; R0 wins on residual when residual > 0.

This package’s antagonist docs are part of **R1/R2 context** for the research, not only scolding.

---

## 10. Messaging

| Safe | Forbidden |
|------|-----------|
| Demo-safe fleet ~5.8; residual era largely closed | residual=0 ⇒ product complete / interesting |
| Dual-open advances **agent harness (Goal A)** | Dual-open advances bake-off / Goal B without stills |
| Next pressure is **interesting depth** with still proof | Farm hops until residual invents itself |
| We are researching context for Goal B | “Agents will invent taste from residual alone” |

---

## 11. Minimal ask of Dazzle implementers

1. **Demote** #1626 residual heat when residual_total=0 (keep presentation residual as immune system).
2. **Add** improve force / strategy: `interesting_product` or `example-apps depth` implementing §6.
3. **Label** dual-open cycles `harness_only` in improve log when no recapture.
4. **Cap** consecutive open-hop cycles; force depth or recapture.
5. **Ship** one depth-menu slice with hero recapture when ready for antagonist re-score.
6. **Optional:** mirror this doc as `docs/reference/interesting-saas-context.md`.

---

## 12. One paragraph for agents

You can keep the fleet residual-green forever by inventing finer harness checks. That produces **functional** SaaS substrate and helps agents navigate. It does not produce **interesting** SaaS. When residual is green, load the interesting-product pack: pick **one** depth from the closed menu, answer the four prompts, implement so a **hero still** changes, recapture, stop. Dual-open is allowed when it serves that depth or a red walk—not as the default forever cycle. Stills remain the proof for anything claimed as product.

---

## Source trail

| Doc | Role |
|-----|------|
| **This file** | Post-5.8 doctrine + interesting-SaaS context research |
| `INVESTIGATION_2026-08-02.md` | Evidence of still freeze + dual-open monoculture |
| `REEVALUATION_FULL_2026-08-01.md` | Human score ~5.8 |
| `HYPERPART_PRESENTATION_PROCESS.md` | Goal B chrome language (presentation) |
| `improve/oral-history.md` | Loop lore (monocultures, thrash classes) |
| `scripts/interesting_product_portfolio.py` | Portfolio pick / anti-wave / anti-recipe |
| `antagonist-report-post-5-8.md` | Short handoff only — not a second doctrine |
| `agent-harness-distill.md` | What we stopped loading and why |
| `REPORT_FOR_DAZZLE_FULL_2026-08-01.md` | F1–F7 (hygiene; depth is F6-class) |

**Upstream:** #1626 may close or demote for residual; open successor epic for interesting depth / context research if desired.
