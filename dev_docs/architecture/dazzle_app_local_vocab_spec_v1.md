# Dazzle App-Local Vocabulary and Extension Packs – LLM Agent Specification (v1)

You are an expert developer agent working inside the Dazzle ecosystem. Your job is to:
- Generate application scaffolds from Dazzle DSL specs.
- Allow each generated app to define and evolve its own local vocabulary (macros / aliases / patterns).
- Ensure that all local vocabulary always compiles back down to the stable, core Dazzle DSL.
- Emit metadata so that Dazzle can later mine app-local vocabularies and propose reusable “extension packs”.

Follow these imperatives precisely.

---

## 1. Core Concepts You MUST Respect

1. **Core DSL as the ground truth**
   - Treat the *core Dazzle DSL* as the only canonical language that the compiler understands.
   - Never mutate, extend, or fork the core DSL schema within an individual app.
   - Assume that any app-specific convenience syntax MUST be expandable into a combination of existing core DSL constructs.

2. **App-local vocabulary**
   - For each app, support a layer of **local vocabulary**: named macros, aliases, or patterns that exist only inside that app.
   - Implement app-local vocabulary as a thin syntactic layer on top of the core DSL.
   - Ensure that app-local vocabularies are:
     - **Purely additive** (no breaking changes to the core).
     - **Deterministically expandable** back to core DSL.
     - **Serializable** to a simple, tool-readable format (e.g. YAML/JSON plus core-DSL fragments).

3. **Extension packs**
   - Treat an **extension pack** as a reusable, versioned bundle of vocabulary definitions and supporting assets.
   - Ensure any extension pack can be installed into an app without modifying the core DSL.
   - Make extension packs composable and namespaced to avoid collisions.

---

## 2. File and Project Layout Requirements

When you generate or update an app, you MUST:

1. **Create a dedicated directory for local vocabulary**
   - Path (recommended): `dazzle/local_vocab/`
   - Inside this directory:
     - `core_map/` for machine-readable expansion rules.
     - `packs/` for imported or candidate extension packs.
     - `usage_logs/` for frequency/telemetry data (if enabled).

2. **Define a canonical vocabulary manifest**
   - Create `dazzle/local_vocab/manifest.yml` with, at minimum:
     - `version`: semantic version for the local vocabulary.
     - `app_id`: unique identifier for the app (provided or inferred).
     - `dsl_core_version`: the version of the core Dazzle DSL you are targeting.
     - `entries`: list of vocabulary entries (see section 3).
   - Always keep this file valid YAML and easy to diff.

3. **Store expansion rules in a core-mappable format**
   - For each vocabulary entry, persist:
     - A stable identifier (slug).
     - Human-readable name and description.
     - The core DSL expansion (canonical form).
   - Use structured fields that allow another tool to:
     - Parse entries.
     - Expand them to core DSL.
     - Compare and cluster similar entries across apps.

---

## 3. Vocabulary Entry Schema

For each app-local vocabulary entry, you MUST emit a structure equivalent to:

```yaml
- id: "user_profile_summary_panel"
  kind: "macro"            # e.g. macro | alias | pattern
  scope: "ui"              # e.g. ui | data | workflow | auth | misc
  dsl_core_version: "1.0.0"
  description: "Reusable panel layout for displaying a user profile with avatar, name, and key stats."
  parameters:
    - name: "source_entity"
      type: "model_ref"
      required: true
    - name: "include_actions"
      type: "boolean"
      required: false
      default: true
  expansion:
    language: "dazzle-core-dsl"
    body: |
      # core DSL fragment here that the compiler already understands
      # ... (no app-local syntax allowed inside this body)
  metadata:
    stability: "experimental"   # experimental | stable | deprecated
    source: "agent"             # agent | human
    created_at: "ISO-8601"
    last_used_at: "ISO-8601"
    usage_count: 0
```

Implement the schema above or a close variant in whatever serialization format the project uses (YAML is preferred). Always ensure:

- `expansion.body` contains **only** valid core DSL.
- `parameters` are fully specified and can be substituted into `expansion.body`.
- `metadata` fields are present to support later mining and clustering.

---

## 4. Rules for Defining New Local Vocabulary

When generating or modifying app DSL code, follow these rules:

1. **Detect repeated patterns**
   - Continuously scan generated core DSL for repeated structures such as:
     - Identical or near-identical UI layouts.
     - Repeated entity + endpoint combinations.
     - Reused workflow fragments (e.g. “authenticate + fetch + render”).
   - Consider any pattern repeated >= 3 times in an app as a strong candidate for a vocabulary entry.

2. **Propose vocabulary entries automatically**
   - Whenever you detect a candidate pattern:
     - Extract the core DSL fragment.
     - Abstract variable parts into parameters.
     - Create a new prototype entry in `manifest.yml`.
   - Add a short description oriented to a human reader.
   - Flag the entry with `metadata.stability: "experimental"`.

3. **Respect namespacing and collision rules**
   - Use a clear naming convention such as:
     - `<domain>_<feature>_<kind>`
     - Examples: `billing_invoice_list_page`, `auth_password_reset_flow`.
   - Avoid using reserved or core DSL keywords as IDs.
   - If an ID already exists:
     - Either extend with a suffix (`_v2`, `_compact`) or refuse to create and log a warning in a `usage_logs` note.

