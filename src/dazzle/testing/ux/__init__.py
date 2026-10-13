"""DAZZLE UX Verification — deterministic interaction testing derived from the DSL.

Usage:
    from dazzle.testing.ux.inventory import generate_inventory
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(Path("examples/simple_task"))
    inventory = generate_inventory(appspec)
"""
