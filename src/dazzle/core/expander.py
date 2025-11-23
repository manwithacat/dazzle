"""
Vocabulary expander for DAZZLE.

Expands vocabulary references to core DSL using template substitution.
"""

from jinja2 import Environment, BaseLoader, TemplateError, StrictUndefined
from typing import Dict, Any, Set, Optional, List, Tuple
from pathlib import Path
import re

from .vocab import VocabManifest, VocabEntry, VocabParameter
from .errors import DazzleError


class ExpansionError(DazzleError):
    """Raised when vocabulary expansion fails."""
    pass


class VocabExpander:
    """
    Expands vocabulary references to core DSL.

    Handles template substitution, parameter validation, and cycle detection.
    """

    def __init__(self, manifest: VocabManifest):
        """
        Initialize expander with vocabulary manifest.

        Args:
            manifest: VocabManifest containing vocabulary entries
        """
        self.manifest = manifest
        self.jinja_env = Environment(
            loader=BaseLoader(),
            undefined=StrictUndefined,  # Raise error on undefined variables
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def expand_entry(
        self,
        entry_id: str,
        params: Dict[str, Any],
        visited: Optional[Set[str]] = None
    ) -> str:
        """
        Expand a vocabulary entry with given parameters.

        Args:
            entry_id: ID of vocabulary entry to expand
            params: Parameters to substitute into template
            visited: Set of visited entry IDs (for cycle detection)

        Returns:
            Expanded core DSL string

        Raises:
            ExpansionError: If expansion fails
        """
        if visited is None:
            visited = set()

        # Cycle detection
        if entry_id in visited:
            cycle = ' -> '.join(visited) + f' -> {entry_id}'
            raise ExpansionError(f"Circular dependency detected: {cycle}")

        visited.add(entry_id)

        # Get entry
        entry = self.manifest.get_entry(entry_id)
        if not entry:
            raise ExpansionError(f"Vocabulary entry '{entry_id}' not found")

        # Validate and prepare parameters
        prepared_params = self._prepare_parameters(entry, params)

        # Expand template
        try:
            template = self.jinja_env.from_string(entry.expansion['body'])
            expanded = template.render(**prepared_params)
        except TemplateError as e:
            raise ExpansionError(f"Template expansion failed for '{entry_id}': {e}")
        except Exception as e:
            raise ExpansionError(f"Unexpected error expanding '{entry_id}': {e}")

        # TODO: Recursively expand any nested vocab references in the result
        # For Phase 1, we'll keep it simple and not support nested references

        visited.remove(entry_id)
        return expanded

    def expand_text(self, text: str) -> str:
        """
        Expand all vocabulary references in text.

        Looks for @use directives and expands them to core DSL.

        Syntax: @use entry_id(param1=value1, param2=value2)

        Args:
            text: Text containing vocab references

        Returns:
            Text with all references expanded

        Raises:
            ExpansionError: If expansion fails
        """
        # Find all @use directives
        pattern = r'@use\s+([a-z0-9_]+)\((.*?)\)'
        matches = list(re.finditer(pattern, text, re.MULTILINE | re.DOTALL))

        if not matches:
            return text  # No vocab references found

        # Expand in reverse order to preserve positions
        result = text
        for match in reversed(matches):
            entry_id = match.group(1)
            params_str = match.group(2).strip()

            # Parse parameters
            params = self._parse_params(params_str) if params_str else {}

            # Expand entry
            try:
                expanded = self.expand_entry(entry_id, params)
            except ExpansionError as e:
                # Add context about where the error occurred
                line_num = text[:match.start()].count('\n') + 1
                raise ExpansionError(f"At line {line_num}: {e}")

            # Replace reference with expansion
            result = result[:match.start()] + expanded + result[match.end():]

        return result

    def expand_file(self, input_path: Path, output_path: Optional[Path] = None) -> str:
        """
        Expand vocabulary references in a file.

        Args:
            input_path: Path to input file containing vocab references
            output_path: Optional path to write expanded output

        Returns:
            Expanded text

        Raises:
            ExpansionError: If expansion fails
            FileNotFoundError: If input file doesn't exist
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Read input
        text = input_path.read_text()

        # Expand
        expanded = self.expand_text(text)

        # Write output if requested
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(expanded)

        return expanded

    def _prepare_parameters(
        self,
        entry: VocabEntry,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and prepare parameters for expansion.

        Args:
            entry: Vocabulary entry
            params: User-provided parameters

        Returns:
            Prepared parameters with defaults applied

        Raises:
            ExpansionError: If validation fails
        """
        prepared = {}

        # Check for required parameters and apply defaults
        for param_def in entry.parameters:
            if param_def.name in params:
                # User provided value - validate type
                value = params[param_def.name]
                validated = self._validate_param_value(param_def, value)
                prepared[param_def.name] = validated
            elif param_def.required:
                # Required but not provided
                raise ExpansionError(
                    f"Missing required parameter '{param_def.name}' for entry '{entry.id}'"
                )
            elif param_def.default is not None:
                # Use default value
                prepared[param_def.name] = param_def.default

        # Check for unknown parameters
        known_params = {p.name for p in entry.parameters}
        unknown = set(params.keys()) - known_params
        if unknown:
            raise ExpansionError(
                f"Unknown parameters for entry '{entry.id}': {', '.join(sorted(unknown))}"
            )

        return prepared

    def _validate_param_value(
        self,
        param_def: VocabParameter,
        value: Any
    ) -> Any:
        """
        Validate parameter value against definition.

        Args:
            param_def: Parameter definition
            value: Value to validate

        Returns:
            Validated value (possibly coerced)

        Raises:
            ExpansionError: If validation fails
        """
        # Type validation (basic - can be enhanced)
        if param_def.type == 'string':
            if not isinstance(value, str):
                raise ExpansionError(
                    f"Parameter '{param_def.name}' must be a string, got {type(value).__name__}"
                )
        elif param_def.type == 'boolean':
            if not isinstance(value, bool):
                # Try to coerce
                if isinstance(value, str):
                    if value.lower() in ('true', 'yes', '1'):
                        value = True
                    elif value.lower() in ('false', 'no', '0'):
                        value = False
                    else:
                        raise ExpansionError(
                            f"Parameter '{param_def.name}' must be a boolean"
                        )
        elif param_def.type == 'number':
            if not isinstance(value, (int, float)):
                # Try to coerce
                try:
                    value = float(value) if '.' in str(value) else int(value)
                except (ValueError, TypeError):
                    raise ExpansionError(
                        f"Parameter '{param_def.name}' must be a number"
                    )
        elif param_def.type == 'list':
            if not isinstance(value, list):
                raise ExpansionError(
                    f"Parameter '{param_def.name}' must be a list"
                )
        elif param_def.type == 'dict':
            if not isinstance(value, dict):
                raise ExpansionError(
                    f"Parameter '{param_def.name}' must be a dict"
                )
        # model_ref is just a string - no special validation needed

        return value

    def _parse_params(self, params_str: str) -> Dict[str, Any]:
        """
        Parse parameter string from @use directive.

        Supports:
        - Simple key=value pairs
        - Quoted strings
        - Numbers and booleans
        - Lists (comma-separated in brackets)

        Examples:
            source_entity=User
            title="My Title", required=true
            items=[1, 2, 3]

        Args:
            params_str: Parameter string

        Returns:
            Dictionary of parameters

        Raises:
            ExpansionError: If parsing fails
        """
        if not params_str.strip():
            return {}

        params = {}

        # Split by comma (but not inside quotes or brackets)
        parts = self._split_params(params_str)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # Split by = (but not inside quotes or brackets)
            if '=' not in part:
                raise ExpansionError(f"Invalid parameter syntax: '{part}' (expected key=value)")

            key, value = part.split('=', 1)
            key = key.strip()
            value = value.strip()

            # Validate key
            if not re.match(r'^[a-z_][a-z0-9_]*$', key):
                raise ExpansionError(f"Invalid parameter name: '{key}'")

            # Parse value
            params[key] = self._parse_value(value)

        return params

    def _split_params(self, params_str: str) -> List[str]:
        """Split parameter string by commas (respecting quotes and brackets)."""
        parts = []
        current = []
        depth = 0  # Track bracket/paren depth
        in_quotes = False
        quote_char = None

        for char in params_str:
            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
                current.append(char)
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current.append(char)
            elif char in ('[', '(') and not in_quotes:
                depth += 1
                current.append(char)
            elif char in (']', ')') and not in_quotes:
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0 and not in_quotes:
                parts.append(''.join(current))
                current = []
            else:
                current.append(char)

        if current:
            parts.append(''.join(current))

        return parts

    def _parse_value(self, value: str) -> Any:
        """Parse a parameter value."""
        value = value.strip()

        # Boolean
        if value.lower() in ('true', 'yes'):
            return True
        if value.lower() in ('false', 'no'):
            return False

        # Quoted string
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            return value[1:-1]

        # List
        if value.startswith('[') and value.endswith(']'):
            items_str = value[1:-1].strip()
            if not items_str:
                return []
            items = [self._parse_value(item.strip()) for item in items_str.split(',')]
            return items

        # Number
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # Plain string (unquoted)
        return value


def expand_vocab_in_file(
    input_path: Path,
    manifest_path: Path,
    output_path: Optional[Path] = None
) -> str:
    """
    Convenience function to expand vocabulary in a file.

    Args:
        input_path: Path to input DSL file
        manifest_path: Path to vocabulary manifest
        output_path: Optional path to write output

    Returns:
        Expanded DSL text

    Raises:
        ExpansionError: If expansion fails
        FileNotFoundError: If files don't exist
    """
    from .vocab import load_manifest

    # Load manifest
    manifest = load_manifest(manifest_path)

    # Create expander
    expander = VocabExpander(manifest)

    # Expand file
    return expander.expand_file(input_path, output_path)
