# Stem: chrome vs protocol

## Claim

Two Hyperparts can **look** like the same modal family and still be different
L1s. Agents must separate:

| Axis | Question | Example |
|------|----------|---------|
| **Chrome** | What does the user *see* (modal shell, focus trap, Esc, buttons)? | `<dialog>`, alert layout, destructive Confirm |
| **Protocol** | How does the surface *attach* to the app and to htmx? | `showModal` by id vs intercept `htmx:confirm` |

**Same chrome ≠ same Hyperpart.** Map **job**, not screenshot.

## Related orthogonality: addressing vs request gating

| Mode | Meaning | Hyperpart |
|------|---------|-----------|
| **Addressing** | Trigger names a **specific** overlay instance (usually by id) | `dialog`, `drawer`, `command` opener |
| **Request gating** | Overlay holds an **already-declared** request until the user accepts | `confirm` via `hx-confirm` |

Addressing answers “which shell opens?”
Gating answers “may this request proceed?”

## Taxonomy (use when splitting overlay L1s)

| Dimension | Ask | `dialog` | `confirm` | `confirm-panel` |
|-----------|-----|----------|-----------|-----------------|
| **Job** | What is the user doing? | Modal workspace / custom decision UI | Yes/no before a serious action runs | Checklist consent before a primary arms |
| **Lifecycle** | How long does the shell live? | Authored in page (or swapped in); N instances | Lazy singleton; reused | In-flow form region |
| **Who authors markup** | Who writes the body? | Author full dialog HTML | Message = `hx-confirm` string; chrome from controller | Author checklist + parked href |
| **htmx attach** | How does it connect? | Optional `hx-*` on buttons inside | **Protocol:** `htmx:confirm` → issue/drop | No modal; gate promotes `href` |

## Reconstruct

1. Need **custom body / multi-control modal**? → `dialog` (addressing).
2. Need **fleet-wide yes/no on existing `hx-*`** with no per-button dialog? → `confirm` (gating).
3. Need **multi-checkbox consent** before arming? → `confirm-panel`.
4. Do **not** invent `POST /confirm` for the dialog itself — exchange is the underlying action.
5. shadcn `AlertDialog` maps by **job** to confirm / confirm-panel / dialog — not one HM name.

## Not this

- Merging dialog and confirm because both use `<dialog>`.
- Building a full dialog for every delete instead of `hx-confirm`.
- A confirm API route that only exists to show the modal.

## Expressions

- pick-a-surface › Modals / confirm / gates
- `site/agents/dialog.md`, `confirm.md`, `confirm-panel.md`
- Controllers: `dz-dialog.js` (addressing), `dz-confirm.js` (gating), `dz-confirm-gate.js`
- Recipes: `overlay-dialog`, `confirm-affordance`
