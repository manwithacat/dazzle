---
id: duplicated_business_rule
name: Duplicated business rule with no single owner
layer: filter
status: active
summary: >-
  A rule that the framework already owns — minor-unit scale, role-name
  normalisation, the entity→URL slug — re-implemented at a second call site
  because nobody could tell it was already owned. The second copy is always
  slightly wrong, and the drift is invisible until two surfaces disagree on
  screen. Three real instances shipped behind green gates: `format_cell`
  hardcoded `/100` while `render/filters` honoured `CURRENCY_SCALES` (JPY
  rendered 100x too small in tables and CSV while the edit form was right);
  `check_deny_roles` normalised neither side of the role comparison while
  `check_require_roles` normalised one; and three URL sites re-derived the slug
  without `.lower()`. Find the canonical helper, import it, and never
  re-derive.
triggers_text:
  - "hardcoded default"
  - "fallback value"
  - "or GBP"
  - "just add .lower()"
  - "simple to just inline"
  - "second implementation"
  - "does it match the other one"
  - "why does the table disagree with the form"
  - "one place shows USD and another shows GBP"
triggers_code:
  - 'Decimal\(.*\)\s*/\s*100\b'
  - '\.replace\(["'']_["''],\s*["'']-["'']\)(?!\s*\.lower)'
  - 'removeprefix\(["'']role_["'']\)'
  - '["'']GBP["'']\s*\)?\s*$'
  - ':\s*["'']GBP["'']'
refs:
  adrs: []
  kb_patterns: []
  tests:
    - tests/unit/test_money_scale_parity.py
    - tests/unit/test_dedup_footgun_gates.py
    - tests/unit/test_slug_case_consistency.py
---

## The corpus prior

*A rule is short, so inline it.*

The training-data shape is that a small expression has no owner and gets
re-typed wherever it is needed. That is right for genuinely small rules and
wrong for rules the framework already owns, because the inline copy has no way
to track the canonical one.

## Wrong shape

Re-deriving a rule that has a helper:

```python
# WRONG — minor units are not always /100
major = Decimal(int(minor)) / 100
path = f"/{surface.name.replace('_', '-')}"     # missing .lower()
denied = set(deny_roles)                        # no prefix normalisation
```

## Right shape

Import the owner:

```python
# RIGHT
from dazzle.core.ir.money import get_currency_scale
from dazzle.core.strings import entity_slug, normalize_role

major = Decimal(int(minor)) / (10 ** get_currency_scale(code))
path = f"/{entity_slug(surface.name)}"
denied = {normalize_role(r) for r in deny_roles}
```

## Why this matters here

Three real instances shipped behind green gates:

| Rule | Canonical owner | Second copy | Consequence |
|---|---|---|---|
| Minor-unit → major | `core.ir.money.get_currency_scale` | `format_cell._currency` divided by a literal `100`, formatted `,.2f` | JPY 1500 rendered `15.00 JPY` — **100x wrong** — in tables and CSV, while the edit form showed the truth. Zero-decimal currencies understated 100x; 3-decimal dinars overstated 10x. |
| Role-name normalisation | `core.strings.normalize_role` | `check_deny_roles` normalised **neither** side | A `role_`-prefixed DB role never intersected a bare DSL persona name, so `deny:` silently stopped denying. Latent only because nothing emitted the prefix yet. |
| Entity → URL slug | `core.strings.entity_slug` | three sites did `.replace("_","-")` without `.lower()` | For a mixed-case name the **registered route** and the breadcrumb link to it disagreed — the #1421/#1426 dead-link class. |

All three passed every gate that existed at the time.

## Why the gates missed them

Structural gates key on a **code shape** against a **baseline that already
contains the debt**:

- `test_clone_ratchet` clusters by *token structure*; these copies differ in
  arity, so they never shared a signature.
- `test_dedup_footgun_gates` greps for the *literal text* of formulas it was
  authored with. `Decimal(x) / 100` was not one of them.
- `test_api_surface_drift` pins *what exists*, not *who uses it*.

The missing check is: **"N sites implement this rule — do they agree?"** That
needs a value-table comparison against the canonical function, not a pattern
match. `test_money_scale_parity.py` is the current answer for currency.

## When the pattern *must* be local

Some `.replace("_", "-")` calls are a **different rule**, not this one:

- CLI flags — `--param-name` in `mcp/cli_help.py`
- locale codes — `en_GB` → `en-GB` in `i18n/display_locale.py`
- free-text search candidates — `cli/spec.py`
- word-splitting to build a label — `render/open_discovery.py`

A gate that flags those gets disabled in a week, so
`test_slug_case_consistency.py` pins a **file list** rather than the whole tree.
Adding a genuinely new slug site means adding it to that list.

## Related

- [silent-control-flow](silent-control-flow.md) — when the duplicated rule is a
  retry or a poll rather than a formula.
