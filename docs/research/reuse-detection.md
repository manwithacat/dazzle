# Can a cheap detector catch re-implemented capability before it's written?

*An empirical investigation, June 2026.*

## Abstract

The strongest measured agent-production bias is **duplication-instead-of-reuse** —
an agent re-implements a helper that already exists because its context window
didn't contain it. We ship a counter-prior for it
([`reinvented-capability`](../counter-priors/reinvented-capability.md)), whose fix
is "search before you write." This note asks whether that search can be *automated
cheaply*: a Type-2 clone detector over the project's own (agent-generated) code. The
answer is yes-with-a-caveat. A ~70-line AST detector finds that **3.2% of functions
(220 of 6,827) sit in near-duplicate clusters**, and the clusters include genuine
re-implemented capability — four separate files each re-deriving "try to import X,
return a bool"; a baseline-diff helper copied five times; a DB-init routine copied
across three stores. But the same detector also flags *parallel-by-design* families
(CLI sub-commands, route handlers) where the duplication is a judgment call. So a
cheap reuse check is feasible and finds real signal — but it is a **screen, not a
verdict**: it needs the same convict/acquit pass every other part of this programme
requires.

## Motivation

The [context-bounds spike](context-bounds-prediction.md) deliberately left one half
of the context problem untouched: **B(ii), missing reuse candidates.** Unlike
missing dependencies, the helper you should reuse is *not* in your call graph — if
it were, you'd already call it. It's a capability search, and the
[`reinvented-capability`](../counter-priors/reinvented-capability.md) counter-prior
prescribes running it "before you write." This note tests whether that search is
cheap enough to automate, by measuring how much re-implemented capability already
exists in this codebase and whether a trivial detector finds it.

## Method

[`clone_detect.py`](scripts/clone_detect.py) parses every function in `src/dazzle`
and builds a **structural signature**: it blanks local names, arguments, and
literals (keeping only their *type*) but retains the control-flow shape and the
called method / keyword names — the "API skeleton." Two functions sharing a
signature are Type-2 clones: the same logic with renamed locals. Functions are
clustered by signature; clusters of size ≥ 2 (and ≥ 5 statements, to skip trivial
stubs) are reported.

The pre-write-check framing is the key one: this index, *queried with the signature
of a function the agent is about to write*, answers "does this already exist?" — the
counter-prior's discriminating question, automated.

## Results

| metric | value |
|---|---|
| functions analysed (≥ 5 statements) | 6,827 |
| near-duplicate clusters (size ≥ 2) | 99 |
| functions in a clone cluster | 220 (**3.2%**) |

For comparison, a peer-reviewed 2025 study (FSE) measured Type-1/2 clone rates up to
7.50% in commercial AI generators; this codebase's 3.2% is lower — consistent with
its refactoring discipline and prior dedup campaigns — but non-trivial and real.

### Convict: genuine re-implemented capability

The clusters include textbook `reinvented-capability` — the same capability
re-derived across *unrelated* modules, where a shared helper was warranted:

- **"is this dependency installed?"** — `_check_matplotlib_available`,
  `_check_networkx`, `_check_pptx_available`, `is_available`: four files each
  re-implementing `try: import X; return True; except: return False`. The poster
  child — one helper, re-derived four times.
- **`diff_against_baseline` × 5** across the five `api_surface/` modules — the same
  diff routine copied per baseline instead of parameterised once.
- **`_init_db` / `init_db` × 4** across `token_store`, `otp_store`,
  `recovery_codes` — the same store-init pattern re-typed per store.

### Acquit: parallel-by-design families

The same detector also clusters functions whose duplication is a *judgment call*,
not a defect:

- CLI sub-commands (`pulse_run`, `pulse_radar`, `pulse_timeline`) — thin parallel
  dispatchers; a family, by design.
- Route handlers (`serve_terms_page`, `serve_privacy_page`) — parallel by intent.

These are exactly the cases the [`reinvented-capability`](../counter-priors/reinvented-capability.md)
acquittal anticipates: structural similarity is not invariant-equivalence. Whether a
cluster of parallel handlers *should* be one parameterised function is a real design
question — sometimes yes, often no.

### The pattern, again

A crude structural-clone count *flags*; a principled distinction — "is this one
capability re-derived, or parallel instances of a family?" — *acquits* a portion.
This is the fourth time this programme has landed on the same shape (premature
abstraction, tautological tests, rising-`noqa`, and now clone-rate). A reuse check
that reported raw clone hits would cry wolf on every CLI command; the value is in the
screen plus the discriminating question, not the screen alone.

## Feasibility of the pre-write check

Affirmative, with the caveat above. The signal is real (the availability-check
cluster is a clean catch a cheap index would have surfaced *before* the fourth copy
was written), the engine is ~70 lines of stdlib `ast`, and the false positives are a
bounded, characterisable class (parallel families) that the convict/acquit prompt
handles. A practical B(ii) check is: at the moment an agent is about to emit a
function, compute its signature, query the index, and if it collides with existing
functions, surface them and ask the discriminating question. **This has since been
shipped** as the `reinvented-capability` counter-prior's filter layer — `dazzle
fitness clones` plus a ratchet gate (`tests/unit/test_clone_ratchet.py`) that fails
the build on a *new* duplicated cluster while grandfathering the parallel-by-design
families as accepted residue. Note this is
*structural*, so it catches re-derivation even when the agent picked different
names — precisely the bounded-context failure mode.

## Limitations

- **Type-2 only.** Exact structural signatures miss Type-3 (modified) clones, so
  3.2% is a **lower bound**; near-duplicates with small edits are invisible here.
  MinHash/LSH would extend to Type-3 at more cost.
- **Already-consolidated duplication doesn't appear.** The project's prior dedup
  campaigns removed cases like the "~20 inline copies" of one helper; this measures
  the *residual* not-yet-caught debt, not the historical total.
- **Structural identity ≠ semantic identity.** The signature keeps method names but
  blanks locals/literals; two functions with the same skeleton can do genuinely
  different things (a source of the parallel-family false positives).
- **One codebase, one substrate.** A within-project measurement, not a claim about
  agentic coding at large.

## Conclusion

Automating the `reinvented-capability` search is cheap and works: a trivial Type-2
clone detector surfaces genuine re-implemented capability in this codebase's own
agent-generated code (3.2% of functions in clone clusters, with clean catches like
four copies of one availability check), and the same index queried pre-write is a
viable B(ii) reuse guard. The catch is the recurring one: it is a *screen* that must
be paired with the convict/acquit distinction between re-derived capability and
parallel-by-design families — without that, it over-reports. Cheap detection of the
duplication prior is feasible; cheap *judgement* about it is not — which is exactly
why the counter-prior is a reflection prompt, not a lint rule.

## Reproduce

```bash
python docs/research/scripts/clone_detect.py
```

Self-contained (stdlib `ast` only); derives the repo root from its own location.
