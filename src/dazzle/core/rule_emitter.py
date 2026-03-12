"""
DSL emitter for rule specifications.

Converts RuleSpec IR objects to DSL text for writing to .dsl files.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.rules import RuleSpec


def emit_rule_dsl(rule: RuleSpec) -> str:
    """Serialize a RuleSpec to DSL text."""
    from dazzle.core.ir.rules import RuleKind, RuleOrigin, RuleStatus

    lines: list[str] = []

    lines.append(f'rule {rule.rule_id} "{rule.title}":')

    if rule.description:
        lines.append(f'  "{rule.description}"')

    if rule.kind != RuleKind.CONSTRAINT:
        lines.append(f"  kind: {rule.kind.value}")
    else:
        lines.append(f"  kind: {rule.kind.value}")

    if rule.origin != RuleOrigin.TOP_DOWN:
        lines.append(f"  origin: {rule.origin.value}")

    if rule.invariant:
        lines.append(f"  invariant: {rule.invariant}")

    if rule.scope:
        scope_str = ", ".join(rule.scope)
        lines.append(f"  scope: [{scope_str}]")

    if rule.status and rule.status != RuleStatus.DRAFT:
        lines.append(f"  status: {rule.status.value}")

    return "\n".join(lines)


def get_next_rule_id(rules: list[RuleSpec]) -> str:
    """Determine the next rule ID from a list of rules."""
    max_num = 0
    for rule in rules:
        rid = rule.rule_id
        if rid.startswith("RULE-"):
            try:
                num = int(rid.split("-")[-1])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f"RULE-{max_num + 1:03d}"


def append_rules_to_dsl(project_root: Path, rules: list[RuleSpec]) -> Path:
    """Append rule DSL blocks to ``dsl/rules.dsl``."""
    dsl_dir = project_root / "dsl"
    dsl_dir.mkdir(parents=True, exist_ok=True)

    rules_file = dsl_dir / "rules.dsl"
    blocks = [emit_rule_dsl(r) for r in rules]
    new_text = "\n\n".join(blocks) + "\n"

    if rules_file.exists():
        existing = rules_file.read_text()
        if existing and not existing.endswith("\n"):
            existing += "\n"
        rules_file.write_text(existing + "\n" + new_text)
    else:
        rules_file.write_text(new_text)

    return rules_file
