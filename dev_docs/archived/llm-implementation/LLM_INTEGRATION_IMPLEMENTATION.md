# LLM Integration Implementation Guide
## Two Approaches: API-Based & CLI Tool Handoff

---

## Overview

DAZZLE needs to support two modes of LLM-assisted spec analysis:

1. **API Mode**: Direct calls to LLM APIs (OpenAI, Anthropic, etc.)
2. **CLI Handoff Mode**: Delegate to local LLM tools (Claude Code, Aider, etc.)

---

## Approach 1: API-Based Integration

### Architecture

```
dazzle analyze-spec SPEC.md
        ↓
    [Read SPEC.md]
        ↓
    [Generate analysis prompt]
        ↓
    [Call LLM API]
        ↓
    [Parse JSON response]
        ↓
    [Present questions to user]
        ↓
    [Generate enhanced spec + DSL]
```

### Configuration

**File: `~/.dazzle/config.toml`**

```toml
[llm]
# API mode configuration
mode = "api"  # or "cli"

# API provider: "openai", "anthropic", "openrouter", "local"
provider = "anthropic"

# API credentials
api_key_env = "ANTHROPIC_API_KEY"  # Environment variable name
# api_key = "sk-..."  # Direct key (not recommended)

# Model selection
model = "claude-3-5-sonnet-20241022"  # or "gpt-4", etc.

# Request parameters
temperature = 0.0  # Deterministic for spec analysis
max_tokens = 16000

# Cost controls
max_cost_per_analysis = 1.00  # USD
warn_on_large_specs = true
size_threshold_kb = 100

# Caching (if provider supports it)
use_prompt_caching = true  # Anthropic prompt caching
cache_system_prompt = true
```

### Implementation

**File: `dazzle/llm/api_client.py`**

```python
import os
import json
from typing import Dict, Any, Optional
from anthropic import Anthropic
from openai import OpenAI

class LLMAPIClient:
    """API-based LLM client for spec analysis."""

    def __init__(self, config: Dict[str, Any]):
        self.provider = config.get("provider", "anthropic")
        self.model = config.get("model")
        self.temperature = config.get("temperature", 0.0)
        self.max_tokens = config.get("max_tokens", 16000)

        # Initialize provider client
        if self.provider == "anthropic":
            api_key = os.environ.get(config.get("api_key_env", "ANTHROPIC_API_KEY"))
            self.client = Anthropic(api_key=api_key)
        elif self.provider == "openai":
            api_key = os.environ.get(config.get("api_key_env", "OPENAI_API_KEY"))
            self.client = OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def analyze_spec(self, spec_content: str, spec_path: str) -> Dict[str, Any]:
        """
        Analyze a specification and return structured analysis.

        Returns:
            {
                "state_machines": [...],
                "crud_analysis": [...],
                "business_rules": [...],
                "clarifying_questions": [...]
            }
        """
        prompt = self._build_analysis_prompt(spec_content, spec_path)

        if self.provider == "anthropic":
            response = self._call_anthropic(prompt)
        elif self.provider == "openai":
            response = self._call_openai(prompt)

        # Parse JSON response
        try:
            analysis = json.loads(response)
            return analysis
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM returned invalid JSON: {e}\n{response}")

    def _build_analysis_prompt(self, spec_content: str, spec_path: str) -> str:
        """Build the analysis prompt with spec content."""
        system_prompt = """You are a specification analyzer for the DAZZLE DSL-based application generator.

Your task is to analyze a product specification and extract structured information needed for code generation.

You must return ONLY valid JSON with this exact structure:

{
  "state_machines": [
    {
      "entity": "EntityName",
      "field": "field_name",
      "states": ["state1", "state2"],
      "transitions_found": [
        {
          "from": "state1",
          "to": "state2",
          "trigger": "description",
          "location": "line reference",
          "side_effects": ["effect1"],
          "conditions": ["condition1"]
        }
      ],
      "transitions_implied_but_missing": [
        {
          "from": "state1",
          "to": "state2",
          "reason": "why this transition is needed",
          "question": "clarifying question for founder"
        }
      ]
    }
  ],
  "crud_analysis": [
    {
      "entity": "EntityName",
      "operations_mentioned": {
        "create": {"found": true, "location": "reference", "who": "role"},
        "read": {"found": true, "location": "reference"},
        "update": {"found": false, "question": "clarifying question"},
        "delete": {"found": true, "constraints": ["constraint1"]},
        "list": {"found": true, "filters_needed": ["filter1"]}
      },
      "missing_operations": ["update"]
    }
  ],
  "business_rules": [
    {
      "type": "validation|constraint|access_control",
      "entity": "EntityName",
      "field": "field_name",
      "rule": "description",
      "location": "reference"
    }
  ],
  "clarifying_questions": [
    {
      "category": "State Machine|CRUD|Access Control|...",
      "priority": "high|medium|low",
      "questions": [
        {
          "q": "The question",
          "context": "Why this matters",
          "options": ["Option A", "Option B"],
          "impacts": "What this affects"
        }
      ]
    }
  ]
}

Be thorough but concise. Focus on actionable information."""

        user_prompt = f"""Analyze this specification file: {spec_path}

<specification>
{spec_content}
</specification>

Return your analysis as JSON following the exact schema provided."""

        return {"system": system_prompt, "user": user_prompt}

    def _call_anthropic(self, prompt: Dict[str, str]) -> str:
        """Call Anthropic API."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=prompt["system"],
            messages=[
                {"role": "user", "content": prompt["user"]}
            ]
        )

        # Extract text from response
        return response.content[0].text

    def _call_openai(self, prompt: Dict[str, str]) -> str:
        """Call OpenAI API."""
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]}
            ],
            response_format={"type": "json_object"}  # Ensure JSON response
        )

        return response.choices[0].message.content

    def ask_followup(self, questions: list, context: str) -> Dict[str, str]:
        """
        Present clarifying questions to user via LLM.
        Can be interactive or batch.
        """
        # Implementation for interactive Q&A
        pass
```

