# DAZZLE LLM Instrumentation Specification  
## (LLM-Facing Implementation Brief for Expert Python Developer)

This document provides explicit, imperative instructions for implementing LLM‑aware project scaffolding inside `dazzle init`.  
Your task is to generate files and directory structures that make a DAZZLE-generated repository maximally understandable to frontier models such as Claude, ChatGPT, and Copilot.  
Follow these instructions exactly when implementing DAZZLE’s LLM instrumentation subsystem.

---

# 1. Add LLM Instrumentation to `dazzle init`

Modify the `dazzle init` command so that every newly created project includes:

```
LLM_CONTEXT.md
.llm/
  DAZZLE_PRIMER.md
.claude/
  PROJECT_CONTEXT.md
  permissions.json
.copilot/
  CONTEXT.md
```

Unless the user explicitly opts out using `--no-llm`, these files must be created automatically.

All files must be populated with the templates defined in this specification.

---

# 2. Create Root File: `LLM_CONTEXT.md`

Implement generation of a root-level file named `LLM_CONTEXT.md`.  
This file must introduce the project to any LLM and describe:

1. What DAZZLE is and how it drives all generated code.
2. The location of truth sources (`dsl/*.dsl` and `dazzle.toml`).
3. The workflow:
   - `dazzle validate`
   - `dazzle build`
   - `docker compose up`
   - `pytest`
4. Rules for modifying behavior:
   - Modify DSL first, then regenerate code.
5. Rules for what not to do:
   - Do not hand-edit generated files unless explicitly allowed.
   - Do not embed infra configuration into the DSL.

This file must be written as a universal model-friendly introduction.

---

# 3. Create `.llm/DAZZLE_PRIMER.md`

Implement a provider-neutral document containing deeper DAZZLE-specific information.

It must include:

1. Summary of DAZZLE concepts:
   - DSL
   - AppSpec IR
   - Backends
   - Stacks
   - Project manifests

2. Editing rules:
   - Prefer editing DSL and `dazzle.toml`.
   - Avoid duplicating logic in generated code.
   - Regenerate artefacts after DSL changes.

3. Clarify file types and their roles:
   - `*.dsl` = DSL
   - `dazzle.toml` = manifest + stack
   - `backend/**`, `frontend/**` = generated
   - `infra/**` = generated infra templates

This file must serve as a reusable universal DAZZLE reference for any LLM.

---

# 4. Implement `.claude/` Integration

Create two files inside `.claude/`:

### 4.1 `PROJECT_CONTEXT.md`
Content must include:

1. Overview of project structure.
2. Explanation of how DAZZLE is used.
3. Instructions to Claude:
   - Suggest DSL edits when user requests behavior changes.
   - Keep code aligned with DSL-defined entities and experiences.
   - Avoid destructive operations.
4. Recommendations for safe interactions:
   - When unclear, inspect DSL first.
   - When generating new code, follow DAZZLE conventions.

### 4.2 `permissions.json`
Implement a sane default JSON with:

- Safe commands allowed:
  - `Bash(git:*)`
  - `Bash(ls:*)`
  - `Bash(cat:*)`
  - `Bash(python3:*)`
  - `Bash(pip:*)`
  - `Bash(dazzle:*)`
  - `Bash(docker:*)`
- Dangerous commands denied:
  - `Bash(rm -rf /*:*)`
  - `Bash(terraform destroy:*)`
- Commands requiring explicit user approval:
  - `Bash(terraform apply:*)`
  - `Bash(docker system prune:*)`

Implement this JSON exactly as written unless overridden by user settings.

---

# 5. Implement `.copilot/CONTEXT.md`

Because GitHub Copilot does not support a strict configuration format, create a plain Markdown file summarizing how Copilot should behave.

The file must include:

1. Instructions for how to propose edits:
   - Prefer modifying the DSL (`dsl/*.dsl`) when requirements change.
   - Suggest regenerated code rather than manual edits when possible.

2. Guidance for interactions:
   - Explain that this repo is DAZZLE-generated.
   - Note that business logic is defined in DSL, not inside framework code.

3. Patterns Copilot should follow when producing code:
   - Align API shapes with DSL entities.
   - Follow existing generated conventions.

This file must be concise, readable, and directive.

---

# 6. Integrate Into Project Scaffolding

When `dazzle init` executes:

1. Generate the DAZZLE base project structure.
2. Create all LLM-related directories and files.
3. Populate files with templates defined in this spec.
4. Add a small section to the generated project `README.md`:

```
## LLM Usage

This project includes LLM context files:

- LLM_CONTEXT.md
- .llm/DAZZLE_PRIMER.md
- .claude/
- .copilot/

Provide `LLM_CONTEXT.md` to your AI assistant before requesting help.
```

---

# 7. Key Principles

Follow these principles when writing all files:

1. **Keep everything frontier-model-friendly**:
   - Use compact, declarative prose.
   - Avoid unnecessary verbosity.
   - Maintain deterministic structure.

2. **Do not introduce LLM-specific grammar into the DSL**.

3. **LLM files must not interfere with generated code**.

4. **DAZZLE remains the system of truth**:
   - DSL → IR → backends → artefacts.

5. **LLM files must help models understand the repo’s architecture quickly**.

---

# End of Specification
