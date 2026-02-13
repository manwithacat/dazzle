"""
MCP handlers for community contribution packaging.

Helps users package their contributions (API packs, UI improvements, bug fixes,
DSL patterns, feature requests) in a structured format for sharing with the
Dazzle team.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

from dazzle.mcp.server.progress import ProgressContext
from dazzle.mcp.server.progress import noop as _noop_progress


def _get_dazzle_version() -> str:
    """Get the current Dazzle version."""
    try:
        from dazzle import __version__

        return __version__
    except ImportError:
        return "unknown"


def _get_python_version() -> str:
    """Get Python version."""
    return platform.python_version()


def _get_os_info() -> str:
    """Get OS information."""
    return f"{platform.system()} {platform.release()}"


CONTRIBUTION_TYPES = [
    {
        "type": "api_pack",
        "description": "New API integration pack (generates TOML + Markdown)",
        "required_content": ["provider", "category", "base_url"],
        "optional_content": [
            "docs_url",
            "auth_type",
            "env_vars",
            "operations",
            "models",
        ],
    },
    {
        "type": "ui_pattern",
        "description": "UI component or layout improvement",
        "required_content": ["use_case", "current_behavior", "proposed_behavior"],
        "optional_content": ["surface_dsl", "mockup_description", "implementation_notes"],
    },
    {
        "type": "bug_fix",
        "description": "Bug fix with reproduction steps and proposed solution",
        "required_content": ["reproduction_steps", "expected", "actual"],
        "optional_content": ["files_changed", "diff", "testing_notes"],
    },
    {
        "type": "dsl_pattern",
        "description": "New DSL pattern, workflow, or story",
        "required_content": ["pattern_type", "dsl_code"],
        "optional_content": ["use_cases", "generated_behavior", "related_patterns"],
    },
    {
        "type": "feature_request",
        "description": "Enhancement suggestion or RFC",
        "required_content": ["motivation", "proposed_solution"],
        "optional_content": ["alternatives", "dsl_impact", "backwards_compatibility"],
    },
]

GITHUB_ISSUE_BASE = "https://github.com/manwithacat/dazzle/issues/new"


def templates_handler(args: dict[str, Any]) -> str:
    """List available contribution templates."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Loading contribution templates...")
    return json.dumps(
        {
            "templates": CONTRIBUTION_TYPES,
            "submission_url": GITHUB_ISSUE_BASE,
            "usage": "Use create operation with type and content to generate a contribution package",
        },
        indent=2,
    )


def create_handler(args: dict[str, Any]) -> str:
    """Create a contribution package."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Creating contribution package...")
    contrib_type = args.get("type")
    title = args.get("title", "Untitled Contribution")
    description = args.get("description", "")
    content = args.get("content", {})
    output_dir = args.get("output_dir")

    if not contrib_type:
        return json.dumps({"error": "type is required"})

    valid_types = [t["type"] for t in CONTRIBUTION_TYPES]
    if contrib_type not in valid_types:
        return json.dumps({"error": f"Invalid type: {contrib_type}. Valid types: {valid_types}"})

    # Pre-check GitHub auth before doing expensive generation work
    from dazzle.mcp.server.github_issues import gh_auth_guidance

    gh_status = gh_auth_guidance()

    # Generate contribution based on type
    if contrib_type == "api_pack":
        result = _generate_api_pack(title, description, content, output_dir)
    elif contrib_type == "bug_fix":
        result = _generate_bug_fix(title, description, content, output_dir)
    elif contrib_type == "ui_pattern":
        result = _generate_ui_pattern(title, description, content, output_dir)
    elif contrib_type == "dsl_pattern":
        result = _generate_dsl_pattern(title, description, content, output_dir)
    elif contrib_type == "feature_request":
        result = _generate_feature_request(title, description, content, output_dir)
    else:
        return json.dumps({"error": f"Unhandled type: {contrib_type}"})

    # Attempt to create a GitHub issue (only if authenticated)
    if gh_status["authenticated"]:
        from dazzle.mcp.server.github_issues import create_github_issue

        issue_body = result.get("markdown", "")
        if not issue_body and "files" in result:
            for fname, fcontent in result["files"].items():
                if fname.endswith(".md"):
                    issue_body = fcontent
                    break

        if issue_body:
            github_issue = create_github_issue(
                title=f"[Contribution] {title}",
                body=issue_body,
                labels=["contribution", contrib_type.replace("_", "-")],
            )
            result["github_issue"] = github_issue
    else:
        result["github_issue"] = {
            "fallback": True,
            "manual_url": GITHUB_ISSUE_BASE,
            "auth_status": gh_status,
            "message": (
                "GitHub CLI is not authenticated. See auth_status.steps for setup instructions."
            ),
        }

    return json.dumps(result, indent=2)


def validate_handler(args: dict[str, Any]) -> str:
    """Validate a contribution package."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Validating contribution...")
    contrib_type = args.get("type")
    content = args.get("content", {})

    if not contrib_type:
        return json.dumps({"error": "type is required"})

    # Find the type definition
    type_def = next((t for t in CONTRIBUTION_TYPES if t["type"] == contrib_type), None)
    if not type_def:
        return json.dumps({"error": f"Unknown type: {contrib_type}"})

    # Check required fields
    missing = []
    for field in type_def["required_content"]:
        if field not in content or not content[field]:
            missing.append(field)

    if missing:
        return json.dumps(
            {
                "valid": False,
                "missing_required": missing,
                "type": contrib_type,
            }
        )

    return json.dumps(
        {
            "valid": True,
            "type": contrib_type,
            "message": "All required fields present",
        }
    )