### CLI Command

```bash
$ dazzle analyze-spec SPEC.md --mode api --provider anthropic

🔍 Analyzing specification via Anthropic API...
   Model: claude-3-5-sonnet-20241022
   Estimated cost: $0.15

[████████████████████████] 100% Complete

✓ Analysis complete (took 8.2s, cost $0.12)

Found:
  ✓ 1 state machine (Ticket.status)
  ✓ 7 transitions (4 explicit, 3 implied)
  ⚠ 3 CRUD gaps
  ⚠ 5 access control questions

Proceeding to interactive Q&A...
```

### Cost Estimation & Safety

```python
def estimate_cost(spec_size_kb: float, provider: str, model: str) -> float:
    """Estimate API cost before making request."""

    # Token estimation (rough: 1KB ≈ 750 tokens)
    estimated_tokens = spec_size_kb * 750

    # Add prompt overhead
    system_prompt_tokens = 500
    output_tokens = 8000  # Structured analysis

    total_input_tokens = estimated_tokens + system_prompt_tokens
    total_output_tokens = output_tokens

    # Pricing (as of 2024)
    pricing = {
        "anthropic": {
            "claude-3-5-sonnet-20241022": {
                "input": 3.00 / 1_000_000,   # $3 per MTok
                "output": 15.00 / 1_000_000  # $15 per MTok
            }
        },
        "openai": {
            "gpt-4-turbo": {
                "input": 10.00 / 1_000_000,
                "output": 30.00 / 1_000_000
            }
        }
    }

    rates = pricing[provider][model]
    cost = (total_input_tokens * rates["input"] +
            total_output_tokens * rates["output"])

    return cost

# Before API call:
estimated_cost = estimate_cost(spec_size_kb=12.5, provider="anthropic",
                               model="claude-3-5-sonnet-20241022")
print(f"Estimated cost: ${estimated_cost:.2f}")

if estimated_cost > config.max_cost_per_analysis:
    print(f"⚠ Cost exceeds limit (${config.max_cost_per_analysis})")
    if not prompt_user("Continue anyway?"):
        sys.exit(1)
```

---

## Approach 2: CLI Tool Handoff

### Architecture

```
dazzle analyze-spec SPEC.md --mode cli --tool claude-code
        ↓
    [Prepare handoff bundle]
        ├─ analysis_request.md (prompt)
        ├─ SPEC.md (spec content)
        └─ analysis_schema.json (output format)
        ↓
    [Invoke CLI tool]
        ↓
    [Tool writes output]
        ↓
    [DAZZLE reads output]
        ↓
    [Continue with questions]
```

### Key Design Decisions

**1. Communication Method**: File-based handoff
   - Stdin/stdout too limiting for rich context
   - Files allow tool to read spec, write structured output
   - Works with any tool (Claude Code, Cursor, Aider, etc.)

