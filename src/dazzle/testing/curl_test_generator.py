"""
Curl/Bash Smoke Test Generator

Generates a self-contained bash script that tests a running Dazzle app using
only curl and jq. Useful for CI pipelines, ops smoke tests, and quick manual
verification without Python dependencies.

Usage:
    generator = CurlTestGenerator(appspec)
    script = generator.generate()  # all suites
    script = generator.generate(suites=["smoke", "crud"])  # specific suites
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from dazzle.core.ir import AppSpec
from dazzle.core.ir.fields import FieldSpec, FieldTypeKind
from dazzle.core.strings import to_api_plural

logger = logging.getLogger(__name__)

ALL_SUITES = ["smoke", "auth", "crud", "validation", "state", "security", "persona"]


class CurlTestGenerator:
    """Generate a bash/curl smoke test script from an AppSpec."""

    def __init__(
        self,
        appspec: AppSpec,
        base_url: str = "http://localhost:8000",
        project_root: Path | None = None,
    ):
        self.appspec = appspec
        self.base_url = base_url
        self.project_root = project_root
        self._entity_map: dict[str, Any] = {e.name: e for e in appspec.domain.entities}
        self._dependency_order = self._build_dependency_order()

    def _build_dependency_order(self) -> list[str]:
        """Topological sort of entities by ref dependencies."""
        deps: dict[str, list[str]] = {}
        for entity in self.appspec.domain.entities:
            entity_deps: list[str] = []
            for fld in entity.fields:
                if fld.type.kind == FieldTypeKind.REF and fld.is_required:
                    target = fld.type.ref_entity
                    if target and target in self._entity_map:
                        entity_deps.append(target)
            deps[entity.name] = entity_deps

        # Build adjacency: if A depends on B, then B -> A (B must come first)
        adj: dict[str, list[str]] = {name: [] for name in deps}
        in_deg: dict[str, int] = dict.fromkeys(deps, 0)
        for name, dep_list in deps.items():
            for dep in dep_list:
                if dep in adj:
                    adj[dep].append(name)
                    in_deg[name] += 1

        queue = [name for name, deg in in_deg.items() if deg == 0]
        order: list[str] = []
        while queue:
            queue.sort()  # deterministic
            node = queue.pop(0)
            order.append(node)
            for neighbor in adj.get(node, []):
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0:
                    queue.append(neighbor)

        # Append any remaining (cycles) at the end
        for name in deps:
            if name not in order:
                order.append(name)

        return order

    def generate(self, suites: list[str] | None = None) -> str:
        """Generate the complete bash smoke test script."""
        selected = suites or ALL_SUITES
        parts: list[str] = []
        parts.append(self._script_header())
        parts.append(self._helper_functions())

        suite_methods = {
            "smoke": self._smoke_tests,
            "auth": self._auth_tests,
            "crud": self._crud_tests,
            "validation": self._validation_tests,
            "state": self._state_machine_tests,
            "security": self._security_tests,
            "persona": self._persona_tests,
        }

        for suite_name in ALL_SUITES:
            if suite_name in selected:
                method = suite_methods.get(suite_name)
                if method:
                    content = method()
                    if content:
                        parts.append(content)

        parts.append(self._suite_runner(selected))
        parts.append(self._script_footer())

        return "\n".join(parts)

    # =========================================================================
    # Script structure
    # =========================================================================

    def _script_header(self) -> str:
        return f"""#!/usr/bin/env bash
# Auto-generated smoke test for {self.appspec.name}
# Generated at {datetime.now().isoformat()}
# Usage: bash smoke_test.sh [base_url] [suite]
#   suite: {"|".join(ALL_SUITES)}|all (default: all)
set -euo pipefail

# Colors
GREEN="\\033[0;32m"
RED="\\033[0;31m"
YELLOW="\\033[0;33m"
NC="\\033[0m"

# Configuration
BASE_URL="${{1:-{self.base_url}}}"
SUITE="${{2:-all}}"

# Counters
PASS=0
FAIL=0
SKIP=0
"""

    def _helper_functions(self) -> str:
        return r"""# =========================================================================
# Helper functions
# =========================================================================

