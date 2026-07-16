# Decisions (package constitution)

Short, frozen **why** records for HaTchi-MaXchi. They are **expressions** of
package **stems** (`stems/INDEX.md`), not a parallel doctrine. Reconstruct from
`stems/` first; open a decision when you need dated history or status.

| ID | Title | Status |
|----|--------|--------|
| [0001](0001-hyperpart-not-component.md) | Hyperpart is not a component | Accepted |
| [0002](0002-three-layers.md) | Three layers: recipe, surface, host | Accepted |
| [0003](0003-composition-declared.md) | Composition is declared (and refusal is too) | Accepted |
| [0004](0004-invention-ladder.md) | Invention ladder | Accepted |
| [0005](0005-morphing-policy.md) | Morphing policy (htmx4) | Accepted |
| [0006](0006-dom-identity-and-state.md) | DOM identity and DOM-carried state | Accepted |
| [0007](0007-no-alpine-in-core.md) | No Alpine.js in HM core | Accepted |
| [0008](0008-template-lint-posture.md) | Template lint posture | Accepted |
| [0009](0009-carousel-stage-and-motion.md) | Carousel: stage, composition, wrap, autoplay | Accepted |
| [0010](0010-controller-coding-standards.md) | HM controller coding standards | Accepted |
| [0011](0011-toast-page-chrome.md) | Toast as page chrome (stack host + emission) | Accepted |

**How agents should use these**

- Open a decision when **challenging a rule**, not when implementing a part.
- Day-to-day procedure lives in `docs/agent/` and `AGENTS.md`.
- If a decision and a playbook disagree on *what to do*, follow `AGENTS.md`, then
  open an issue to reconcile; if they disagree on *why*, the decision wins until
  revised.

**Not every preference needs a decision.** Prefer playbooks for procedures and
machine maps for graphs. Add a decision only when a misconception is costly and
recurring (e.g. “merge combobox and grid select”).