4. **Always maintain reversibility**
   - For every local vocabulary use:
     - Ensure you can expand it to a pure core DSL fragment without losing information.
   - Never introduce app-local constructs that rely on hidden global state or side channels.

5. **Keep the core DSL clean**
   - When writing files that represent “final” app DSL to compile:
     - Option A: Emit DSL that already has local vocab expanded.
     - Option B: Emit DSL that still references local vocab, but also provide a compiled, core-only artifact (e.g. `dazzle/build/app_core_dsl.yml`).
   - Choose a strategy and implement it consistently per project.

---

## 5. Supporting Dazzle’s Extension Pack Mining

You MUST design all outputs so that an offline “Dazzle mining process” can safely aggregate app-local vocabulary across many apps.

1. **Emit machine-friendly metadata**
   - In each `manifest.yml`, include:
     - `tags`: list of short keywords (e.g. `["crud", "admin", "dashboard", "auth"]`).
     - `context`: optional hints like `["b2b_saas", "internal_tool"]`.
   - Use tags to describe *function*, not visual aesthetics.

2. **Log usage for ranking**
   - For each vocabulary entry use, increment `usage_count`.
   - Optionally write a short log entry under `dazzle/local_vocab/usage_logs/` with:
     - Entry ID.
     - File and location where it was used.
     - Timestamp.

3. **Mark candidates for promotion**
   - When you detect that a local vocabulary entry:
     - Has high `usage_count`, and/or
     - Closely matches other entries in semantics and expansion,
     - Then set `metadata.stability: "candidate_for_pack"` and add a `metadata.cluster_hint` with a short description (e.g. `"user_profile_components"`).
   - Do NOT attempt to create the extension pack yourself; only mark candidates and provide rich metadata.

4. **Keep everything deterministic**
   - Ensure that given the same app DSL and vocabulary manifests, the mining process would always see:
     - The same set of entries.
     - The same expansion fragments.
     - The same metadata fields.
   - Avoid non-deterministic naming or ordering.

---

## 6. Agent Behaviours and Safety Constraints

Follow these behavioural rules:

1. **Never mutate the core DSL**
   - Do not edit, version-bump, or extend the core DSL specification files.
   - If a feature genuinely cannot be expressed in the existing core DSL:
     - Emit a clear comment in a TODO file (e.g. `dazzle/TODO.md`) with:
       - A human-readable description.
       - A minimal core-DSL-ish sketch of what is missing.
     - Do NOT hack around it using app-local magic.

2. **Prefer fewer, well-factored entries**
   - Avoid creating hundreds of tiny vocabulary entries.
   - Prioritize:
     - High leverage patterns.
     - Semantically meaningful abstractions.
   - Merge or deprecate redundant entries by:
     - Marking old ones as `metadata.stability: "deprecated"`.
     - Introducing a newer, better-factored entry.

3. **Ensure human readability**
   - Write descriptions and IDs so that a human developer can understand purpose without reading the expansion body.
   - Avoid naming that exposes internal implementation details.

4. **Validate before writing**
   - Before finalizing any `manifest.yml` or extension definition file:
     - Syntactically validate the YAML/JSON if possible.
     - Expand each entry at least once to confirm that the core DSL body is valid and parameter-substitution works.

---

## 7. Example Workflow

When creating or updating an app, follow a workflow like this:

1. **Generate baseline core DSL**
   - From the high-level spec, first emit a pure core DSL version of the app (no app-local vocabulary yet).
2. **Scan for patterns**
   - Analyse the core DSL for repeated patterns.
3. **Create vocabulary entries**
   - Extract repeated patterns into parameterised entries and store them in `manifest.yml`.
   - Replace relevant occurrences in the app DSL with references to these entries (if the chosen strategy uses references).
4. **Persist and log**
   - Save `manifest.yml` and any `usage_logs`.
   - Ensure that a core-only compiled artifact exists.
5. **Iterate**
   - On subsequent edits or regenerations:
     - Reuse existing vocabulary entries whenever appropriate.
     - Update usage counts and metadata.
     - Mark strong candidates for promotion to extension packs.

---

## 8. Deliverables You MUST Produce

For each app you touch, you MUST ensure the repository contains at least:

1. `dazzle/local_vocab/manifest.yml`
   - Complete, validated, and referencing only core DSL in expansions.

2. `dazzle/local_vocab/usage_logs/…`
   - Optional but recommended; at minimum, track timestamps and counts in `manifest.yml`.

3. A core-only representation of the DSL
   - Example: `dazzle/build/app_core_dsl.yml`.
   - This file must be directly compilable by the core Dazzle toolchain.

4. A brief README section
   - In either `README.md` or `dazzle/LOCAL_VOCAB.md`, add:
     - One short paragraph explaining app-local vocabulary.
     - How a human developer can add, modify, or deprecate entries.
     - Where extension pack candidates are marked.

By following these imperatives, you allow each generated app to evolve a rich, local vocabulary while preserving a single, stable Dazzle core DSL and enabling Dazzle to mine those vocabularies into reusable extension packs over time.
