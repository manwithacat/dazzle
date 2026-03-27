"""Haiku-based DSL generator for fuzzing.

Uses Claude Haiku to generate plausible-but-wrong DSL. Haiku's tendency
to pattern-match without full structural understanding produces exactly
the near-miss error distribution we want to test against.
"""

from __future__ import annotations

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

GRAMMAR_SUMMARY = """DAZZLE DSL Grammar Summary:

Top-level constructs (each starts at column 0, followed by identifier and optional "Label"):
  entity Name "Label":     — data model with typed fields
  surface Name "Label":    — UI screen (sections with fields, actions)
  workspace Name "Label":  — dashboard grouping surfaces into regions
  experience Name "Label": — multi-step wizard/flow
  process Name "Label":    — background workflow with steps
  story Name "Label":      — user story with scenes
  rhythm Name "Label":     — recurring scheduled operation
  persona Name "Label":    — user role definition
  integration Name "Label": — external API connection
  service Name "Label":    — internal/external service
  ledger Name "Label":     — financial/audit ledger
  enum Name "Label":       — enumeration type
  approval Name "Label":   — approval workflow
  sla Name "Label":        — service level agreement
  webhook Name "Label":    — incoming webhook handler

Entity fields (indented 2 spaces):
  field_name: type modifiers
  Types: str(N), text, int, decimal, bool, date, datetime, uuid, email, json, money, file, url
  Modifiers: required, unique, pk, indexed
  Relationships: ref EntityName, has_many EntityName, has_one EntityName, belongs_to EntityName
  Default values: field_name: type = default_value
  State machines: state_machine Name: / state active / transition activate: idle -> active

Surface sections (indented 2 spaces):
  uses entity EntityName
  mode: list | detail | form | kanban
  section name:
    field field_name "Label"
    action action_name "Label"
  permit:
    read: role_name
    write: role_name
  scope:
    read: field = current_user.field
      for: persona_name

Workspace regions:
  region name "Label":
    surface SurfaceName
  access: persona(persona_name)

Process steps:
  trigger: event_name on EntityName
  step name "Label":
    action: do_something
  sla: 2h

Important syntax rules:
- Indentation is 2 spaces (not tabs)
- Strings use double quotes
- Blocks end with colon
- Surface fields do NOT have types — those belong on entities
- filter: in surfaces must be inside a ux: block
- Access control uses access: persona(name), not allow_personas: [name]
"""

PROMPT_VARIATIONS: list[str] = [
    "entity-heavy",
    "surface-heavy",
    "process-heavy",
    "rbac-heavy",
    "integration-heavy",
    "kitchen-sink",
]

_VARIATION_DESCRIPTIONS: dict[str, str] = {
    "entity-heavy": "Define a CRM system with 5 entities including relationships, state machines, and computed fields",
    "surface-heavy": "Build admin dashboards with filters, multi-section layouts, actions, and persona-based access",
    "process-heavy": "Model a multi-step approval workflow with branching, SLA tracking, and error compensation",
    "rbac-heavy": "Define 4 personas with scoped access to shared entities using permit and scope blocks",
    "integration-heavy": "Connect to 3 external APIs with webhooks, sync schedules, and field mappings",
    "kitchen-sink": "Build a complete project management app with tasks, teams, sprints, and reporting",
}


def build_generation_prompt(seed_dsl: str, variation: str) -> str:
    """Build a prompt for Haiku to generate DSL."""
    description = _VARIATION_DESCRIPTIONS.get(variation, _VARIATION_DESCRIPTIONS["kitchen-sink"])
    return f"""{GRAMMAR_SUMMARY}

Here is an example of valid DAZZLE DSL:

```dsl
{seed_dsl}
```

Write DAZZLE DSL for the following requirement. Output ONLY the DSL code, no explanations:

{description}
"""


def generate_samples(
    seed_dsl: str,
    count: int,
    model: str = "claude-haiku-4-5-20251001",
) -> list[str]:
    """Generate DSL samples using Haiku."""
    if anthropic is None:
        raise ImportError(
            "anthropic package required for LLM generation. "
            "Install with: pip install dazzle-dsl[llm]"
        )

    client = anthropic.Anthropic()
    samples: list[str] = []

    for i in range(count):
        variation = PROMPT_VARIATIONS[i % len(PROMPT_VARIATIONS)]
        prompt = build_generation_prompt(seed_dsl=seed_dsl, variation=variation)

        response = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from the response's TextBlock
        content_block = response.content[0]
        if hasattr(content_block, "text"):
            text = content_block.text
        else:
            raise ValueError("Expected TextBlock in response")
        # Strip markdown fences if Haiku wraps output
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            text = "\n".join(lines)
        samples.append(text.strip())

    return samples
