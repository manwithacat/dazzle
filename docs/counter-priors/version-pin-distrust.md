---
id: version_pin_distrust
name: Version pin / banner distrust
layer: inference
status: active
summary: >-
  Trusting CLI banner version alone for dazzle.toml framework_version pins, or
  inventing pins from partial package metadata. Use installed package version
  (dazzle version / status.mcp version_cognition), project pin, and compatibility
  together. Init now stamps ~{{framework_minor}} from installed package (#1629 G7).
triggers_text:
  - "framework_version"
  - "install ~0."
  - "version mismatch"
  - "banner"
  - "0.106"
  - "0.38"
  - "pip install dazzle"
triggers_code:
  - "framework_version\\s*="
  - "~0\\.38"
  - "dazzle-dsl"
refs:
  adrs: []
  memories: []
  pr_review_agents: []
  kb_patterns: ["first_principles_demo", "version_cognition"]
  tests: []
detectors: []
---

# Version pin / banner distrust

## The corpus prior

Agents read the **CLI banner** or a single importlib string and write
`framework_version = "~0.38"` (stale template) or refuse to serve because two
version strings disagree. Training data treats “printed version” as SSOT.

## Wrong shape

```toml
# from stale init template or banner folklore
framework_version = "~0.38"
```

```text
banner says 0.106.0, package metadata 0.104.x → agent invents “install ~0.106”
while pin and installed may already match under tilde rules
```

## Right shape

1. After `dazzle init`, pin is `~{{major.minor}}` from **installed** package.
2. For decisions: use `status(operation=mcp)` → `version_cognition` (installed,
   project_pin, compatible) or `dazzle version` / doctor — not banner alone.
3. If serve rejects pin: fix `framework_version` in dazzle.toml to match
   installed minor, or install the requested range deliberately.
4. Do not invent pins from partial greps of monorepo tags.

## Why this matters here

#1629 G7: agent cannot trust version statements for pin decisions. Cognition
needs a **triple** (installed / pin / compatible), not a single string.