**2. Handoff Location**: `.dazzle/llm_handoff/`
   - Temporary workspace for LLM tool
   - Contains all context needed
   - Output written back to this location

**3. Tool Invocation**: Configurable command template
   - Different tools have different CLIs
   - User configures how to invoke their tool

### Configuration

**File: `~/.dazzle/config.toml`**

```toml
[llm]
mode = "cli"  # Use CLI tool handoff

# CLI tool configuration
[llm.cli]
# Which tool to use: "claude-code", "aider", "custom"
tool = "claude-code"

# How to invoke the tool
# Variables: {handoff_dir}, {prompt_file}, {output_file}
invoke_command = "claude-code --prompt-file {prompt_file} --output {output_file}"

# Alternative for interactive tools:
# invoke_command = "code --wait {handoff_dir}"  # Opens in VS Code with Claude
# invoke_command = "cursor --wait {handoff_dir}"  # Opens in Cursor

# Timeout for tool completion (seconds)
timeout = 300  # 5 minutes

# Auto-open handoff directory in editor?
auto_open_editor = true
editor_command = "code {handoff_dir}"  # VS Code

# Validation
validate_output = true
output_format = "json"  # or "markdown"
```

### Handoff Directory Structure

```
.dazzle/llm_handoff/
├── README.md                    # Instructions for LLM tool
├── analysis_request.md          # Main prompt
├── SPEC.md                      # Spec content (symlink or copy)
├── analysis_schema.json         # Expected output format
├── examples/                    # Example analyses
│   └── example_analysis.json
└── output/
    ├── analysis.json            # LLM writes here
    └── notes.md                 # Optional: LLM's reasoning
```

### Handoff Bundle Contents

**File: `.dazzle/llm_handoff/README.md`**

```markdown
# DAZZLE Spec Analysis Handoff

This directory contains a specification analysis request from DAZZLE.

## What DAZZLE needs

DAZZLE is analyzing a product specification (`SPEC.md`) to prepare for code generation.

Your task is to read the spec and produce a structured analysis identifying:
- State machines (entities with status/state fields and their transitions)
- CRUD completeness (which Create/Read/Update/Delete operations are mentioned)
- Business rules (validation, access control, constraints)
- Clarifying questions (gaps that need founder input)

## Input Files

- `SPEC.md` - The specification to analyze
- `analysis_request.md` - Detailed instructions
- `analysis_schema.json` - Required output format

## Output

Write your analysis to: `output/analysis.json`

Follow the exact JSON schema in `analysis_schema.json`.

## How to Proceed

1. Read `SPEC.md` thoroughly
2. Read `analysis_request.md` for specific instructions
3. Review `examples/example_analysis.json` for reference
4. Write your analysis to `output/analysis.json`
5. Optionally: Add reasoning notes to `output/notes.md`

## Validation

After writing `output/analysis.json`, DAZZLE will:
- Validate against schema
- Check for required fields
- Proceed with interactive Q&A

## Questions?

This is an automated handoff. If the task is unclear:
- Check `analysis_request.md` for details
- Review example files
- Make reasonable assumptions and document them in `output/notes.md`
```

**File: `.dazzle/llm_handoff/analysis_request.md`**

```markdown
# Specification Analysis Request

## Context

You are analyzing a specification for the DAZZLE DSL-based application generator.

DAZZLE generates web applications from a declarative DSL. To create a complete DSL,
we need to extract structured information from the founder's natural language spec.

## Your Task

Analyze `SPEC.md` and produce a JSON file (`output/analysis.json`) containing:

### 1. State Machines

Identify entities with state/status fields and extract:
- All states mentioned
- Explicit transitions (A → B when X happens)
- Implied transitions (mentioned in workflows but not formalized)
- Missing transitions (gaps in the state machine)
- Clarifying questions for ambiguous transitions

### 2. CRUD Analysis

For each entity mentioned, determine:
- Which CRUD operations are mentioned in the spec
- Who can perform each operation
- Any constraints or special rules
- Missing operations that should be clarified

### 3. Business Rules

Extract:
- Validation rules (required fields, uniqueness, formats)
- Access control (who can do what)
- Cascade rules (what happens when X is deleted)
- Computed/derived fields
- Constraints

### 4. Clarifying Questions

Generate questions for the founder about:
- Incomplete state machines
- Missing CRUD operations
- Ambiguous access control
- Edge cases not covered

## Output Format

Write valid JSON following the schema in `analysis_schema.json`.

See `examples/example_analysis.json` for a complete example.

## Important Notes

- Focus on extracting what's IN the spec, not what you think should be there
- Flag gaps and ambiguities as questions, don't assume
- Provide line references when possible (e.g., "SPEC.md:123")
- Be specific in questions (give options, explain impact)

## Quality Checklist

Before submitting, verify:
- [ ] All entities mentioned in spec are analyzed
- [ ] State machines have complete transition rules or questions
- [ ] CRUD analysis covers C, R, U, D, List for each entity
- [ ] Questions are specific and actionable
- [ ] JSON is valid and follows schema
```

