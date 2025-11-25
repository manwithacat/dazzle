# DAZZLE VS Code Integration Specification
## (LLM-Facing Implementation Brief)

This document gives explicit, imperative instructions for an LLM operating as an expert TypeScript/Python developer.
Your task is to implement a DAZZLE-aware VS Code extension that provides syntax highlighting, linting, CLI integration, and optional LSP features, while delegating all actual logic to DAZZLE Core in Python.

Follow these instructions exactly.

---

# 1. Define Language Surface in VS Code

1. Register a new language:
   - `id`: `dazzle-dsl`
   - aliases: `DAZZLE`, `Dazzle DSL`
   - extensions: `[".dsl", ".dazzle"]`
   - configuration file: `./language-configuration.json`

2. Add contributions to `package.json`:

```json
{
  "contributes": {
    "languages": [
      {
        "id": "dazzle-dsl",
        "aliases": ["DAZZLE", "Dazzle DSL"],
        "extensions": [".dsl", ".dazzle"],
        "configuration": "./language-configuration.json"
      }
    ],
    "grammars": [
      {
        "language": "dazzle-dsl",
        "scopeName": "source.dazzle",
        "path": "./syntaxes/dazzle.tmLanguage.json"
      }
    ]
  }
}
```

3. Add configuration options that allow users to define:
   - `dazzle.cliPath` (default `"dazzle"`)
   - `dazzle.manifest` (default `"dazzle.toml"`)

---

# 2. Implement Syntax Highlighting (v0.1)

1. Create `syntaxes/dazzle.tmLanguage.json` using a minimal TextMate grammar.

2. Include patterns for:
   - Keywords (module, use, app, entity, surface, experience, service, integration, section, action, step, uses, constraint, key, mode)
   - Strings (`"..."`)
   - Comments (`# ...`)
   - Identifiers

3. Follow this structure:

```json
{
  "scopeName": "source.dazzle",
  "patterns": [
    { "include": "#keywords" },
    { "include": "#strings" },
    { "include": "#comments" }
  ],
  "repository": {
    "keywords": {
      "patterns": [
        {
          "name": "keyword.control.dazzle",
          "match": "\b(app|module|use|entity|surface|experience|service|foreign_model|integration|section|action|step|sync|uses|constraint|key|mode|from|when|call|map|with|as|on|submitted|owner|spec|auth_profile)\b"
        }
      ]
    },
    "strings": {
      "patterns": [
        { "name": "string.quoted.double.dazzle", "match": ""([^"\\]|\\.)*"" }
      ]
    },
    "comments": {
      "patterns": [
        { "name": "comment.line.number-sign.dazzle", "match": "#.*$" }
      ]
    }
  }
}
```

---

# 3. Expose DAZZLE CLI Commands to Users

Create VS Code tasks (in extension or documented defaults):

- `dazzle: validate` → runs `dazzle validate`
- `dazzle: build` → runs `dazzle build`

Example task:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "dazzle: validate",
      "type": "shell",
      "command": "dazzle validate",
      "problemMatcher": "$dazzle"
    }
  ]
}
```

---

# 4. Implement Linting Integration (v0.2)

1. Modify DAZZLE CLI to output errors in this format:

```
file.dsl:12:5: error: Unknown entity 'TicketStatus'
file.dsl:24:3: warning: Unused surface 'ticket_debug'
```

2. Define a problem matcher in `package.json`:

```json
"contributes": {
  "problemMatchers": [
    {
      "name": "dazzle",
      "owner": "dazzle",
      "fileLocation": ["relative", "${workspaceFolder}"],
      "pattern": {
        "regexp": "^(.*):(\d+):(\d+):\s+(error|warning):\s+(.*)$",
        "file": 1,
        "line": 2,
        "column": 3,
        "severity": 4,
        "message": 5
      }
    }
  ]
}
```

3. In the extension’s TypeScript:
   - Watch `*.dsl` and `dazzle.toml` files.
   - On save, execute: `dazzle validate --file <path>`.
   - Parse output via the problem matcher.
   - Display problems in the Problems panel.

Avoid re-implementing any DAZZLE parsing/linting logic in TypeScript.

---

# 5. Implement Optional LSP Features (v0.3)

Create a lightweight LSP server in Python using `pygls`:

1. Implement LSP entrypoint:
   `python -m dazzle.lsp`

2. Provide LSP features using the DAZZLE IR:
   - Go-to-definition (entities, surfaces, experiences, modules)
   - Hover (show field lists, relationships)
   - Completion (entity names, surface names, service names)
   - Diagnostics (fallback for CLI-based checks)

3. In VS Code extension:
   - Spawn the Python LSP server on activation.
   - Connect using `vscode-languageclient`.

Ensure LSP features query DAZZLE’s Python IR, not re-parse DSL in TypeScript.

---

# 6. Recommended Workspace Bootstrapping

When DAZZLE initializes a new project (`dazzle init`), generate:

```
.vscode/
  settings.json
  tasks.json
```

`settings.json` example:

```json
{
  "files.associations": {
    "*.dsl": "dazzle-dsl"
  },
  "dazzle.cliPath": "python -m dazzle.cli"
}
```

`tasks.json` example:

```json
{
  "version": "2.0.0",
  "tasks": [
    { "label": "dazzle: validate", "type": "shell", "command": "dazzle validate" }
  ]
}
```

Do not include any hard-coded framework assumptions.

---

# 7. Key Principles You Must Follow

1. **Do not reimplement DAZZLE logic in TypeScript.**
   All parsing, linting, module-resolution, and IR generation must be done by the Python core.

2. **Extension provides UI/UX only**:
   - Syntax colouring
   - CLI integration
   - Problem display
   - Optional LSP for navigation and completion

3. **Always delegate to the DAZZLE CLI or DAZZLE LSP**.

4. **Keep the extension lightweight, conventional, and maintainable.**

---

# 8. Deliverables You Must Produce

When implementing DAZZLE’s VS Code integration:

- Generate a full VS Code extension scaffold:
  - `package.json`
  - `extension.ts`
  - `syntaxes/dazzle.tmLanguage.json`
  - `language-configuration.json`
  - Activation events
  - Commands (`dazzle.validate`, etc.)

- Implement LSP wrapper (optional but recommended):
  - `dazzle/lsp/server.py`

- Integrate CLI commands and diagnostics pipeline.

- Produce a sample project `.vscode/` folder for demonstration.

---

# End of Specification
