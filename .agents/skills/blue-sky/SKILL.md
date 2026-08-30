---
name: blue-sky
description: >
  Framework Blue Sky — extract a Dazzle-agnostic scene spec from an example
  app's DSL, have an isolated agent prototype the same job in another stack,
  then critique for framework gaps. Use for /blue-sky, "blue sky", orthogonal
  prototype from DSL, break out of list/detail attractors, example-app enquiry.
---

# Blue Sky — orthogonal prototype from example DSL

`/improve` and `/qa-trial` evaluate the **rendered Dazzle product**. They cannot
ask whether the job should be a list at all. Blue Sky inverts that: independent
implementation of the **job**, then contrast. The load-bearing invention is the
**firewall** — if the spec or the builder sees Dazzle ontology, you get a second
CRUD admin and learn nothing.

The product that ships stays Dazzle. This loop does not port React into the
framework. It produces **lines of enquiry** (and, when they survive translation,
stems / GitHub issues).

## 0. Pick example + slice

```bash
.venv/bin/python scripts/blue_sky_spec.py --list-examples
.venv/bin/python scripts/blue_sky_spec.py --example invoice_ops --list-slices
```

Default example if the user did not name one: `invoice_ops` (keystone).
Default slice: the first unused persona slice (no `blue_sky/runs/*-<example>-<slice>/`).
One slice per builder. Do not prototype the whole example.

## 1. EXTRACT (this repo)

```bash
.venv/bin/python scripts/blue_sky_spec.py --example <app> --slice <id> --write
```

Writes:

- `blue_sky/specs/<example>/<id>.md` — domain brief (no framework words)
- `blue_sky/specs/<example>/<id>.implementer.md` — walls for the builder

Skim the spec. Grep for `entity`, `surface`, `workspace`, `region`,
`executed_by`, `dazzle`, `hx-`, `tenant_host`. Any hit is an extractor bug —
fix the script, do not hand-edit around it.

## 2. BUILD (independent agent)

Create `blue_sky/runs/YYYY-MM-DD-<example>-<slice>/` with **only** the two spec
files copied in. Spawn a general-purpose subagent:

- `cwd` = that run directory (absolute). Do **not** use `isolation=worktree`
  (a Dazzle worktree is full of DSL).
- Prompt is self-contained: paste both files. They have never heard of Dazzle.
- Forbid reading anything above cwd. Stack is their choice. Fake auth, in-memory
  seed. Cap: six screens. Must be demoable this session.
- Stop when `README.md`, `ASSUMPTIONS.md`, `JOURNEYS.md`, and a run command exist.

A builder that produces an entity admin is a **failed run**. Record and stop.
Do not harvest CRUD as insight.

## 3. READ (this repo, different hat)

Walk the prototype as a stranger. Then walk the **same jobs** on the example
(`dazzle serve` in `examples/<app>` if a live app is available; otherwise the
DSL + generated UI as it actually is). Write `CRITIQUE.md` in the run directory.

| Lens | Question |
|------|----------|
| Styling | What visual language did they spend care on that Dazzle treats as chrome? |
| Affordances | What control, preview, undo, or progress did they invent that the example lacks? |
| Elegance | Where is their IA simpler (one object, fewer lists)? |
| Domain | What did `ASSUMPTIONS.md` invent that the example DSL never modelled? |
| Framework | What did they need that Dazzle cannot *say* (missing primitive, not missing CSS)? |

Each finding is one of:

| Tag | Meaning |
|-----|---------|
| **steal** | Pattern should exist in the *example* as DSL/workspace/copy — not cloned React |
| **translate** | Needs a Dazzle primitive, stem, or issue; do not private-CSS it in the example |
| **discard** | Pretty because the prototype is fake, or wrong for the domain |
| **theory** | Update example `stems/` or domain theory — a judgement, not a widget |

Do not score pixel parity.

## 4. PROMOTE

For each **steal** / **translate** / **theory** row:

- steal → example change (or `agent/` backlog if the example is a consumer)
- translate → read `stems/` first, then a Dazzle issue or stem amendment
- theory → `examples/<app>/stems/`

Cite the run path and lens. Log the round in `blue_sky/LOG.md`.

## 5. What not to do

- Rebuild the example's generated list/detail as "the prototype".
- Port the prototype stack into Dazzle or an example.
- File a framework issue from taste without a stem.
- Run Blue Sky as an improve ticker.
