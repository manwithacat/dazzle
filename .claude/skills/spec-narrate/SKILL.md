---
name: spec-narrate
description: Use when the user wants to generate a stakeholder-facing English specification document (SPECIFICATION.md) from a Dazzle DSL project — for investors, business leaders, founders, or non-technical decision-makers. Reverses the usual DSL→app flow into DSL→prose.
---

# spec-narrate — DSL → stakeholder specification

Turn a Dazzle project's DSL into `SPECIFICATION.md`: a single, layered,
non-technical document (executive summary → progressive depth) that explains
what the system does, who uses it, where and how work happens, what runs by
itself, and the technical guarantees that hold *because it is built on Dazzle*.

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
     `lifecycle_states`, and `relationships` — typed links to other domain items,
     each with `field`, `target`, `target_title`, `required`). Framework plumbing
     is already excluded.
   - `actors` — personas (`id`, `label`, `description`, `goals`, `workspaces` —
     the places each is explicitly granted)
   - `capabilities` — surfaces (`name`, `title`, `entity`, `mode`)
   - `journeys` — the authored user stories (`id`, `title`, `actor`,
     `description`, `when`, `outcomes`). These are the app author's own
     narratives — the richest material in the brief.
   - `places` — workspaces and experiences (`kind`, `title`, `purpose`,
     `personas`, `contents` — e.g. "kanban of IssueReport" or wizard step names)
   - `automation` — processes, schedules, approvals, SLAs, AI-assisted steps,
     integrations, ledgers, transactions (`kind`, `title`, `description`, `detail`)
   - `security` — `has_row_level_security`, `scoped_entities`, `persona_count`,
     and `scope_rules`: every row-visibility rule already rendered in plain
     English (`entity`, `operation`, `personas`, `rule`)
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
     `title`/`intent`, and weave `relationships` into the prose ("every Issue
     Report is tied to the Device it was observed on and the Tester who filed
     it"). Group related entities. No database vocabulary — never "tables",
     "foreign keys", "columns", "uuid".
   - **Who uses it** — one short passage per actor: `label`, `description`,
     their `goals` in flowing prose (these are the persona's own stated aims),
     and where they work (`workspaces`). Where `security.scope_rules` names the
     persona, say what they can see in plain terms — the `rule` text is already
     stakeholder-safe ("a tester sees only devices where its assigned tester is
     the signed-in user").
   - **Where work happens** — narrate `places`: each workspace's `purpose`, who
     it serves (`personas`), and what it shows (`contents`, translated: "a kanban
     board of issue reports, a timeline of test sessions"). Experiences are
     guided step-by-step flows — name their steps.
   - **How work flows through it** — two threads, woven:
     1. lifecycles: entities with `lifecycle_states` as journeys ("a Task moves
        from todo → in progress → review → done"), plus approvals;
     2. `journeys`: pick 3–6 REPRESENTATIVE stories — favour ones that span the
        lifecycle above, cover different actors, and have `outcomes`. Render each
        as one flowing sentence ("When an engineer creates a device, it is saved
        and confirmed on screen"), not as given/when/then scaffolding. With many
        journeys, summarise the coverage ("26 authored scenarios pin these flows
        down") rather than listing all.
   - **Automation & controls** — only if populated. Two groups, prose not lists
     where the counts are small: what runs without a human (processes, schedules,
     AI-assisted steps — use each item's `description`/`detail`), and the
     declared constraints (approvals with their quorum/role detail, SLAs,
     double-entry ledgers/transactions for money).
   - **The technical foundation** — for each claim id in the skeleton's
     `technical_foundation.claim_ids`, write the matching `claim` text in your own
     flowing prose, grouped by `group` (Security, Data & reliability,
     Architecture). After each guarantee, note that it can be independently
     verified (cite the claim's `evidence` command). This verifiability is a
     selling point — lean into it.
   - **Compliance posture** — only if populated; narrate the compliance-group
     claim(s).

3. Append the freshness footer (the drift gate depends on it) as the LAST line:
   ```bash
   dazzle spec brief --project <dir> --fingerprint
   ```
   ```markdown
   <!-- dazzle-spec-brief: sha256:… -->
   ```
   The example-spec gate recomputes this from the live DSL; a stale footer fails
   CI with "re-run /spec-narrate".

4. Self-check before finishing: re-read each paragraph. Does any sentence assert
   something not present in the brief? Delete it. Does any claim text appear that
   wasn't in `activated_claims`? Delete it. Any journey named that isn't in
   `journeys`? Delete it.

5. Tell the user where the document is and which claims activated (so they can
   see which guarantees their app currently earns).

## Length scaling

Scale depth to the brief, not to a template: a 3-entity app deserves ~1 page; a
6-entity app with 20+ journeys, workspaces, and ledgers deserves 2–3. The
skeleton's `populated` flags do the structural scaling — within sections, more
facts earn more prose, but never pad.

## Tone

Confident but substantiated. Every architectural assertion is backed by an
`evidence` command — write like someone who can prove what they say. Avoid hype
adjectives ("revolutionary", "cutting-edge"); let the guarantees speak.

## Notes

- This is Stage 2 of a two-stage pipeline; Stage 1 (`dazzle spec brief`) is
  deterministic and tested. You are the language layer.
- To add or reword a framework guarantee, edit
  `src/dazzle/spec_narrative/claims.toml` (not this skill).
- Committed example docs are gated by `tests/unit/test_example_spec_bar.py`
  (existence, fingerprint freshness, populated sections present, no DB
  vocabulary, no placeholder text).