def examples_handler(args: dict[str, Any]) -> str:
    """Show example contributions."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Loading example contributions...")
    contrib_type = args.get("type", "api_pack")

    examples = {
        "api_pack": {
            "title": "Plaid Banking API",
            "description": "Access bank account data via Plaid",
            "content": {
                "provider": "Plaid",
                "category": "banking",
                "base_url": "https://api.plaid.com",
                "docs_url": "https://plaid.com/docs",
                "auth_type": "api_key",
                "env_vars": {
                    "PLAID_CLIENT_ID": "Plaid client ID",
                    "PLAID_SECRET": "Plaid secret key",
                },
                "operations": {
                    "get_accounts": {"method": "GET", "path": "/accounts/get"},
                    "get_transactions": {"method": "GET", "path": "/transactions/get"},
                },
                "models": {
                    "Account": {
                        "fields": {
                            "account_id": "str(50) pk",
                            "name": "str(100)",
                            "type": "str(20)",
                            "balance": "decimal(12,2)",
                        }
                    }
                },
            },
        },
        "bug_fix": {
            "title": "Fix list pagination reset on filter clear",
            "description": "Pagination resets to page 1 when clearing filters",
            "content": {
                "reproduction_steps": [
                    "Navigate to a list view with pagination",
                    "Apply a filter",
                    "Go to page 2 or later",
                    "Clear the filter",
                ],
                "expected": "Stay on current page after clearing filter",
                "actual": "Page resets to 1",
                "files_changed": ["src/dazzle_ui/runtime/static/js/components.js"],
                "testing_notes": "Verified fix on simple_task example",
            },
        },
        "ui_pattern": {
            "title": "Collapsible sidebar navigation",
            "description": "Allow sidebar to collapse to icons only",
            "content": {
                "use_case": "Users with smaller screens or who prefer more content area",
                "current_behavior": "Sidebar is always fully expanded",
                "proposed_behavior": "Sidebar collapses to icon-only mode with hover expansion",
                "surface_dsl": """surface settings "Settings":
  layout: sidebar_collapsible
  section main:
    field theme "Theme"
""",
            },
        },
        "dsl_pattern": {
            "title": "Approval workflow pattern",
            "description": "Multi-step approval with escalation",
            "content": {
                "pattern_type": "workflow",
                "dsl_code": """entity PurchaseOrder "Purchase Order":
  id: uuid pk
  amount: decimal(12,2)
  status: enum[draft,pending,approved,rejected]

  state_machine:
    field: status
    initial: draft
    transitions:
      submit: draft -> pending
      approve: pending -> approved when amount < 1000
      escalate: pending -> pending when amount >= 1000
      reject: pending -> rejected
