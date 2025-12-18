"""
Process execution context for tracking state during workflow execution.

ProcessContext accumulates step outputs and provides expression resolution
for input mappings between steps.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProcessContext(BaseModel):
    """
    Execution context for a process run.

    Tracks:
    - Initial inputs
    - Step outputs (accumulated)
    - Current step being executed
    - Timing information

    Provides expression resolution for input/output mappings.
    """

    inputs: dict[str, Any] = Field(default_factory=dict, description="Process inputs")
    step_outputs: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Outputs from each completed step"
    )
    current_step: str | None = Field(default=None, description="Currently executing step")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    variables: dict[str, Any] = Field(default_factory=dict, description="User-defined variables")

    model_config = ConfigDict(frozen=False)

    def update_step(self, step_name: str, output: dict[str, Any]) -> None:
        """Record output from a completed step."""
        self.step_outputs[step_name] = output

    def set_current_step(self, step_name: str | None) -> None:
        """Update the currently executing step."""
        self.current_step = step_name

    def set_variable(self, name: str, value: Any) -> None:
        """Set a context variable."""
        self.variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self.variables.get(name, default)

    def resolve(self, expression: str) -> Any:
        """
        Resolve an expression to a value.

        Supported expressions:
        - "inputs.field_name" -> process input
        - "step_name.field_name" -> step output
        - "vars.name" -> context variable
        - "literal_value" -> literal string
        - "${expr}" -> interpolated expression

        Examples:
            resolve("inputs.order_id") -> "123"
            resolve("validate_order.is_valid") -> True
            resolve("vars.counter") -> 5
        """
        if expression is None:
            return None

        # Check for interpolation pattern ${...}
        if "${" in expression:
            return self._interpolate(expression)

        # Split path
        parts = expression.split(".")
        if len(parts) < 2:
            # Literal value
            return expression

        root = parts[0]
        path = parts[1:]

        # Resolve root
        if root == "inputs":
            obj = self.inputs
        elif root == "vars":
            obj = self.variables
        elif root in self.step_outputs:
            obj = self.step_outputs[root]
        else:
            # Unknown root, return as literal
            return expression

        # Navigate path
        return self._navigate(obj, path)

    def _navigate(self, obj: Any, path: list[str]) -> Any:
        """Navigate a dotted path through an object."""
        for part in path:
            if obj is None:
                return None
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                # Try array indexing
                try:
                    idx = int(part)
                    obj = obj[idx]
                except (ValueError, IndexError, TypeError):
                    return None
        return obj

    def _interpolate(self, template: str) -> str:
        """Interpolate ${...} expressions in a template string."""
        pattern = r"\$\{([^}]+)\}"

        def replacer(match: re.Match[str]) -> str:
            expr = match.group(1)
            value = self.resolve(expr)
            return str(value) if value is not None else ""

        return re.sub(pattern, replacer, template)

    def evaluate_condition(self, condition: str) -> bool:
        """
        Evaluate a boolean condition expression.

        Supported operators:
        - "expr == value" -> equality
        - "expr != value" -> inequality
        - "expr > value" -> greater than (numeric)
        - "expr < value" -> less than (numeric)
        - "expr >= value" -> greater or equal (numeric)
        - "expr <= value" -> less or equal (numeric)
        - "expr" -> truthy check

        Examples:
            evaluate_condition("validate_order.is_valid == true")
            evaluate_condition("inputs.amount > 1000")
            evaluate_condition("check_inventory.in_stock")
        """
        if condition is None:
            return True

        condition = condition.strip()

        # Check for comparison operators
        for op in ["==", "!=", ">=", "<=", ">", "<"]:
            if op in condition:
                parts = condition.split(op, 1)
                if len(parts) == 2:
                    left = self.resolve(parts[0].strip())
                    right_str = parts[1].strip()

                    # Parse right side
                    right = self._parse_literal(right_str)

                    return self._compare(left, right, op)

        # Simple truthy check
        value = self.resolve(condition)
        return bool(value)

    def _parse_literal(self, value: str) -> Any:
        """Parse a literal value from string."""
        value = value.strip()

        # Boolean literals
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # Null literal
        if value.lower() in ("null", "none"):
            return None

        # Quoted string
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]

        # Try numeric
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Otherwise, resolve as expression
        return self.resolve(value)

    def _compare(self, left: Any, right: Any, op: str) -> bool:
        """Compare two values with an operator."""
        try:
            if op == "==":
                return bool(left == right)
            elif op == "!=":
                return bool(left != right)
            elif op == ">":
                return bool(left > right)
            elif op == "<":
                return bool(left < right)
            elif op == ">=":
                return bool(left >= right)
            elif op == "<=":
                return bool(left <= right)
        except TypeError:
            # Incompatible types
            return False
        return False

    def build_step_inputs(self, mappings: list[tuple[str, str]]) -> dict[str, Any]:
        """
        Build step inputs from a list of (source, target) mappings.

        Args:
            mappings: List of (source_expression, target_field) tuples

        Returns:
            Dict of resolved inputs for the step
        """
        result: dict[str, Any] = {}
        for source, target in mappings:
            value = self.resolve(source)
            result[target] = value
        return result

    def to_dict(self) -> dict[str, Any]:
        """Export context as a serializable dict."""
        return {
            "inputs": self.inputs,
            "step_outputs": self.step_outputs,
            "current_step": self.current_step,
            "started_at": self.started_at.isoformat(),
            "variables": self.variables,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProcessContext:
        """Restore context from a dict."""
        started_at = data.get("started_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        else:
            started_at = datetime.utcnow()

        return cls(
            inputs=data.get("inputs", {}),
            step_outputs=data.get("step_outputs", {}),
            current_step=data.get("current_step"),
            started_at=started_at,
            variables=data.get("variables", {}),
        )

    @property
    def outputs(self) -> dict[str, Any]:
        """Get the accumulated outputs (all step outputs merged)."""
        result: dict[str, Any] = {}
        for step_name, outputs in self.step_outputs.items():
            for key, value in outputs.items():
                result[f"{step_name}.{key}"] = value
        return result