assert_status() {
  local label="$1"
  local method="$2"
  local url="$3"
  local expected="$4"
  local data="${5:-}"
  local auth="${6:-}"

  local curl_args=(-s -o /tmp/dazzle_response -w "%{http_code}" -X "$method")
  curl_args+=(-H "Content-Type: application/json")

  if [ -n "$auth" ]; then
    curl_args+=(-H "Authorization: Bearer $auth")
  fi

  if [ -n "$data" ]; then
    curl_args+=(-d "$data")
  fi

  local status
  status=$(curl "${curl_args[@]}" "$url" 2>/dev/null) || status="000"

  if [ "$status" = "$expected" ]; then
    echo -e "  ${GREEN}PASS${NC} $label (HTTP $status)"
    PASS=$((PASS + 1))
  else
    echo -e "  ${RED}FAIL${NC} $label (expected $expected, got $status)"
    if [ -f /tmp/dazzle_response ]; then
      echo "       Response: $(head -c 200 /tmp/dazzle_response)"
    fi
    FAIL=$((FAIL + 1))
  fi
}

extract_json() {
  local jq_path="$1"
  if command -v jq &>/dev/null && [ -f /tmp/dazzle_response ]; then
    jq -r "$jq_path" /tmp/dazzle_response 2>/dev/null || echo ""
  else
    echo ""
  fi
}

section_header() {
  local name="$1"
  echo ""
  echo -e "${YELLOW}━━━ $name ━━━${NC}"
}

report() {
  echo ""
  echo "==========================================="
  echo -e "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$SKIP skipped${NC}"
  echo "==========================================="
  if [ "$FAIL" -gt 0 ]; then
    exit 1
  fi
  exit 0
}
"""

    def _script_footer(self) -> str:
        return """# =========================================================================
# Cleanup
# =========================================================================
cleanup() {
  rm -f /tmp/dazzle_response
  # Reset test data if endpoint available
  curl -s -X POST "${BASE_URL}/__test__/reset" -H "Content-Type: application/json" &>/dev/null || true
}
trap cleanup EXIT

