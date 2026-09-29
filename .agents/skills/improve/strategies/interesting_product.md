# Strategy: interesting_product

**Lane:** example-apps (default) / framework-ux when depth needs a shared primitive
**Force path:** `/improve example-apps interesting_product`
**Also:** `/improve example-apps depth` (alias)
**Doctrine:** `docs/reference/interesting-saas-context.md`
**Handoff:** `docs/reference/antagonist-report-post-5.8.md`
**Umbrella:** post-5.8 Goal B (interesting SaaS) — antagonist 2026-08-02

When **machine residual is green**, do **not** invent another dual-open hop and
call it product. Load this pack: **honor the portfolio recommend**, pick **one**
depth from the closed menu, answer four prompts (peer pack when present),
implement so a **hero still** changes, recapture, stop.

**Stills beat walk green.** Dual-open without recapture is **harness_only**
(Goal A) — log it that way; never claim bake-off lift.

**Oral history:** `improve/oral-history.md` (depth-wave monoculture, panel thrash,
hyperpart coupling). Do not re-learn those by shipping another headshot shelf.

---

## When to pick

* `example_probes residual_total=0` **and** policy force is `interesting_product`
* Hero stills are stale (fleet max mtime ≫ recapture) while residual is green
* ≥ **K** consecutive open-hop / walk cycles under residual=0 (policy cap)
* Operator force: `/improve example-apps interesting_product`

Skip when:

* residual_total > 0 → presentation / demo_fleet / maturity first (Goal A hygiene)
* presentation residual (`ref_as_repr` / `person_as_text` / `delta_theater`) →
  `framework-ux hyperpart_presentation` (immune system — keep)
* `goal_b_coat residual_total>0` → **`example-apps distill`** (Goal C; do not add)
* portfolio `--recommend` is `-` / `interesting_product_saturated=1` → **STOP**
  (no coat; `require_mutation` off)

---

## Closed depth menu (pick **one** per cycle)

| depth_id | Buyer read | Still proof |
|----------|------------|-------------|
| `conversation` | Thread / message trail on work | Hero shows conversation strip or messages |
| `document` | Document or line-item hub | Invoice/project still shows lines or doc region |
| `media` | Pixels not only meta | Asset/brand still shows thumbs or strong visual |
| `command_density` | Multi-panel attention | Command center still has ≥2 regions above fold |
| `org_structure` | Hierarchy people can parse | Tree / reporting people (not only depts) |
| `empty_region_honesty` | No large void / skeleton | Secondary regions filled **or** omitted |

**Refuse:** new example app to “fix” depth; metric tile proliferation;
dual-open-only cycle labeled as depth; densify when `densify_allowed=0`;
**same recipe on the Nth app** while portfolio bans that recipe.

---

## Playbook (one depth slice)

### 1. OBSERVE

```bash
uv run python scripts/improve_example_probes.py --status
# residual_total should be 0 for this strategy
uv run python scripts/improve_policy.py --status
# includes interesting_product portfolio lines when residual green
uv run python scripts/interesting_product_portfolio.py --status
# open hero stills under examples/<app>/.dazzle/qa/screenshots/ — note mtimes
```

### 2. SELECT (portfolio first, then four prompts)

**2a. Portfolio (required)** — honor unless residual heat or red CI appears:

```bash
uv run python scripts/interesting_product_portfolio.py --recommend
# → app depth_id # reason   OR   `-` (saturated — STOP)
uv run python scripts/goal_b_coat.py --status
```

**STOP is a legal cycle.** If `--recommend` prints `-` or policy says
`interesting_product_saturated=1`, do **not** add a region. Log
`saturated, no ship`, leave `require_mutation` off, yield to framework-ux
or wait. A cycle with no Goal B coat is green.

Rules the planner enforces (also in policy status):

