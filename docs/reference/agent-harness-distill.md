# Agent harness distill evaluation (2026-08)

**Audience:** Maintainers deciding what agents still need loaded
**Stance:** Evaluate overspecification; prefer stems + gates over oral lore
**Related:** `stems/epistemic-layout.md`, `improve/oral-history.md`, ADR-0002

This is an evaluation, not a bulk deletion PR. Cuts should be deliberate and
gated so we do not throw away hard-won counter-priors.

---

## Volume snapshot (order of magnitude)

| Surface | Scale | Notes |
|---------|-------|--------|
| `AGENTS.md` | ~540 lines | Entry + pointers; still dense |
| `.claude/commands/improve.md` | ~640 lines | Driver; force table + schedule |
| Improve strategies (×24) | ~3k lines total | Many are healthy playbooks |
| Capability-map | ~1.7k lines | **Oral history dump** — stamps dominate |
| Framework stems | 8 short stems | Healthy; already distilled |
| HM stems | many, some 80–150 lines | Composition-heavy; may overlap docs |
| ADRs | 54 files | Long tail; many still load-bearing |
| Counter-priors | ~15 | High value, short |
| Deferred decisions | few | Correct parking lot |

**Hypothesis:** The harness is not overspecified in *stems*; it is overweight in
**improve capability-map history**, **duplicated doctrine** (interesting SaaS
said three times), and **2025-era MCP/CLI boundary prose** that agents re-read
every session without new signal.

---

## Keep (high signal / low volume)

- **Stems** (framework + HM): reconstruct judgement; do not merge into one blob.
- **Counter-priors:** pathology list agents re-suggest; keep short and mean.
- **Dig contracts / residual probes:** machine honesty under automation.
- **Closed menus** (depth ids, presentation role×host): selection > invention.
- **ADR-0002 MCP/CLI boundary intent** (“can the agent keep thinking?”) — still
  true; *implementation* may move with MCP 2026-07-28 (see MCP note).
- **Clean-breaks, dsl-first, four-layer-stack, rbac-and-scope.**

---

## Distill candidates (overspecified or counterproductive)

### 1. Capability-map as conversation log

**Problem:** USED@cycle stamps and multi-paragraph cycle digests are oral
history that **expands forever** and crowds the map agents are told to read.

**Distill:**

- Keep a short inventory table (tool → lane → last USED cycle number only).
- Move narrative rules to `improve/oral-history.md` (done for v0).
- Cap stamp prose; capability-sweep should not append 1k tokens of “Next:”.

### 2. Doctrine triple-copy

Interesting SaaS lives in:

- `docs/reference/interesting-saas-context.md` (canonical)
- `interesting_product.md` strategy
- `antagonist-report-post-5-8.md`
- exemplar / operator guide snippets

**Distill:** One canonical + one playbook + one-line pointers elsewhere.
Antagonist short report can become a 20-line handoff.

### 3. ADRs: archive vs active

54 ADRs is fine as a ledger; it is bad as **must-read context**.

**Distill:**

- Mark **Active** vs **Historical** in `docs/adr/README` (or INDEX).
- Active set for agents: clean-breaks, MCP/CLI boundary, frozen IR, RBAC layers,
  SSR/HTMX, poly_ref if still hot, permit/scope.
- Historical: early docs-site, one-off migration notes — link only when
  changing that subsystem.

Do **not** merge ADRs into stems. Stems are timeless; ADRs are dated decisions.

### 4. HM stems vs gallery vs presentation process

Some HM stems restate gallery aesthetics and host chrome already in
`hyperpart-presentation.md`.

**Distill:** Stem = judgement rule (≤40 lines). Long matrices stay in reference
docs. Agents load stem first; open matrix only when implementing chrome.

### 5. Pre-2026 MCP session folklore

Process lock, session dirs, “MCP blocks Claude” guidance was necessary when
transports held sessions and tools blocked the thread.

**Distill:** Keep the **boundary test** (read vs side-effect / long work).
Rewrite “MCP freezes the agent” as “long tools still need CLI or Tasks/MRTR”
once on `mcp` v2 / 2026-07-28. See `docs/reference/mcp-2026-07-28-opportunity.md`.

### 6. Improve strategy sprawl

~24 strategies is mostly real lanes. Candidates to **fold**:

- Near-duplicate hygiene: `semgrep_hygiene` cadence vs self_audit overlap messaging
- Gallery vs hyperpart_coherence (shared “visual truth” language)

Do not fold Goal B into product_maturity — different proof.

### 7. Example-app agent packs

Per-example `AGENT_DOMAIN.md` / stems are good when short. Audit for copy-paste
of framework CLAUDE that **fights** current counter-priors (empty desk, metric
theater). Prefer “inherit framework + 30 lines domain.”

---

## Oral history that was not surfaced (now partially fixed)

| Lore | Was only in… | Surfaced to |
|------|----------------|-------------|
| Depth wave monoculture | git log + operator memory | `improve/oral-history.md` + portfolio script |
| Acceptance re-panel thrash | cycle stamps | oral-history |
| Smoke stale suppress | improve-policy.yaml | already policy; oral-history |
| LFS empty-hero | CI fails | oral-history |
| ensure_missing columns | emergency fix ships | oral-history |
| Peer packs underbuilt | doctrine §6 | `improve/peer_packs/` |

**Process:** self-audit should ask “new durable rule?” → one bullet in
oral-history same week.

---

## Recommended sequence (no big-bang rewrite)

1. **Done in this pass:** portfolio planner, peer packs, oral-history v0,
   playbook SELECT rules.
2. **Next:** capability-map stamp diet (table only + link oral-history).
3. **Next:** ADR INDEX Active/Historical labels (no content rewrite).
4. **Later:** MCP v2 migration spike (pin `<2` until then).
5. **Later:** HM stem length pass (split matrix out of stems).
6. **Avoid:** “one mega AGENTS.md” or deleting counter-priors.

---

## Overspecification test (use when editing guidance)

Before adding a paragraph to agent-facing docs:

1. Is it a **stem** (timeless judgement), **ADR** (dated decision),
   **counter-prior** (pathology), **playbook step**, or **oral history**?
2. Does a gate or probe already enforce it? Prefer gate > prose.
3. Will this still be true after residual=0 / MCP v2 / next model generation?
4. If agents ignore it today, is it wrong or unenforced? Fix enforcement first.

If the answer is “we said this three times already,” delete two copies.
