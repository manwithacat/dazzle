# Python Version Support: Reconnaissance Findings + Outcomes

**Status:** **COMPLETE — shipped v0.82.1 → v0.82.8** (the recon below, §1–§8, is preserved as the original
Phase-0 read-only snapshot; the *Outcomes* section that follows records what actually shipped and where reality
diverged from the recon's predictions).
**Date:** recon 2026-06-09; outcomes appended 2026-06-09 · **Floor:** `requires-python = ">=3.12"` (unchanged) ·
**Primary target:** Python 3.14
**Source plan:** `/Users/james/Desktop/python-version-support-plan.md`

> Location: `docs/migration-findings.md` — tracked. Companion reports: `docs/python-3.14-primary-target.md`
> (perf/primary-target), `docs/superpowers/specs|plans/2026-06-09-pep695-adoption*` (PEP 695).

---

## 0. Headline

Two **plan-assumption corrections** and two **deployment discrepancies** dominate this report; the actual
language-compat risk surface (PEP 594 / 649 / 686) is **small to moderate**.

1. **Toolchain ≠ plan.** Plan assumes `uv` + `pyright` + a lockfile. Reality: **pip** (`actions/setup-python`,
   `cache: pip`), **mypy**, and **no lockfile**. The plan's lockfile-regeneration gates have nothing to act on.
   → see §1, §7 (uv assessment).
2. **`runtime.txt` pins `python-3.11.11`** while `pyproject` requires `>=3.12`. A live floor/deploy
   discrepancy, independent of this initiative. → §6.
3. **`.python-version` contains `dazzle-dev`** (a pyenv *virtualenv name*, not a version). Harmless for pyenv
   local dev, but it is exactly the file Heroku's uv path needs to hold a real version. → §6, §7.
4. PEP 594 removed-module exposure is **zero**. PEP 649 surface is **8 sites, all writes**. PEP 686 surface is
   real but portable (~55 non-test `open()` + 306 `read_text/write_text` without `encoding=`). → §3–5.

---

## Outcomes — what shipped (v0.82.1 → v0.82.8, all green on a 3.12/3.13/3.14 hard matrix)

The initiative completed across eight releases. Sequencing was reordered from the recon's §8 (uv was pulled
ahead of the interpreter cells, on the rationale that it makes multi-interpreter testing trivial), and a
perf-driven **3.14-primary-target** promotion was added beyond the original plan.

| Slice | Shipped | Result |
|---|---|---|
| Deploy/floor pin reconciliation (`runtime.txt` 3.11→3.12; Docker bases) | **v0.82.1** | fixed the live discrepancy from §0/§6 |
| PEP 686 `encoding=` backfill (~278 sites, 6 parallel agents) | **v0.82.1** | §5 surface closed; portable, floor-independent |
| **uv = canonical toolchain** (`uv.lock`, `setup-dazzle` composite → `uv sync --frozen`, `uv pip` for in-job tools, `pygls`→`lsp` extra) | **v0.82.2** | §7 executed; reproducible builds; the §7c work items (CI rewrites, the `\|\| true` hack) all resolved |
| 3.13 CI cell (hard-required) | **v0.82.3** | clean; all native deps incl. xmlsec have 3.13 wheels |
| 3.14 CI cell (allow-failure → then promoted) | **v0.82.4** | see correction ① below |
| `dazzle deploy heroku` uv-buildpack scaffolding (`pyproject.toml`+`uv.lock`+`.python-version`; `--pip` fallback) | **v0.82.5** | §7a downstream story delivered; also fixed deploy deps to `dazzle-dsl[serve]` |
| **3.14 promoted to PRIMARY target + hard CI cell** | **v0.82.6** | new vs recon; see ① and ② |
| **PEP 695 adoption** (18→20 sites, ruff ignores removed) | **v0.82.7 / .8** | §1/§8 lever pulled; see correction ③ |

**Where reality diverged from the recon's predictions:**