""",
                "use_cases": ["Purchase approvals", "Time-off requests", "Document review"],
            },
        },
        "feature_request": {
            "title": "GraphQL API generation",
            "description": "Generate GraphQL schema from DSL entities",
            "content": {
                "motivation": "Teams using GraphQL need native support",
                "proposed_solution": "Add graphql_api option to surface definition",
                "dsl_impact": "New surface mode: graphql",
                "backwards_compatibility": "Fully backwards compatible, opt-in feature",
            },
        },
    }

    example = examples.get(contrib_type)
    if not example:
        return json.dumps({"error": f"No example for type: {contrib_type}"})

    return json.dumps(
        {
            "type": contrib_type,
            "example": example,
            "usage": f"Use create operation with type='{contrib_type}' and similar content",
        },
        indent=2,
    )


# =============================================================================
# Contribution Generators
# =============================================================================


def _generate_api_pack(
    title: str, description: str, content: dict[str, Any], output_dir: str | None
) -> dict[str, Any]:
    """Generate API pack contribution (TOML + Markdown)."""
    provider = content.get("provider", "Provider")
    category = content.get("category", "general")
    base_url = content.get("base_url", "https://api.example.com")
    docs_url = content.get("docs_url", "")
    auth_type = content.get("auth_type", "api_key")
    env_vars = content.get("env_vars", {})
    operations = content.get("operations", {})
    models = content.get("models", {})
    testing_notes = content.get("testing_notes", "")

    # Generate safe name
    safe_name = f"{provider.lower()}_{category.lower()}".replace(" ", "_").replace("-", "_")

    # Generate TOML
    toml_lines = [
        "[pack]",
        f'name = "{safe_name}"',
        f'provider = "{provider}"',
        f'category = "{category}"',
        f'version = "{datetime.now().strftime("%Y-%m-%d")}"',
        f'description = "{description}"',
        f'base_url = "{base_url}"',
    ]
    if docs_url:
        toml_lines.append(f'docs_url = "{docs_url}"')

    toml_lines.extend(["", "[auth]", f'type = "{auth_type}"'])

    if env_vars:
        toml_lines.extend(["", "[env_vars]"])
        for var_name, var_desc in env_vars.items():
            toml_lines.append(f'{var_name} = {{ required = true, description = "{var_desc}" }}')

    if operations:
        toml_lines.extend(["", "[operations]"])
        for op_name, op_def in operations.items():
            method = op_def.get("method", "GET")
            path = op_def.get("path", "/")
            op_desc = op_def.get("description", "")
            toml_lines.append(
                f'{op_name} = {{ method = "{method}", path = "{path}", description = "{op_desc}" }}'
            )

    if models:
        for model_name, model_def in models.items():
            toml_lines.extend(
                [
                    "",
                    f"[foreign_models.{model_name}]",
                    f'description = "{model_name}"',
                    'key = "id"',
                ]
            )
            if "fields" in model_def:
                toml_lines.append(f"[foreign_models.{model_name}.fields]")
                for field_name, field_type in model_def["fields"].items():
                    toml_lines.append(f'{field_name} = {{ type = "{field_type}" }}')

    toml_content = "\n".join(toml_lines)

    # Generate Markdown
    ops_table = "| Operation | Method | Path |\n|-----------|--------|------|\n"
    for op_name, op_def in operations.items():
        ops_table += f"| {op_name} | {op_def.get('method', 'GET')} | {op_def.get('path', '/')} |\n"

    models_table = "| Model | Fields |\n|-------|--------|\n"
    for model_name, model_def in models.items():
        fields = ", ".join(model_def.get("fields", {}).keys())
        models_table += f"| {model_name} | {fields} |\n"

    markdown = f"""# API Pack Contribution: {title}

## Provider Information
- **Provider**: {provider}
- **Category**: {category}
- **API Docs**: {docs_url or "N/A"}

## What This Pack Provides
{description}

## Operations
{ops_table}

## Foreign Models
{models_table}

## Testing Notes
{testing_notes or "No testing notes provided."}

## Files Included
- `{safe_name}.toml` - Ready to add to `src/dazzle/api_kb/{provider.lower()}/`

---
*Generated by Dazzle contribution packager on {datetime.now().strftime("%Y-%m-%d")}*
*Submit via: {GITHUB_ISSUE_BASE}?labels=contribution,api-pack*
"""

    result: dict[str, Any] = {
        "status": "generated",
        "type": "api_pack",
        "files": {
            f"{safe_name}.toml": toml_content,
            f"{safe_name}_CONTRIBUTION.md": markdown,
        },
    }

    # Write files if output_dir specified
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        toml_path = out_path / f"{safe_name}.toml"
        md_path = out_path / f"{safe_name}_CONTRIBUTION.md"

        toml_path.write_text(toml_content)
        md_path.write_text(markdown)

        result["written_to"] = [str(toml_path), str(md_path)]

    return result


def _generate_bug_fix(
    title: str, description: str, content: dict[str, Any], output_dir: str | None
) -> dict[str, Any]:
    """Generate bug fix contribution."""
    steps = content.get("reproduction_steps", [])
    expected = content.get("expected", "")
    actual = content.get("actual", "")
    files_changed = content.get("files_changed", [])
    diff = content.get("diff", "")
    testing_notes = content.get("testing_notes", "")

    steps_md = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
    files_md = "\n".join(f"- `{f}`" for f in files_changed) if files_changed else "N/A"

    markdown = f"""# Bug Fix: {title}

## Summary
{description}

## Reproduction Steps
{steps_md}

## Expected Behavior
{expected}

## Actual Behavior
{actual}

## Environment
- Dazzle Version: {_get_dazzle_version()}
- Python Version: {_get_python_version()}
- OS: {_get_os_info()}

## Proposed Fix

### Files Changed
{files_md}

### Code Changes
```diff
{diff or "No diff provided"}
```

## Testing
{testing_notes or "No testing notes provided."}

