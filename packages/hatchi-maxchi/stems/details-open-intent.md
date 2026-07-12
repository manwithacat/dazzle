# Stem: details open intent

## Claim

Native `<details>` is an open/closed **primitive**, not a product behaviour.
**Same substrate, different stems:** open intent is part of the Hyperpart’s
identity. Agents must **declare intent** before shipping multi-`<details>` UI.

| Intent | Meaning | Typical stems | How exclusivity/dismiss is enforced |
|--------|---------|---------------|-------------------------------------|
| **exclusive** | One peer panel open at a time | `menubar`, `navigation-menu`, `accordion` | Controller (`dz-menubar.js`, `dz-navigation-menu.js`) **or** shared HTML `name=` (accordion) |
| **multi_open** | Peers stay open together | `tree` | **No** exclusive controller — forest is native multi-open by design |

**Dismiss** (outside click / Escape) is required for **app chrome** exclusive
panels (menubar, product nav). It is **not** required for accordion (page
content) or tree (hierarchical browse).

## Reconstruct

1. Count peer `<details>` under one chrome root or group.
2. Ask: should opening B close A?
   - Yes → exclusive (controller or `name=`).
   - No → multi_open (do **not** add exclusive-open JS).
3. Ask: is this transient chrome (menu) or persistent content (tree/FAQ)?
   - Chrome → outside dismiss + Escape in the controller.
   - Content → leave open state on the DOM.
4. Pin intent with a gallery probe before claiming “fixed”:
   - `packages/hatchi-maxchi/tools/gallery_probes.py` / `scripts/hm_gallery_probes.py`
   - Catalog: `GALLERY_PROBES.md`
   - Strategy: monorepo `improve/strategies/gallery_probes.md`

## Not this

- Treating all multi-`<details>` as bugs to “fix” with exclusive-open.
- Shipping menubar/nav without the controller (native multi-open + no outside dismiss).
- Adding exclusive-open to `tree` “for consistency” with menubar.
- Relying on gallery dual roots (`.hm-preview` vs `.hm-contract-live__preview`)
  as one forest when validating interaction — probes scope to `.hm-preview`.

## Expressions

- Controllers: `controllers/dz-menubar.js`, `controllers/dz-navigation-menu.js`
- Dual-locks: `contracts/menubar.py`, `contracts/navigation_menu.py`, `contracts/tree.py`
- Probes: `menubar.exclusive_open`, `menubar.dismiss_outside`,
  `navigation_menu.exclusive_open`, `navigation_menu.dismiss_outside`,
  `accordion.exclusive_open`, `tree.multi_open`
- Agent packs: `site/agents/menubar.md`, `navigation-menu.md`, `accordion.md`, `tree.md`
- Registry Guidance on those Hyperparts (seams / pitfalls / do-dont)
