---
name: spec-narrate
description: Use when the user wants to generate a stakeholder-facing English specification document (SPECIFICATION.md) from a Dazzle DSL project — for investors, business leaders, founders, or non-technical decision-makers. Reverses the usual DSL→app flow into DSL→prose.
---

# spec-narrate — DSL → stakeholder specification

Turn a Dazzle project's DSL into `SPECIFICATION.md`: a single, layered,
non-technical document (executive summary → progressive depth) that explains
what the system does, who uses it, how work flows through it, and the technical
guarantees that hold *because it is built on Dazzle*.

## The hard rule

The brief is the **single source of truth**. Every sentence you write MUST trace
to a fact or an activated claim in the brief. **Invent nothing** — no metrics, no
roadmap, no capabilities, no market claims that aren't in the brief. If a section
has no supporting facts, omit it. An investor-facing document that overstates is
worse than one that is terse.

## Steps

1. Run the deterministic extractor:
   ```bash
   dazzle spec brief --project <dir> --format json
   ```
   (Default `<dir>` is `.`.) Parse the JSON. It contains:
   - `app_name` / `app_title`
   - `domain` — the things the system manages (each with `title`, `intent`,
     `lifecycle_states`). Framework plumbing is already excluded.
   - `actors` — personas (`id`, `label`, `description`)
   - `capabilities` — surfaces (`name`, `title`, `entity`, `mode`)
   - `security` — `has_row_level_security`, `scoped_entities`, `persona_count`
   - `activated_claims` — framework guarantees that fired, each with `group`,
     `audience`, `claim` text, and an `evidence` command
   - `skeleton` — which sections to write (`populated`) and which claim ids
     belong in each (`claim_ids`)

2. Write `SPECIFICATION.md` at the project root, following the skeleton's section
   order. Only write sections whose skeleton entry has `populated: true`.

   - **Executive summary** — 2–3 paragraphs: what the system is (from `app_title`
     + the domain), who it's for (from `actors`), and 1–2 standout guarantees
     (pick the highest-impact `investor`-audience activated claims).
   - **What it does** — narrate `domain` items in plain English using each item's
     `title`/`intent`. Group related entities. No database vocabulary (no
     "tables", "foreign keys", "columns").
   - **Who uses it** — narrate `actors` (label + description) and, drawing on
     `capabilities`, what each can accomplish.
   - **How work flows through it** — narrate entities that have `lifecycle_states`
     as journeys ("a Task moves from todo → in progress → review → done"), plus
     approvals.
   - **The technical foundation** — for each claim id in the skeleton's
     `technical_foundation.claim_ids`, write the matching `claim` text in your own
     flowing prose, grouped by `group` (Security, Data & reliability,
     Architecture). After each guarantee, note that it can be independently
     verified (cite the claim's `evidence` command). This verifiability is a
     selling point — lean into it.
   - **Compliance posture** — only if populated; narrate the compliance-group
     claim(s).

3. Self-check before finishing: re-read each paragraph. Does any sentence assert
   something not present in the brief? Delete it. Does any claim text appear that
   wasn't in `activated_claims`? Delete it.

4. Tell the user where the document is and which claims activated (so they can
   see which guarantees their app currently earns).

## Tone

Confident but substantiated. Every architectural assertion is backed by an
`evidence` command — write like someone who can prove what they say. Avoid hype
adjectives ("revolutionary", "cutting-edge"); let the guarantees speak.

## Notes

- This is Stage 2 of a two-stage pipeline; Stage 1 (`dazzle spec brief`) is
  deterministic and tested. You are the language layer.
- To add or reword a framework guarantee, edit
  `src/dazzle/spec_narrative/claims.toml` (not this skill).