**File: `.dazzle/llm_handoff/analysis_schema.json`**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "DAZZLE Spec Analysis",
  "type": "object",
  "required": ["state_machines", "crud_analysis", "business_rules", "clarifying_questions"],
  "properties": {
    "state_machines": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["entity", "field", "states", "transitions_found"],
        "properties": {
          "entity": {"type": "string"},
          "field": {"type": "string"},
          "states": {"type": "array", "items": {"type": "string"}},
          "transitions_found": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["from", "to", "trigger"],
              "properties": {
                "from": {"type": "string"},
                "to": {"type": "string"},
                "trigger": {"type": "string"},
                "location": {"type": "string"},
                "side_effects": {"type": "array", "items": {"type": "string"}},
                "conditions": {"type": "array", "items": {"type": "string"}}
              }
            }
          },
          "transitions_implied_but_missing": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["from", "to", "reason", "question"],
              "properties": {
                "from": {"type": "string"},
                "to": {"type": "string"},
                "reason": {"type": "string"},
                "question": {"type": "string"}
              }
            }
          }
        }
      }
    },
    "crud_analysis": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["entity", "operations_mentioned"],
        "properties": {
          "entity": {"type": "string"},
          "operations_mentioned": {
            "type": "object",
            "properties": {
              "create": {"$ref": "#/definitions/operation"},
              "read": {"$ref": "#/definitions/operation"},
              "update": {"$ref": "#/definitions/operation"},
              "delete": {"$ref": "#/definitions/operation"},
              "list": {"$ref": "#/definitions/operation"}
            }
          },
          "missing_operations": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "business_rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "entity", "rule"],
        "properties": {
          "type": {"enum": ["validation", "constraint", "access_control", "cascade"]},
          "entity": {"type": "string"},
          "field": {"type": "string"},
          "rule": {"type": "string"},
          "location": {"type": "string"}
        }
      }
    },
    "clarifying_questions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["category", "priority", "questions"],
        "properties": {
          "category": {"type": "string"},
          "priority": {"enum": ["high", "medium", "low"]},
          "questions": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["q", "context", "options", "impacts"],
              "properties": {
                "q": {"type": "string"},
                "context": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "impacts": {"type": "string"}
              }
            }
          }
        }
      }
    }
  },
  "definitions": {
    "operation": {
      "type": "object",
      "required": ["found"],
      "properties": {
        "found": {"type": "boolean"},
        "location": {"type": "string"},
        "who": {"type": "string"},
        "question": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

### Implementation

**File: `dazzle/llm/cli_handoff.py`**

```python
import os
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional

class CLIHandoff:
    """Handoff spec analysis to local CLI tool (Claude Code, Aider, etc.)."""

    def __init__(self, config: Dict[str, Any]):
        self.tool = config.get("tool", "claude-code")
        self.invoke_command = config.get("invoke_command")
        self.timeout = config.get("timeout", 300)
        self.auto_open = config.get("auto_open_editor", True)
        self.editor_command = config.get("editor_command", "code {handoff_dir}")

        # Handoff directory
        self.handoff_dir = Path.home() / ".dazzle" / "llm_handoff"
        self.output_file = self.handoff_dir / "output" / "analysis.json"

    def analyze_spec(self, spec_content: str, spec_path: str) -> Dict[str, Any]:
        """
        Prepare handoff bundle, invoke CLI tool, and read results.
        """
        print(f"🔄 Preparing handoff for {self.tool}...")

        # 1. Prepare handoff directory
        self._prepare_handoff_bundle(spec_content, spec_path)

        # 2. Invoke CLI tool
        success = self._invoke_tool()

        if not success:
            raise RuntimeError(f"CLI tool {self.tool} failed or timed out")

        # 3. Read and validate output
        analysis = self._read_output()

        # 4. Cleanup
        self._cleanup()

        return analysis

    def _prepare_handoff_bundle(self, spec_content: str, spec_path: str):
        """Create handoff directory with all necessary files."""

        # Create/clear handoff directory
        self.handoff_dir.mkdir(parents=True, exist_ok=True)

        # Clear previous output
        output_dir = self.handoff_dir / "output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir()

        # Copy spec file
        spec_file = self.handoff_dir / "SPEC.md"
        spec_file.write_text(spec_content)

        # Write README
        readme = self._generate_readme()
        (self.handoff_dir / "README.md").write_text(readme)

        # Write analysis request
        request = self._generate_analysis_request()
        (self.handoff_dir / "analysis_request.md").write_text(request)

        # Write schema
        schema = self._get_analysis_schema()
        (self.handoff_dir / "analysis_schema.json").write_text(
            json.dumps(schema, indent=2)
        )

        # Copy examples if they exist
        examples_dir = self.handoff_dir / "examples"
        examples_dir.mkdir(exist_ok=True)
        # TODO: Include example analysis

        print(f"✓ Handoff bundle prepared at: {self.handoff_dir}")

    def _invoke_tool(self) -> bool:
        """Invoke the configured CLI tool."""

        if self.invoke_command:
            # Use configured command
            cmd = self.invoke_command.format(
                handoff_dir=self.handoff_dir,
                prompt_file=self.handoff_dir / "analysis_request.md",
                output_file=self.output_file
            )

            print(f"🚀 Invoking {self.tool}: {cmd}")

            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    timeout=self.timeout,
                    capture_output=True,
                    text=True
                )

                if result.returncode == 0:
                    print(f"✓ {self.tool} completed successfully")
                    return True
                else:
                    print(f"✗ {self.tool} failed: {result.stderr}")
                    return False

            except subprocess.TimeoutExpired:
                print(f"✗ {self.tool} timed out after {self.timeout}s")
                return False

        else:
            # Manual mode - open in editor and wait
            if self.auto_open:
                editor_cmd = self.editor_command.format(handoff_dir=self.handoff_dir)
                subprocess.run(editor_cmd, shell=True)

            print(f"\n📂 Handoff directory opened: {self.handoff_dir}")
            print(f"\nPlease use {self.tool} to:")
            print(f"  1. Read SPEC.md")
            print(f"  2. Follow instructions in analysis_request.md")
            print(f"  3. Write analysis to output/analysis.json")
            print(f"\nPress Enter when analysis is complete...")
            input()

            # Check if output exists
            if self.output_file.exists():
                return True
            else:
                print(f"✗ No output file found at {self.output_file}")
                return False

    def _read_output(self) -> Dict[str, Any]:
        """Read and validate the analysis output."""

        if not self.output_file.exists():
            raise FileNotFoundError(f"Output file not found: {self.output_file}")

        try:
            with open(self.output_file) as f:
                analysis = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in output file: {e}")

        # Validate against schema
        # TODO: Implement JSON schema validation

        print(f"✓ Analysis loaded from {self.output_file}")
        return analysis

    def _cleanup(self):
        """Optional: Clean up handoff directory."""
        # Keep for debugging by default
        pass

    def _generate_readme(self) -> str:
        """Generate README.md for handoff bundle."""
        # Return the README content from above
        return """[README content from above]"""

    def _generate_analysis_request(self) -> str:
        """Generate analysis_request.md."""
        # Return the analysis request content from above
        return """[Analysis request content from above]"""

    def _get_analysis_schema(self) -> dict:
        """Get the JSON schema for analysis output."""
        # Return the schema from above
        return {...}
```

### Tool-Specific Adapters

**For Claude Code:**

```bash
# ~/.dazzle/config.toml
[llm.cli]
tool = "claude-code"

# Option 1: Non-interactive (Claude Code runs analysis and exits)
invoke_command = "claude --prompt 'Analyze the spec in {handoff_dir} and write output to {output_file}'"

# Option 2: Interactive (user works with Claude Code)
auto_open_editor = true
editor_command = "code {handoff_dir}"
```

**For Aider:**

```bash
[llm.cli]
tool = "aider"
invoke_command = "cd {handoff_dir} && aider --yes --message 'Read analysis_request.md and SPEC.md, then write analysis to output/analysis.json following the schema'"
```

**For Cursor:**

```bash
[llm.cli]
tool = "cursor"
auto_open_editor = true
editor_command = "cursor {handoff_dir}"
# User manually runs analysis in Cursor
```

### User Experience

```bash
$ dazzle analyze-spec SPEC.md --mode cli --tool claude-code

🔄 Preparing handoff for claude-code...
✓ Handoff bundle prepared at: ~/.dazzle/llm_handoff

🚀 Invoking claude-code...

[Claude Code runs analysis...]

✓ claude-code completed successfully
✓ Analysis loaded from ~/.dazzle/llm_handoff/output/analysis.json

Found:
  ✓ 1 state machine (Ticket.status)
  ✓ 7 transitions
  ⚠ 3 CRUD gaps

Proceeding to interactive Q&A...
```

**Or in manual mode:**

```bash
$ dazzle analyze-spec SPEC.md --mode cli --manual

🔄 Preparing handoff for manual analysis...
✓ Handoff bundle prepared at: ~/.dazzle/llm_handoff
📂 Opening in VS Code...

Please use your LLM tool to:
  1. Read SPEC.md
  2. Follow instructions in analysis_request.md
  3. Write analysis to output/analysis.json

Press Enter when analysis is complete...
```

---

## Comparison: API vs CLI Handoff

| Aspect | API Mode | CLI Handoff |
|--------|----------|-------------|
| **Setup** | API key + config | Tool installation |
| **Speed** | Fast (seconds) | Slower (minutes) |
| **Cost** | Per-token pricing | Free (local) or subscription |
| **Privacy** | Data sent to API | Data stays local |
| **Automation** | Fully automated | Can be interactive |
| **Flexibility** | Limited to API capabilities | Full tool capabilities |
| **Offline** | Requires internet | Can work offline |
| **Integration** | Simple (HTTP) | Complex (file handoff) |

---

## Unified CLI Interface

**File: `dazzle/cli.py`**

```python
import click
from dazzle.llm.api_client import LLMAPIClient
from dazzle.llm.cli_handoff import CLIHandoff
from dazzle.config import load_config

@click.command()
@click.argument('spec_file', type=click.Path(exists=True))
@click.option('--mode', type=click.Choice(['api', 'cli', 'auto']),
              default='auto', help='LLM integration mode')
@click.option('--provider', help='API provider (if mode=api)')
@click.option('--tool', help='CLI tool name (if mode=cli)')
@click.option('--interactive/--no-interactive', default=True,
              help='Interactive Q&A after analysis')
def analyze_spec(spec_file, mode, provider, tool, interactive):
    """Analyze a specification file for DSL generation."""

    # Load config
    config = load_config()

    # Override with CLI options
    if mode == 'auto':
        mode = config['llm']['mode']
    if provider:
        config['llm']['provider'] = provider
    if tool:
        config['llm']['cli']['tool'] = tool

    # Read spec file
    with open(spec_file) as f:
        spec_content = f.read()

    # Choose integration method
    if mode == 'api':
        client = LLMAPIClient(config['llm'])
        print(f"🔍 Analyzing via {config['llm']['provider']} API...")
    elif mode == 'cli':
        client = CLIHandoff(config['llm']['cli'])
        print(f"🔄 Analyzing via {config['llm']['cli']['tool']}...")

    # Run analysis
    try:
        analysis = client.analyze_spec(spec_content, spec_file)
    except Exception as e:
        click.echo(f"✗ Analysis failed: {e}", err=True)
        return 1

    # Display results
    display_analysis_summary(analysis)

    # Interactive Q&A
    if interactive:
        answers = run_interactive_qa(analysis['clarifying_questions'])

        # Generate enhanced spec + DSL
        generate_enhanced_spec(spec_content, analysis, answers)
        generate_dsl(spec_content, analysis, answers)

    return 0

def display_analysis_summary(analysis):
    """Display analysis results."""
    click.echo("\n📊 Analysis Results:")
    click.echo("─" * 50)

    # State machines
    if analysis.get('state_machines'):
        for sm in analysis['state_machines']:
            click.echo(f"\n✓ State machine: {sm['entity']}.{sm['field']}")
            click.echo(f"  States: {', '.join(sm['states'])}")
            click.echo(f"  Transitions: {len(sm['transitions_found'])} found")
            if sm.get('transitions_implied_but_missing'):
                click.echo(f"  ⚠ {len(sm['transitions_implied_but_missing'])} gaps")

    # CRUD gaps
    crud_gaps = sum(len(e.get('missing_operations', []))
                    for e in analysis.get('crud_analysis', []))
    if crud_gaps:
        click.echo(f"\n⚠ {crud_gaps} CRUD operations need clarification")

    # Questions
    total_questions = sum(len(cat['questions'])
                         for cat in analysis.get('clarifying_questions', []))
    click.echo(f"\n❓ {total_questions} clarifying questions")

def run_interactive_qa(questions):
    """Run interactive Q&A session."""
    click.echo("\n" + "="*50)
    click.echo("Interactive Q&A")
    click.echo("="*50)

    answers = {}

    for category in questions:
        click.echo(f"\n📋 {category['category']} (Priority: {category['priority']})")
        click.echo("─" * 50)

        for i, q in enumerate(category['questions'], 1):
            click.echo(f"\n{i}. {q['q']}")
            click.echo(f"   Context: {q['context']}")
            click.echo(f"   Options:")
            for j, opt in enumerate(q['options'], 1):
                click.echo(f"     {j}) {opt}")

            # Get answer
            while True:
                answer_idx = click.prompt("   Choose", type=int)
                if 1 <= answer_idx <= len(q['options']):
                    answers[q['q']] = q['options'][answer_idx - 1]
                    break
                else:
                    click.echo("   Invalid choice, try again")

    return answers
```

---

## Advanced: Protocol for Tool Integration

Define a standard that any LLM tool can implement:

**File: `.dazzle/protocols/spec_analysis_v1.json`**

```json
{
  "protocol": "dazzle-spec-analysis",
  "version": "1.0",
  "description": "Standard protocol for LLM tools to analyze DAZZLE specs",

  "input": {
    "location": ".dazzle/llm_handoff/",
    "files": {
      "spec": "SPEC.md",
      "instructions": "analysis_request.md",
      "schema": "analysis_schema.json"
    }
  },

  "output": {
    "location": ".dazzle/llm_handoff/output/",
    "required_files": {
      "analysis": "analysis.json"
    },
    "optional_files": {
      "notes": "notes.md",
      "questions": "questions.txt"
    }
  },

  "validation": {
    "schema_validation": true,
    "required_fields": ["state_machines", "crud_analysis", "clarifying_questions"]
  }
}
```

Any tool that implements this protocol can be used with DAZZLE:

```bash
$ dazzle analyze-spec SPEC.md --protocol spec-analysis-v1 --tool my-custom-tool
```

---

## Recommendations

### For Prototyping
- **Use API mode** with Anthropic Claude
- Fast iteration, good quality
- Cost is minimal for specs (<$1 per analysis)

### For Production
- **Support both modes**
- API for automated workflows (CI/CD)
- CLI handoff for developer workflows
- Let users choose based on their setup

### For Privacy-Sensitive Projects
- **Use CLI handoff with local models**
- Tools like LM Studio, Ollama
- No data leaves the machine

### For Best Results
- **Start with API analysis** (fast, accurate)
- **Use CLI handoff for refinement** (human-in-the-loop)
- **Iterate** as spec evolves

---

## Implementation Roadmap

### Phase 1: API Mode (Week 1)
- [ ] LLMAPIClient with Anthropic
- [ ] Basic spec analysis prompt
- [ ] JSON parsing and validation
- [ ] Cost estimation and safety

### Phase 2: CLI Handoff (Week 2)
- [ ] Handoff bundle generation
- [ ] File-based communication
- [ ] Tool invocation (Claude Code, Aider)
- [ ] Output validation

### Phase 3: Interactive Q&A (Week 3)
- [ ] Question presentation UI
- [ ] Answer collection
- [ ] Enhanced spec generation

### Phase 4: DSL Generation (Week 4)
- [ ] Analysis → DSL translation
- [ ] Template system
- [ ] Validation

### Phase 5: Polish (Week 5)
- [ ] Error handling
- [ ] Progress indicators
- [ ] Documentation
- [ ] Tests

---

## Next Steps

1. **Implement API mode first** (simpler, faster feedback)
2. **Test with real specs** (our SPEC.md is perfect test case)
3. **Add CLI handoff** for local workflows
4. **Define protocol** for tool interoperability
5. **Document** for users and tool developers