- ① **The §2 "most likely 3.14 dependency blocker" (`python-xmlsec`/`lxml`) did NOT materialize.** On CPython
  3.14.5 every dependency — xmlsec included — installs from wheels; the full suite is green on 3.14. The
  recon's caution was correct to flag it, but the gate passed cleanly. 3.14 went from allow-failure to
  hard-required once two *non-Dazzle* reds were cleared (a pygls `asyncio.iscoroutinefunction` deprecation and
  CPython 3.14's `ForwardRef` repr change — both fixed portably, no api-surface baseline regen).
- ② **3.14 is now the *primary* target, not just supported** — a perf-driven addition beyond the plan. Measured
  ~6–12% faster on Dazzle's parse→IR path via the uv tail-call interpreter (`Py_TAIL_CALL_INTERP=1` in uv/pbs
  builds only, *not* GCC `python:3.14-slim`). Full analysis + caveats: `docs/python-3.14-primary-target.md`.
- ③ **The floor was NOT moved, and PEP 695 was decoupled from it.** Key insight (refines §4/§8): PEP 695 syntax
  is legal since 3.12 — it is *floor-independent* and shipped now at `>=3.12`. Only the
  `from __future__ import annotations` cleanup (§4) is genuinely gated on a 3.14 floor (PEP 649). So the floor
  stays `>=3.12` with full 3.12/3.13/3.14 support; **the floor move is the one remaining deferred item** (a
  product decision, revisit when there's concrete reason to drop 3.12 — EOL Oct 2028).

**Still deferred (intentionally):** the floor move (`>=3.13`/`>=3.14`) + the 669-file `__future__`-annotations
cleanup (§4, ADR-0014-aware, needs a 3.14 floor).

**Process note (§7-adjacent):** a uv-specific footgun surfaced — CI lints with the `uv.lock`-pinned ruff, which
can be newer than the local pyenv ruff and flag more sites; v0.82.7 shipped a red `lint` job for exactly this
and was fixed in v0.82.8. Pre-ship lint now uses `uvx ruff@<locked>`.

---

## 1. Declared configuration (plan step 1)

| Setting | Location | Value |
|---|---|---|
| `requires-python` | `pyproject.toml:10` | `">=3.12"` |
| ruff `target-version` | `pyproject.toml:521` | `py312` |
| ruff `line-length` | `pyproject.toml:520` | `100` |
| type checker | `pyproject.toml:461–462` | **mypy**, `python_version = "3.12"` (plan said pyright — N/A) |
| CI matrix | `.github/workflows/ci.yml:50–51` | `python-version: ["3.12"]` (single cell) |
| installer | `.github/actions/setup-dazzle/action.yml:51–68` | `actions/setup-python@v6` + `pip install -e ".[…]"` |
| lockfile | — | **none** (`requirements.txt` is a 1-line stub; deps are `>=` ranges in pyproject) |
| nox/tox | — | none |

**Deliberate, documented deferral already in-repo:** `pyproject.toml:561–571` ignores ruff `UP040/UP046/UP047`
(PEP 695 `class C[T]` / `def fn[T]()` / `type X =`) — a reviewed refactor gated behind a floor move (#1175), not
a metadata side effect. **This is the codebase's actual "adopt new syntax" lever** and the plan does not mention it.

## 2. C-extension / compiled-wheel dependencies (plan step 2 — the new-interpreter gating set)

Distinct third-party deps across all extras: **66**. Core runtime deps: 15. Native/compiled wheels (the constraint
on 3.13/3.14 support and any future free-threaded build):

| Package | Extra | Wheel situation on new interpreters |
|---|---|---|
| `psycopg[binary]>=3.2` | core | bundles libpq; fast wheel shipper — clean 3.13, expected 3.14 |
| `pydantic>=2.0` (→ `pydantic-core`, Rust) | core | abi3 Rust wheels; among the fastest to ship |
| `cryptography>=41` (Rust/OpenSSL) | sso/saml/signing | abi3 wheels; fast shipper |
| `Pillow` | pitch/imagery | C; reliable wheel shipper |
| `tigerbeetle` | tigerbeetle | native client; **verify per-interpreter** |
| `aiokafka` | kafka | optional C accel; mostly pure |
| **`python3-saml` → `lxml` + `python-xmlsec`** | **saml** | **highest risk.** Native `libxmlsec1`; historically the last to ship wheels for a new minor. **This is the most likely 3.14 dependency blocker.** Confined to the `[saml]` extra. |

> Per the plan's guardrail 7 and §6.2: if `python-xmlsec`/`lxml` lacks a 3.14 wheel at remediation time, **stop and
> report** — do not fork/pin a pre-release. 3.13 should be clean across the board.
>
> **OUTCOME:** wheels existed for **both 3.13 and 3.14** — `xmlsec==1.3.17` installs cleanly on CPython 3.14.5.
> No blocker materialized; the full suite is green on all three interpreters. (See Outcomes ①.)

## 3. PEP 594 removed-module exposure (plan step 3)

**Zero hits.** Grepped `cgi, cgitb, telnetlib, nntplib, smtpd, aifc, audioop, chunk, crypt, imghdr, mailcap, msilib,
nis, ossaudiodev, pipes, sndhdr, spwd, sunau, uu, xdrlib` across `src/`. **Phase 2.1 removed-module remediation is
empty work here** — confirm-and-close, do not budget for it.

## 4. PEP 649 / deferred-annotation surface (plan step 4)

**Runtime annotation introspection: 8 sites — all are `__annotations__` *assignments*, not reads:**

```
src/dazzle/http/runtime/route_generator.py:191, 2006, 2059, 4281, 4308
src/dazzle/http/graphql/integration.py:323, 361, 394
```

These dynamically build FastAPI/GraphQL handler signatures by **setting** `fn.__annotations__ = {…}`. Under PEP 649
(3.14) deferred annotations, *assigning* a plain dict still works; the interaction to verify is whether FastAPI's
own annotation *reading* of these synthetic handlers changes. **Classify as "review on 3.14," not "broken."**
`typing.get_args/get_origin`: 6 sites (static-analysis paths; low risk).

**`from __future__ import annotations`: 669 files** — and this is the plan's biggest oversimplification:

| Scope | Count | Why it matters |
|---|---|---|
| total `src/dazzle/**.py` | 669 | Pervasive; load-bearing for forward refs, **not** a uniform 3.12 compat shim |
| `*_routes.py` | 7 | **ADR-0014 forbids `from __future__ import annotations` in FastAPI route files** (runtime needs real annotations at import). Removal here is *banned*, not "dead shim cleanup". |
| `src/dazzle/http/**` | 228 | The runtime layer where annotation-resolution timing actually bites |

→ **The plan's Phase 3 "remove now-dead compatibility shims (e.g. `from __future__ import annotations`)" is unsafe
as written for this codebase.** It is a 669-file diff that collides with ADR-0014 and changes runtime annotation
timing. Treat any future-annotations change as a PEP-649-aware, ADR-0014-aware task gated on a **floor ≥ 3.14**
decision — never a mechanical sweep.

## 5. PEP 686 implicit-encoding surface (plan step 5 — report counts, do not fix)

`src/dazzle/**.py`, excluding binary modes and vendored `dist/` JS/CSS:

| Pattern | All | Non-test |
|---|---|---|
| `open(...)` without `encoding=` | 73 | 55 |
| `.read_text()` / `.write_text()` without `encoding=` | 306 | 306 |

Most read paths are DSL/template/config file reads (`core/`, parser, loaders) where UTF-8 is the intended
encoding — so the 3.15 change is mostly *benign* but should be made *explicit*. This is **fully portable to 3.12**
and the cheapest independent win (plan §9). Recommend scheduling it standalone, decoupled from any floor move.
(Raw grep also flags `open(` inside `src/dazzle/page/runtime/static/dist/*.min.js` — vendored htmx, **false positives**,
excluded from the counts above.)

## 6. Deployment / runtime pins (cross-check vs guardrail "do not drop a version the runtime still pins")

| File | Content | Issue |
|---|---|---|
| `Procfile` | `web: uvicorn dazzle_http.runtime.app_factory:create_app_factory --factory …` | fine |
| `runtime.txt` | `python-3.11.11` | **Conflicts with `requires-python>=3.12`.** Either stale or deploys on a pinned 3.11. Heroku also **deprecated `runtime.txt`** in favour of `.python-version`. |
| `.python-version` | `dazzle-dev` | pyenv venv name, not a version. Fine for local pyenv; **would break Heroku's `.python-version` / uv path**, which needs `3.12` (or `3.13`). |

**Action regardless of this initiative:** reconcile the 3.11.11 `runtime.txt` against the 3.12 floor.

---

## 7. uv vs pip — quantified assessment (requested)

> Framing correction: **pip is not being retired.** CPython ships pip indefinitely (PEP 453 ensurepip). The real
> question is what we lose by **dropping pip from *our* workflow** in favour of uv. Answer: little operationally,
> and Heroku now actively *rewards* the switch.

### 7a. The Heroku finding (validates your hypothesis — with prerequisites)

Heroku's official Python buildpack has **first-class uv support since 13 May 2025**, kept current through 2026
(uv 0.10.9 as of 13 Mar 2026):

- [Python buildpacks now support uv — Heroku changelog #3238](https://devcenter.heroku.com/changelog-items/3238)
- [updated to uv 0.10.9 (Mar 2026)](https://devcenter.heroku.com/changelog-items/3625) · [heroku-buildpack-python](https://elements.heroku.com/buildpacks/heroku/heroku-buildpack-python)

To activate the uv path, an app must have **`pyproject.toml` + `uv.lock` + `.python-version`**, and must **remove
`requirements.txt` / `Pipfile` / `poetry.lock`**. For Dazzle + downstream projects that means three concrete edits:
1. commit a `uv.lock`,
2. delete the stub `requirements.txt` **and** the deprecated `runtime.txt`,
3. put a real version (`3.12`) in `.python-version` (currently `dazzle-dev`).

**Net Heroku effect:** Heroku's pip path resolves the full `>=`-range tree from scratch on every build; the uv path
installs from a hash-pinned `uv.lock` with a parallel downloader and a shared cache → **the single biggest, most
defensible build-time win**, and it makes deploys *reproducible* (today they are not — unpinned ranges resolve
differently over time).

### 7b. Speed gain (Astral published benchmarks + Dazzle's dependency shape)

uv is not installed locally, so these are vendor-published ranges, not measured-here numbers:

- **Warm cache:** uv ≈ 8–10× faster than pip for installs.
- **Cold resolve+install:** 10–100× (the regime Heroku/CI cold builds live in), because uv resolves in parallel and
  hard-links from a global cache instead of re-extracting wheels.

Dazzle's shape *amplifies* this: **66 distinct deps**, install dominated by **fetching large pre-built native
wheels** (psycopg-binary/libpq, pydantic-core, cryptography, Pillow, lxml/xmlsec) — exactly where uv's parallel
download + global cache helps most. Expect the largest wins on **CI cold cells** (and a 3-interpreter matrix
multiplies that benefit 3×) and on **Heroku cold builds**. A measured before/after should be taken on a CI runner
once uv is installed, not asserted from these ranges.

### 7c. What we actually lose by dropping pip from the workflow

| Loss / cost | Severity | Notes |
|---|---|---|
| **Ubiquity / zero-bootstrap** | low–med | pip is always present; uv is an extra bootstrap (one curl/pipx line; Heroku & GH Actions both provide it). |
| **`uv.lock` becomes a required, committed artifact** | low | A *gain* for reproducibility, but a new review surface. Aligns with global rule "pin exact, not ranges" — uv pins hashes. |
| **CI rewrites** | med | `setup-dazzle` composite, `ci.yml`, `publish-pypi.yml` move to `uv sync`/`uv pip`. **`bandit`/`pip-audit` steps** (`ci.yml:145,184,216`) need `uv pip install` or `uv export` shims. |
| **`optional-pip … \|\| true` best-effort pattern** (`setup-dazzle/action.yml:62–68`, swallows pygls/bleach failures) | med | uv has no clean "install best-effort, ignore failure" idiom in `uv sync`; this needs redesign into a proper optional extra. |
| **Editable install (`pip install -e`)** | none | uv supports editable + workspace installs natively. |
| **Downstream user docs / muscle memory** | med | "many Dazzle projects host on Heroku" → migration guidance + the 3-file Heroku change must be documented for users, not just the framework. |
| **pip-only corner cases** (custom index/proxy/`pip.conf`) | low | uv has equivalents but config differs; verify if any downstream uses private indexes. |

**Nothing in the loss column is a blocker.** The two that need real work are CI step rewrites (incl. bandit/
pip-audit) and replacing the `|| true` best-effort optional-install hack.

### 7d. Recommendation on uv

**Worth doing, and best decoupled from the version-support matrix.** It is the highest-leverage *deploy/CI* change
(reproducible Heroku builds + faster cold installs) but it is **orthogonal to** extending interpreter support.
Sequence it as its own slice so a uv migration failure can't stall (or be conflated with) 3.13/3.14 support — and
so the matrix work in Phase 1 doesn't have to absorb a toolchain swap at the same time. Capture a measured
before/after on a CI runner to put a real number on §7b before committing.

---

## 8. Risk-surface summary & recommended resequencing

| Surface | Dazzle exposure | Plan's weighting | Reality |
|---|---|---|---|
| PEP 594 removed modules | **0 hits** | Phase 2.1 remediation | drop — confirm-only |
| PEP 649 annotations | 8 writes, 6 get_args | "audit risk surface" | low; "review on 3.14" |
| `from __future__` removal | 669 files, ADR-0014 ban | "remove dead shims" (Phase 3) | **unsafe as written**; floor-≥3.14 + ADR-aware only |
| PEP 686 encoding | 55 + 306 sites | §9 forward note | correct; cheapest portable win, schedule standalone |
| PEP 695 modernisation | already deferred in ruff (#1175) | **not mentioned** | this is the real "new syntax" lever post-floor-move |
| C-ext wheels (3.14) | xmlsec/lxml laggard | Phase 0 step 2 | correct instinct; `[saml]` is the watch item |
| Toolchain (uv/pyright/lock) | pip/mypy/no-lock | assumed present | **false** — reskin before executing |
| Heroku/runtime pins | 3.11.11 vs >=3.12 | guardrail only | live discrepancy to fix now |

**Recommended order (Dazzle-accurate) — annotated with what actually shipped:**
1. ✅ **This report** (gate) + reconcile `runtime.txt`/`.python-version` vs the 3.12 floor → **v0.82.1**.
2. ✅ **PEP 686 `encoding=` backfill** → **v0.82.1** (~278 sites).
3. ↪ **uv migration** — *reordered ahead of the cells* (it makes multi-interpreter testing trivial) → **v0.82.2**;
   downstream Heroku scaffolding → **v0.82.5**.
4. ✅ **3.13 CI cell** → **v0.82.3** (hard-required).
5. ✅ **3.14 cell** → **v0.82.4** (allow-fail) → **v0.82.6** (promoted to **primary + hard**); the `[saml]`/xmlsec
   gate passed cleanly (Outcomes ①).
6. ↪ **PEP 695** — *split out and shipped at the current floor* (it's floor-independent) → **v0.82.7/.8**. The
   **floor move + `__future__`-annotations cleanup remain deferred** (product decision; Outcomes ③).

**Initiative complete.** Floor stays `>=3.12`; 3.14 is the primary target; the only open item is the floor move
itself, intentionally deferred.