# Run
run_suites
report
"""

    # =========================================================================
    # Suite: smoke
    # =========================================================================

    def _smoke_tests(self) -> str:
        lines = [
            "suite_smoke() {",
            '  section_header "Smoke Tests"',
            '  assert_status "Health check" GET "${BASE_URL}/health" 200',
        ]

        # SiteSpec public pages (loaded separately from appspec)
        if self.project_root:
            try:
                from dazzle.core.sitespec_loader import load_sitespec

                sitespec = load_sitespec(self.project_root)
                for route in sitespec.get_all_routes():
                    label = f"Page {route}"
                    lines.append(f'  assert_status "{label}" GET "${{BASE_URL}}{route}" 200')
            except Exception:
                logger.debug("Optional sitespec not available for curl tests", exc_info=True)

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite: auth
    # =========================================================================

    def _auth_tests(self) -> str:
        personas = self.appspec.personas
        if not personas:
            return ""

        lines = [
            "suite_auth() {",
            '  section_header "Auth Tests"',
        ]

        for persona in personas:
            pid = persona.id
            var_name = f"TOKEN_{pid.upper()}"
            data = json.dumps({"role": pid, "username": f"test_{pid}"})
            lines.append(
                f'  assert_status "Authenticate as {pid}" POST "${{BASE_URL}}/__test__/authenticate" 200 \'{data}\''
            )
            lines.append(f'  {var_name}=$(extract_json ".token")')
            lines.append(f'  if [ -z "${var_name}" ]; then')
            lines.append(f'    echo -e "  ${{YELLOW}}SKIP${{NC}} No token for {pid}"')
            lines.append("    SKIP=$((SKIP + 1))")
            lines.append("  fi")

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite: crud
    # =========================================================================

    def _crud_tests(self) -> str:
        lines = [
            "suite_crud() {",
            '  section_header "CRUD Tests"',
        ]

        for entity_name in self._dependency_order:
            entity = self._entity_map[entity_name]
            plural = to_api_plural(entity_name)
            id_var = f"ID_{entity_name.upper()}"
            create_data = self._generate_create_payload(entity)
            update_data = self._generate_update_payload(entity)

            # Create
            lines.append(
                f'  assert_status "Create {entity_name}" POST "${{BASE_URL}}/api/{plural}" 201 \'{create_data}\''
            )
            lines.append(f'  {id_var}=$(extract_json ".id")')

            # List
            lines.append(
                f'  assert_status "List {entity_name}" GET "${{BASE_URL}}/api/{plural}" 200'
            )

            # Get by ID
            lines.append(f'  if [ -n "${id_var}" ]; then')
            lines.append(
                f'    assert_status "Get {entity_name}" GET "${{BASE_URL}}/api/{plural}/${id_var}" 200'
            )

            # Update
            if update_data:
                lines.append(
                    f'    assert_status "Update {entity_name}" PUT "${{BASE_URL}}/api/{plural}/${id_var}" 200 \'{update_data}\''
                )

            # Delete
            lines.append(
                f'    assert_status "Delete {entity_name}" DELETE "${{BASE_URL}}/api/{plural}/${id_var}" 200'
            )
            lines.append("  fi")

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite: validation
    # =========================================================================

    def _validation_tests(self) -> str:
        lines = [
            "suite_validation() {",
            '  section_header "Validation Tests"',
        ]

        for entity in self.appspec.domain.entities:
            required_fields = [
                f
                for f in entity.fields
                if f.is_required and f.name not in ("id", "created_at", "updated_at")
            ]
            if required_fields:
                plural = to_api_plural(entity.name)
                lines.append(
                    f'  assert_status "Reject empty {entity.name}" POST "${{BASE_URL}}/api/{plural}" 422 \'{{}}\''
                )

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite: state
    # =========================================================================

    def _state_machine_tests(self) -> str:
        has_sm = any(e.state_machine for e in self.appspec.domain.entities)
        if not has_sm:
            return ""

        lines = [
            "suite_state() {",
            '  section_header "State Machine Tests"',
        ]

        for entity in self.appspec.domain.entities:
            sm = entity.state_machine
            if not sm:
                continue

            plural = to_api_plural(entity.name)
            create_data = self._generate_create_payload(entity)

            # Create entity, then test first valid transition
            if sm.transitions:
                trans = sm.transitions[0]
                lines.append(f"  # {entity.name}: {trans.from_state} -> {trans.to_state}")
                lines.append(
                    f'  assert_status "Create {entity.name} for state test" POST "${{BASE_URL}}/api/{plural}" 201 \'{create_data}\''
                )
                lines.append('  SM_ID=$(extract_json ".id")')
                lines.append('  if [ -n "$SM_ID" ]; then')
                transition_data = json.dumps({"status": trans.to_state})
                lines.append(
                    f'    assert_status "{entity.name}: {trans.from_state} -> {trans.to_state}" POST "${{BASE_URL}}/api/{plural}/$SM_ID/transition" 200 \'{transition_data}\''
                )
                lines.append("  fi")

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite: security
    # =========================================================================

    def _security_tests(self) -> str:
        lines = [
            "suite_security() {",
            '  section_header "Security Tests"',
        ]

        for entity in self.appspec.domain.entities:
            plural = to_api_plural(entity.name)
            lines.append(
                f'  assert_status "Unauthenticated {entity.name} list" GET "${{BASE_URL}}/api/{plural}" 401'
            )

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite: persona
    # =========================================================================

    def _persona_tests(self) -> str:
        personas = self.appspec.personas
        if not personas:
            return ""

        lines = [
            "suite_persona() {",
            '  section_header "Persona Tests"',
        ]

        for persona in personas:
            pid = persona.id
            token_var = f"TOKEN_{pid.upper()}"

            # Auth
            data = json.dumps({"role": pid, "username": f"test_{pid}"})
            lines.append(f"  # Authenticate as {pid}")
            lines.append(
                f'  assert_status "Persona auth: {pid}" POST "${{BASE_URL}}/__test__/authenticate" 200 \'{data}\''
            )
            lines.append(f'  {token_var}=$(extract_json ".token")')

            # List endpoints with token
            for entity in self.appspec.domain.entities:
                plural = to_api_plural(entity.name)
                lines.append(
                    f'  assert_status "{pid}: list {entity.name}" GET "${{BASE_URL}}/api/{plural}" 200 "" "${token_var}"'
                )

        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Suite runner
    # =========================================================================

    def _suite_runner(self, selected: list[str]) -> str:
        lines = ["run_suites() {", '  case "$SUITE" in']

        for suite_name in ALL_SUITES:
            if suite_name in selected:
                lines.append(f"    {suite_name})")
                lines.append(f"      suite_{suite_name}")
                lines.append("      ;;")

        # all) runs all selected suites
        all_calls = "\n".join(f"      suite_{s}" for s in ALL_SUITES if s in selected)
        lines.append("    all)")
        lines.append(all_calls)
        lines.append("      ;;")

        lines.append("    *)")
        lines.append('      echo "Unknown suite: $SUITE"')
        lines.append(f'      echo "Available: {"|".join(ALL_SUITES)}|all"')
        lines.append("      exit 1")
        lines.append("      ;;")

        lines.append("  esac")
        lines.append("}")
        lines.append("")
        return "\n".join(lines)

    # =========================================================================
    # Field value generation
    # =========================================================================

    def _generate_field_value(self, field: FieldSpec) -> str:
        """Generate a bash-compatible JSON value string for a field."""
        kind = field.type.kind
        name = field.name

        if kind == FieldTypeKind.ENUM:
            if field.type.enum_values:
                return json.dumps(field.type.enum_values[0])
            return '"default"'

        if kind == FieldTypeKind.REF:
            # Use shell variable reference
            target = field.type.ref_entity or "Unknown"
            return f'"${{ID_{target.upper()}}}"'

        if kind == FieldTypeKind.MONEY:
            # Money fields expand to _minor + _currency per #131
            # Handled specially in _generate_create_payload
            return "10000"

        if kind == FieldTypeKind.UUID:
            return '"$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo test-uuid)"'

        if name == "email" or kind == FieldTypeKind.EMAIL:
            return '"test@example.com"'

        if kind == FieldTypeKind.STR:
            return json.dumps(f"Test {name}")
        if kind == FieldTypeKind.TEXT:
            return json.dumps(f"Test description for {name}")
        if kind == FieldTypeKind.INT:
            return "1"
        if kind == FieldTypeKind.DECIMAL:
            return "10.0"
        if kind == FieldTypeKind.BOOL:
            return "true"
        if kind == FieldTypeKind.DATE:
            return json.dumps(datetime.now().strftime("%Y-%m-%d"))
        if kind == FieldTypeKind.DATETIME:
            return json.dumps(datetime.now().isoformat())
        if kind == FieldTypeKind.URL:
            return json.dumps(f"https://example.com/{name}")
        if kind == FieldTypeKind.FILE:
            return '"test_file.txt"'
        if kind == FieldTypeKind.JSON:
            return '{"key": "value"}'

        return json.dumps(f"test_{name}")

    def _generate_create_payload(self, entity: Any) -> str:
        """Generate JSON payload string for creating an entity."""
        parts: list[str] = []

        for fld in entity.fields:
            if fld.name in ("id", "created_at", "updated_at"):
                continue
            if not fld.is_required:
                continue

            if fld.type.kind == FieldTypeKind.MONEY:
                # Money expansion: _minor (int) + _currency (str)
                currency = fld.type.currency_code or "USD"
                parts.append(f'"{fld.name}_minor": 10000')
                parts.append(f'"{fld.name}_currency": {json.dumps(currency)}')
            else:
                val = self._generate_field_value(fld)
                parts.append(f'"{fld.name}": {val}')

        return "{" + ", ".join(parts) + "}"

    def _generate_update_payload(self, entity: Any) -> str:
        """Generate JSON payload for updating an entity (first mutable string field)."""
        for fld in entity.fields:
            if fld.name in ("id", "created_at", "updated_at"):
                continue
            if fld.type.kind == FieldTypeKind.STR:
                return "{" + f'"{fld.name}": "Updated value"' + "}"
            if fld.type.kind == FieldTypeKind.TEXT:
                return "{" + f'"{fld.name}": "Updated description"' + "}"
        return ""
