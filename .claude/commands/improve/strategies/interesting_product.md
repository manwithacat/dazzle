# Strategy: interesting_product

**Lane:** example-apps (default) / framework-ux when depth needs a shared primitive
**Force path:** `/improve example-apps interesting_product`
**Also:** `/improve example-apps depth` (alias)
**Doctrine:** `docs/reference/interesting-saas-context.md`
**Handoff:** `docs/reference/antagonist-report-post-5.8.md`
**Umbrella:** post-5.8 Goal B (interesting SaaS) — antagonist 2026-08-02

When **machine residual is green**, do **not** invent another dual-open hop and
call it product. Load this pack: pick **one** depth from the closed menu, answer
four prompts, implement so a **hero still** changes, recapture, stop.

**Stills beat walk green.** Dual-open without recapture is **harness_only**
(Goal A) — log it that way; never claim bake-off lift.

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
dual-open-only cycle labeled as depth; densify when `densify_allowed=0`.

---

## Playbook (one depth slice)

### 1. OBSERVE

```bash
uv run python scripts/improve_example_probes.py --status
# residual_total should be 0 for this strategy
uv run python scripts/improve_policy.py --status
# open hero stills under examples/<app>/.dazzle/qa/screenshots/ — note mtimes
```

### 2. SELECT (log before implement)

In the cycle log, answer **all four** (short):

1. **Peer:** What does a good commercial tool show on this desk’s first screen that we do not?
2. **Surprise:** What one domain-true detail would make a founder lean in?
3. **Still:** Which hero PNG will change, and what will a buyer see differently?
4. **Harness:** Does this need new open-via, or only product surface?
   (If only open-via → this is Goal A; set `harness_only: true` and do not claim Goal B.)

Also log:

```text
depth_id: conversation|document|media|command_density|org_structure|empty_region_honesty
harness_only: false
app: <showcase>
still_paths: examples/<app>/.dazzle/qa/screenshots/<hero>_desktop_light.png
```

### 3. IMPLEMENT

* Prefer **framework-wide** depth primitive if the gap is cross-app
* Else one showcase **icon app** with still proof
* Do **not** ship hop attrs alone under this strategy

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

### 5. RECORD

* `harness_only: false` only if still changed and depth is visible
* No “fleet improved” without antagonist re-score
* No category leadership claims

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