| Rule | Meaning |
|------|---------|
| **Anti-wave** | After ≥3 tipward Goal B ships with the same `depth_id`, that depth is banned |
| **Family, not tag** | Recipe is a closed family. `thankful_needs_reply_trail` is `conversation_filter_slice`. Synonyms do not count as novel |
| **Saturate** | One coat-family ship on `(app, depth)`, or live DSL above honest grain, saturates that cell. Do not upgrade it |
| **Icon stacking** | Prefer icon apps for a depth and apps with 1–2 depths already over thin fleet coat on every app — unless the cell is saturated |
| **Peer pack** | If `improve/peer_packs/<app>.toml` exists, Peer prompt must use it. Honor `refuse` |
| **Freeze ratchet** | `scripts/goal_b_coat.py` — conversation/rail/focus/metric counts must not grow. Distill later lowers the caps |

Override portfolio only with a one-line dig reason (e.g. `scenario_underused`
emitter dogfood on a different home). Never override a stop to add another
filter slice.

**2b. Four prompts** (cycle log, short):

1. **Peer:** From peer pack `above_fold` / named commercial peer — what do we lack?
2. **Surprise:** One domain-true detail (pack `surprise_prompts` or better).
3. **Still:** Which hero PNG will change, and what will a buyer see differently?
4. **Harness:** New open-via only, or product surface?
   (If only open-via → Goal A; `harness_only: true`.)

Also log:

```text
depth_id: conversation|document|media|command_density|org_structure|empty_region_honesty
harness_only: false
app: <showcase>   # from portfolio recommend unless overridden
recipe: <closed family>   # conversation_filter_slice / document_rail_slice / … — never a synonym tag
still_paths: examples/<app>/.dazzle/qa/screenshots/<hero>_desktop_light.png
portfolio_reason: <from --recommend>
```

### 3. IMPLEMENT

* Prefer **framework-wide** depth primitive if the **same gap** appeared on ≥3 apps
  this wave (stop painting; lift the primitive)
* Else prefer **icon-app stacking** (2–3 depths coherent on one showcase) over
  the next thin coat on a greenfield app
* **scenario_underused:** if an emitter exists and few apps mount it, one icon
  home + still beats a parallel custom region
* Do **not** ship hop attrs alone under this strategy
* Dig receipt notes must include `depth_id=<id>` (portfolio parses receipts)

### 4. PROVE

```bash
# Recapture the claimed hero(s) same cycle
.venv/bin/python scripts/recapture_demo_fleet_1626.py --apps <app>
# OCR / open the PNG — buyer-visible diff above fold
```

| Gate | Rule |
|------|------|
| Recapture | Hero still mtime after change |
| Visible | Diff readable above fold without walk script |
| Residual | May stay 0 — Goal B is not residual_total |
| Score | Antagonist re-score only after recapture package |
| Portfolio | Unit pin name `test_<app>_<depth>_goal_b.py` so coverage matrix updates |

### 5. RECORD

* `harness_only: false` only if still changed and depth is visible
* No “fleet improved” without antagonist re-score
* No category leadership claims
* If you learned a durable rule, one bullet in `improve/oral-history.md`

---

## Dual-open under this doctrine

| Dual-open **in** policy | Dual-open **out** of policy |
|-------------------------|-----------------------------|
| Depth slice needs multi-hop nav | residual=0 and no still plan |
| Walk/acceptance is red on hop | Cycle goal is only “add another hop label” |
| Framework shares discovery attrs **once** | Nth app triple-open without new primitive |

If the cycle is only open-via / walk labels: force `story_walk` etc. and log
`harness_only: true` — **not** this strategy.

---

## Messaging

| Safe | Forbidden |
|------|-----------|
| “Depth id X with recapture on still Y” | residual=0 ⇒ interesting product |
| “Goal B slice; dual-open was harness only” | Dual-open advances bake-off without stills |
| Fleet human ~5.8 until re-score | Category competitive |

---

## Related

* Presentation chrome (Goal B language): `hyperpart_presentation`
* Investigation of dual-open monoculture: `docs/reference/antagonist-investigation-2026-08-02.md`
* F1 still recapture example: `docs/reference/antagonist-rescore-handoff-2026-08-02.md`