---
*Generated by Dazzle contribution packager on {datetime.now().strftime("%Y-%m-%d")}*
*Submit via: {GITHUB_ISSUE_BASE}?labels=contribution,bug-fix*
"""

    result: dict[str, Any] = {
        "status": "generated",
        "type": "bug_fix",
        "markdown": markdown,
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        safe_title = title.lower().replace(" ", "-")[:50]
        md_path = out_path / f"bug-fix-{safe_title}.md"
        md_path.write_text(markdown)
        result["written_to"] = str(md_path)

    return result


def _generate_ui_pattern(
    title: str, description: str, content: dict[str, Any], output_dir: str | None
) -> dict[str, Any]:
    """Generate UI pattern contribution."""
    use_case = content.get("use_case", "")
    current = content.get("current_behavior", "")
    proposed = content.get("proposed_behavior", "")
    surface_dsl = content.get("surface_dsl", "")
    mockup = content.get("mockup_description", "")
    impl_notes = content.get("implementation_notes", "")

    markdown = f"""# UI Pattern Contribution: {title}

## Summary
{description}

## Use Case
{use_case}

## Current Behavior
{current}

## Proposed Behavior
{proposed}

## DSL Surface Example
```dsl
{surface_dsl or "# No DSL example provided"}
```

## Mockup/Screenshot
{mockup or "No mockup provided."}

## Implementation Notes
{impl_notes or "No implementation notes provided."}

---
*Generated by Dazzle contribution packager on {datetime.now().strftime("%Y-%m-%d")}*
*Submit via: {GITHUB_ISSUE_BASE}?labels=contribution,ui-pattern*
"""

    result: dict[str, Any] = {
        "status": "generated",
        "type": "ui_pattern",
        "markdown": markdown,
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        safe_title = title.lower().replace(" ", "-")[:50]
        md_path = out_path / f"ui-pattern-{safe_title}.md"
        md_path.write_text(markdown)
        result["written_to"] = str(md_path)

    return result


def _generate_dsl_pattern(
    title: str, description: str, content: dict[str, Any], output_dir: str | None
) -> dict[str, Any]:
    """Generate DSL pattern contribution."""
    pattern_type = content.get("pattern_type", "general")
    dsl_code = content.get("dsl_code", "")
    use_cases = content.get("use_cases", [])
    generated_behavior = content.get("generated_behavior", "")
    related = content.get("related_patterns", [])

    use_cases_md = "\n".join(f"- {uc}" for uc in use_cases) if use_cases else "N/A"
    related_md = "\n".join(f"- {r}" for r in related) if related else "N/A"

    markdown = f"""# DSL Pattern Contribution: {title}

## Summary
{description}

## Pattern Type
{pattern_type}

## DSL Example
```dsl
{dsl_code or "# No DSL code provided"}
```

## Use Cases
{use_cases_md}

## Generated Behavior
{generated_behavior or "No behavior description provided."}

## Related Patterns
{related_md}

---
*Generated by Dazzle contribution packager on {datetime.now().strftime("%Y-%m-%d")}*
*Submit via: {GITHUB_ISSUE_BASE}?labels=contribution,dsl-pattern*
"""

    result: dict[str, Any] = {
        "status": "generated",
        "type": "dsl_pattern",
        "markdown": markdown,
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        safe_title = title.lower().replace(" ", "-")[:50]
        md_path = out_path / f"dsl-pattern-{safe_title}.md"
        md_path.write_text(markdown)
        result["written_to"] = str(md_path)

    return result


def _generate_feature_request(
    title: str, description: str, content: dict[str, Any], output_dir: str | None
) -> dict[str, Any]:
    """Generate feature request contribution."""
    motivation = content.get("motivation", "")
    solution = content.get("proposed_solution", "")
    alternatives = content.get("alternatives", "")
    dsl_impact = content.get("dsl_impact", "")
    compat = content.get("backwards_compatibility", "")

    markdown = f"""# Feature Request: {title}

## Summary
{description}

## Motivation
{motivation}

## Proposed Solution
{solution}

## Alternatives Considered
{alternatives or "No alternatives provided."}

## DSL Impact
{dsl_impact or "No DSL impact described."}

## Backwards Compatibility
{compat or "Not assessed."}

---
*Generated by Dazzle contribution packager on {datetime.now().strftime("%Y-%m-%d")}*
*Submit via: {GITHUB_ISSUE_BASE}?labels=contribution,feature-request*
"""

    result: dict[str, Any] = {
        "status": "generated",
        "type": "feature_request",
        "markdown": markdown,
    }

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        safe_title = title.lower().replace(" ", "-")[:50]
        md_path = out_path / f"feature-request-{safe_title}.md"
        md_path.write_text(markdown)
        result["written_to"] = str(md_path)

    return result
