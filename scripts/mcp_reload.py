#!/usr/bin/env python3
"""
MCP Development Helper Script

Quick commands for MCP development:
- Check semantic index version
- Test concept lookups
- Verify changes without restarting server

Usage:
    python scripts/mcp_reload.py version     # Show current version
    python scripts/mcp_reload.py lookup <term>  # Test concept lookup
    python scripts/mcp_reload.py check       # Verify all expected concepts exist
"""

import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def show_version():
    """Show current MCP semantic index version."""
    from dazzle.mcp.semantics import get_mcp_version

    info = get_mcp_version()
    print(f"MCP Semantics Version: {info['full_version']}")
    print(f"  Version: {info['version']}")
    print(f"  Build: {info['build']}")


def lookup_term(term: str):
    """Test looking up a concept."""
    from dazzle.mcp.semantics import lookup_concept
    import json

    result = lookup_concept(term)
    print(json.dumps(result, indent=2))


def check_concepts():
    """Verify all expected concepts are found."""
    from dazzle.mcp.semantics import lookup_concept

    # Core concepts that should always exist
    expected_concepts = [
        # Core constructs
        "entity",
        "surface",
        "workspace",
        "persona",
        # UX layer
        "ux_block",
        "attention_signals",
        "scope",
        # Type system
        "field_types",
        "relationships",
        # Business logic (v0.7)
        "transitions",  # alias for state_machine
        "access",  # alias for access_rules
        "invariant",
        "computed",  # alias for computed_field
        # Layout (v0.8)
        "stage",
        # Entity features
        "index",
        "section",
        # UX features
        "defaults",
    ]

    print("Checking expected MCP concepts...")
    print("-" * 50)

    all_found = True
    for term in expected_concepts:
        result = lookup_concept(term)
        found = result.get("found", False)
        status = "✓" if found else "✗"
        if not found:
            all_found = False
        category = result.get("category", "N/A") if found else "NOT FOUND"
        print(f"  {status} {term:20} - {category}")

    print("-" * 50)
    if all_found:
        print("✓ All concepts found!")
    else:
        print("✗ Some concepts missing - check semantics.py")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "version":
        show_version()
    elif command == "lookup":
        if len(sys.argv) < 3:
            print("Usage: mcp_reload.py lookup <term>")
            sys.exit(1)
        lookup_term(sys.argv[2])
    elif command == "check":
        check_concepts()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
