# Framework stems — index

| Stem | One line |
|------|----------|
| [dsl-first](dsl-first.md) | The DSL (and frozen AppSpec IR) is the maintained artefact; runtime projects it |
| [agent-first](agent-first.md) | Agents primarily author; humans review; precision beats ergonomic ambiguity |
| [hypermedia-ssr](hypermedia-ssr.md) | Server owns HTML; HTMX swaps fragments; no SPA client state graph |
| [four-layer-stack](four-layer-stack.md) | `http → page → render → core` — dependencies only downward |
| [authoring-boundary](authoring-boundary.md) | Structural Dazzle authoring stays in-session; APIs get data, not DSL writes |
| [clean-breaks](clean-breaks.md) | No backward-compat shims; update all callers in the same change |
| [rbac-and-scope](rbac-and-scope.md) | Permit vs scope are separate; never collapse into one “auth” blob |
| [epistemic-layout](epistemic-layout.md) | Stems / AGENTS / ADRs / DDs / counter-priors / gates — hierarchy of reconstruction |

**Not stems (sibling epistemic classes):**

| Class | Path | Use when |
|-------|------|----------|
| Deferred Decisions | [`docs/decisions/`](../docs/decisions/INDEX.md) | Parked plan + consumer-force reopen (e.g. [DD-001](../docs/decisions/DD-001-1617-poly-ref-and-sti-eav.md) for #1621/#1622) |
| Counter-priors | [`docs/counter-priors/`](../docs/counter-priors/INDEX.md) | Corpus pathologies the agent will re-suggest |
| Practice note | [`docs/architecture/epistemic-engineering-practice.md`](../docs/architecture/epistemic-engineering-practice.md) | How this repo applies epistemic engineering |

**Related packages:** [HaTchi-MaXchi stems](../packages/hatchi-maxchi/stems/INDEX.md)
**Examples:** each `examples/*/stems/` inherits this index and adds domain stems.
