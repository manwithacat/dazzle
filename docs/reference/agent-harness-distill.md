# Agent harness distill

**Audience:** Maintainers + agents deciding what to *stop* loading
**Success criterion (agent-facing):** Less duplicative / oral context, same
judgement — gates and stems still win.
**Related:** `stems/epistemic-layout.md`, `improve/oral-history.md`, ADR INDEX

This is not a human-docs polish exercise. The consumer is a coding agent that
overweights any prose placed in always-on paths.

---

## Success criteria (agent consumer)

| Criterion | Check |
|-----------|--------|
| **Map is a table, not a chat log** | capability-map ≪ 300 lines; no multi-KB cycle digests |
| **One doctrine per topic** | Goal B: interesting-saas-context + playbook only; antagonist report ≤1 screen |
| **ADRs are on-demand** | INDEX has Active set; agents not told to pre-load the ledger |
| **Lore has a home** | Durable thrash classes → `improve/oral-history.md` once |
| **Stamp rule is cheap** | Driver stamps Last-exercised cells only |
| **Gates > prose** | Counter-priors / residual / dig contracts still enforce hard truths |
| **No resurrected thrash** | Capability-sweep does not re-grow cycle-note archives |

If an agent still needs a deleted paragraph to act correctly, **the gate or
stem was wrong** — restore as a stem/counter-prior/gate, not as oral dump.

---

## Done (2026-08-10)

| Surface | Before | After |
|---------|--------|--------|
| `.claude/commands/improve/capability-map.md` | ~1700 lines (cycle digests) | ~150 lines: vocab + registry + ≤5 sweep one-liners |
| `docs/reference/antagonist-report-post-5-8.md` | Second full doctrine | Short pointer to interesting-saas-context |
| `docs/adr/INDEX.md` | Flat must-scan ledger | **Active** table + historical full list |
| `improve.md` stamp rule | Implied narrative stamps | Explicit: table only; lore → oral-history |
| Path honesty | Mixed `improve/capability-map.md` | Canonical `.claude/commands/improve/…` |
| MCP boundary (AGENTS) | Session-era freeze language | Stateless protocol + CLI for long work |

Not bulk-deleted (still high signal): stems, counter-priors, dig contracts,
closed depth menu, strategy playbooks (action steps).

---

## Still optional later

| Candidate | Why wait |
|-----------|----------|
| HM stem length | Split matrix vs judgement when editing those stems |
| AGENTS architecture table | Drift-gated; trim only with intentional gate update |
| Strategy fold (gallery vs coherence) | Real lanes; not pure duplication |
| Capability-map row count | Inventory itself is useful; only *prose* was thrash |

---

## Anti-patterns this pass removes

1. **Capability-map as improve-log mirror** — re-told every ship; used as
   “what to do next” instead of residual/policy/portfolio.
2. **Doctrine triple-copy** — same Goal B rules in antagonist report +
   doctrine + playbook (agent re-decides which is canonical).
3. **ADR pre-load** — 50+ long paragraphs of subsystem history as if curriculum.
4. **Session-MCP folklore** as always-on fear — “MCP freezes the agent” without
   distinguishing long tools vs knowledge tools after stateless SDK.

---

## Maintenance rule

When you learn a durable improve lesson:

1. Prefer a **gate** or **probe residual**.
2. Else one bullet in **`improve/oral-history.md`**.
3. Else a **stem / counter-prior**.
4. **Never** append another essay to capability-map.
