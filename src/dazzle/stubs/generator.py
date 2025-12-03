"""
Stub Generator for DAZZLE Domain Services.

Generates service stub files from DomainServiceSpec. Stubs are the ONLY
location where Turing-complete logic may exist in a Dazzle application.

Key features:
- Generate Python or TypeScript stubs
- Regenerate headers while preserving implementation bodies
- Type-safe contracts matching DSL declarations
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.stubs.models import DomainServiceSpec

# Markers for header/body separation
HEADER_START = "# === AUTO-GENERATED HEADER ================================================"
HEADER_END = "# =========================================================================="
IMPL_MARKER = '"""'  # Start of implementation docstring


class StubGenerator:
    """
    Generate service stub files from DomainServiceSpec.

    The generator creates stub files with:
    1. Auto-generated header (service metadata, regenerated on changes)
    2. Type definitions (TypedDict for outputs)
    3. Function signature (from input contract)
    4. Implementation body (preserved across regenerations)
    """

    # Type mappings from DSL to Python
    DSL_TO_PYTHON_TYPES: dict[str, str] = {
        "uuid": "str",
        "str": "str",
        "text": "str",
        "int": "int",
        "decimal": "float",
        "money": "float",
        "bool": "bool",
        "date": "str",  # ISO format
        "datetime": "str",  # ISO format
        "json": "dict",
        "email": "str",
    }

    # Type mappings from DSL to TypeScript
    DSL_TO_TS_TYPES: dict[str, str] = {
        "uuid": "string",
        "str": "string",
        "text": "string",
        "int": "number",
        "decimal": "number",
        "money": "number",
        "bool": "boolean",
        "date": "string",
        "datetime": "string",
        "json": "Record<string, unknown>",
        "email": "string",
    }

    def generate_stub(self, service: DomainServiceSpec, language: str = "python") -> str:
        """
        Generate complete stub file content.

        Args:
            service: The domain service specification
            language: Target language ('python' or 'typescript')

        Returns:
            Complete stub file content
        """
        if language == "python":
            return self._generate_python_stub(service)
        elif language == "typescript":
            return self._generate_typescript_stub(service)
        else:
            raise ValueError(f"Unsupported language: {language}")

    def update_stub(self, service: DomainServiceSpec, existing_path: Path) -> str:
        """
        Regenerate header while preserving implementation body.

        Args:
            service: The domain service specification
            existing_path: Path to existing stub file

        Returns:
            Updated stub file content
        """
        existing_content = existing_path.read_text()
        language = "typescript" if existing_path.suffix == ".ts" else "python"

        # Find where implementation begins
        impl_start = self._detect_implementation_marker(existing_content)

        if impl_start < 0:
            # No implementation found, generate fresh
            return self.generate_stub(service, language)

        # Extract existing implementation
        existing_impl = existing_content[impl_start:]

        # Generate new header
        if language == "python":
            new_header = self._generate_python_header(service)
            new_header += self._generate_python_types(service)
            new_header += self._generate_python_signature(service)
        else:
            new_header = self._generate_typescript_header(service)
            new_header += self._generate_typescript_types(service)
            new_header += self._generate_typescript_signature(service)

        return new_header + existing_impl

    def _detect_implementation_marker(self, content: str) -> int:
        """
        Find where header ends and implementation begins.

        The implementation section starts after the function signature,
        marked by the docstring.

        Returns:
            Index of implementation start, or -1 if not found
        """
        # Look for the implementation docstring after the function signature
        # Pattern: def function_name(...) -> ReturnType:\n    """
        pattern = r'def \w+\([^)]*\)[^:]*:\s*\n\s*"""'
        match = re.search(pattern, content)
        if match:
            # Return position of the docstring
            docstring_match = content.find('"""', match.start())
            if docstring_match >= 0:
                return docstring_match
        return -1

    def _generate_python_stub(self, service: DomainServiceSpec) -> str:
        """Generate complete Python stub."""
        parts = [
            self._generate_python_header(service),
            self._generate_python_types(service),
            self._generate_python_signature(service),
            self._generate_python_impl_body(service),
        ]
        return "".join(parts)

    def _generate_python_header(self, service: DomainServiceSpec) -> str:
        """Generate Python stub header."""
        lines = [
            HEADER_START,
            f"# Service ID: {service.id}",
            f"# Kind: {service.kind.value}",
        ]

        if service.title:
            lines.append(f"# Description: {service.title}")

        if service.inputs:
            lines.append("# Input:")
            for field in service.inputs:
                req = " (required)" if field.required else " (optional)"
                lines.append(f"#   - {field.name}: {field.type_name}{req}")

        if service.outputs:
            lines.append("# Output:")
            for field in service.outputs:
                lines.append(f"#   - {field.name}: {field.type_name}")

        if service.guarantees:
            lines.append("# Guarantees:")
            for guarantee in service.guarantees:
                lines.append(f"#   - {guarantee}")

        lines.append(HEADER_END)
        lines.append("")

        return "\n".join(lines) + "\n"

    def _generate_python_types(self, service: DomainServiceSpec) -> str:
        """Generate Python type definitions."""
        lines = ["from typing import TypedDict", ""]

        if service.outputs:
            lines.append(f"class {service.result_type_name()}(TypedDict):")
            for field in service.outputs:
                py_type = self._dsl_to_python_type(field.type_name)
                lines.append(f"    {field.name}: {py_type}")
            lines.append("")

        return "\n".join(lines) + "\n"

    def _generate_python_signature(self, service: DomainServiceSpec) -> str:
        """Generate Python function signature."""
        # Build parameter list
        params = []
        for field in service.inputs:
            py_type = self._dsl_to_python_type(field.type_name)
            params.append(f"{field.name}: {py_type}")

        param_str = ", ".join(params) if params else ""

        # Return type
        return_type = service.result_type_name() if service.outputs else "None"

        return f"def {service.python_function_name()}({param_str}) -> {return_type}:\n"

    def _generate_python_impl_body(self, service: DomainServiceSpec) -> str:
        """Generate Python implementation body (placeholder)."""
        lines = [
            '    """',
            "    IMPLEMENTATION SECTION - Edit below this line.",
            "    The header above will be regenerated; this body will NOT be overwritten.",
            '    """',
            '    raise NotImplementedError("Implement this service")',
            "",
        ]
        return "\n".join(lines)

    def _generate_typescript_stub(self, service: DomainServiceSpec) -> str:
        """Generate complete TypeScript stub."""
        parts = [
            self._generate_typescript_header(service),
            self._generate_typescript_types(service),
            self._generate_typescript_signature(service),
            self._generate_typescript_impl_body(service),
        ]
        return "".join(parts)

    def _generate_typescript_header(self, service: DomainServiceSpec) -> str:
        """Generate TypeScript stub header."""
        lines = [
            "// === AUTO-GENERATED HEADER ================================================",
            f"// Service ID: {service.id}",
            f"// Kind: {service.kind.value}",
        ]

        if service.title:
            lines.append(f"// Description: {service.title}")

        if service.inputs:
            lines.append("// Input:")
            for field in service.inputs:
                req = " (required)" if field.required else " (optional)"
                lines.append(f"//   - {field.name}: {field.type_name}{req}")

        if service.outputs:
            lines.append("// Output:")
            for field in service.outputs:
                lines.append(f"//   - {field.name}: {field.type_name}")

        if service.guarantees:
            lines.append("// Guarantees:")
            for guarantee in service.guarantees:
                lines.append(f"//   - {guarantee}")

        lines.append(
            "// =========================================================================="
        )
        lines.append("")

        return "\n".join(lines) + "\n"

    def _generate_typescript_types(self, service: DomainServiceSpec) -> str:
        """Generate TypeScript type definitions."""
        lines = []

        if service.outputs:
            lines.append(f"export interface {service.result_type_name()} {{")
            for field in service.outputs:
                ts_type = self._dsl_to_typescript_type(field.type_name)
                lines.append(f"  {field.name}: {ts_type};")
            lines.append("}")
            lines.append("")

        return "\n".join(lines) + "\n" if lines else ""

    def _generate_typescript_signature(self, service: DomainServiceSpec) -> str:
        """Generate TypeScript function signature."""
        # Build parameter list
        params = []
        for field in service.inputs:
            ts_type = self._dsl_to_typescript_type(field.type_name)
            optional = "" if field.required else "?"
            params.append(f"{field.name}{optional}: {ts_type}")

        param_str = ", ".join(params) if params else ""

        # Return type
        return_type = service.result_type_name() if service.outputs else "void"

        return (
            f"export async function {service.python_function_name()}"
            f"({param_str}): Promise<{return_type}> {{\n"
        )

    def _generate_typescript_impl_body(self, service: DomainServiceSpec) -> str:
        """Generate TypeScript implementation body (placeholder)."""
        lines = [
            "  /**",
            "   * IMPLEMENTATION SECTION - Edit below this line.",
            "   * The header above will be regenerated; this body will NOT be overwritten.",
            "   */",
            '  throw new Error("Not implemented");',
            "}",
            "",
        ]
        return "\n".join(lines)

    def _dsl_to_python_type(self, dsl_type: str) -> str:
        """Convert DSL type to Python type annotation."""
        # Handle parameterized types like str(200), decimal(10,2)
        base_type = dsl_type.split("(")[0].lower()
        return self.DSL_TO_PYTHON_TYPES.get(base_type, "Any")

    def _dsl_to_typescript_type(self, dsl_type: str) -> str:
        """Convert DSL type to TypeScript type annotation."""
        base_type = dsl_type.split("(")[0].lower()
        return self.DSL_TO_TS_TYPES.get(base_type, "unknown")


def generate_stub_file(
    service: DomainServiceSpec,
    output_dir: Path,
    language: str = "python",
    overwrite: bool = False,
) -> Path:
    """
    Generate a stub file for a domain service.

    Args:
        service: The domain service specification
        output_dir: Directory to write the stub file
        language: Target language ('python' or 'typescript')
        overwrite: If True, overwrite existing files; if False, preserve impl

    Returns:
        Path to the generated stub file
    """
    generator = StubGenerator()
    ext = ".ts" if language == "typescript" else ".py"
    stub_path = output_dir / f"{service.id}{ext}"

    if stub_path.exists() and not overwrite:
        # Update header, preserve implementation
        content = generator.update_stub(service, stub_path)
    else:
        # Generate fresh stub
        content = generator.generate_stub(service, language)

    stub_path.write_text(content)
    return stub_path
