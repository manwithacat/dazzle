"""DAZZLE UX Verification — deterministic interaction testing derived from the DSL.

Usage:
    from dazzle.testing.ux import generate_inventory, generate_report
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(Path("examples/simple_task"))
    inventory = generate_inventory(appspec)
"""

from dazzle.testing.ux.baseline import Baseline, compare_results
from dazzle.testing.ux.contracts import Contract, ContractKind, generate_contracts
from dazzle.testing.ux.inventory import (
    Interaction,
    InteractionClass,
    generate_inventory,
)
from dazzle.testing.ux.report import UXReport, generate_report
from dazzle.testing.ux.structural import (
    StructuralResult,
    check_detail_view,
    check_form,
    check_html,
)

__all__ = [
    "Baseline",
    "Contract",
    "ContractKind",
    "Interaction",
    "InteractionClass",
    "StructuralResult",
    "UXReport",
    "check_detail_view",
    "check_form",
    "check_html",
    "compare_results",
    "generate_contracts",
    "generate_inventory",
    "generate_report",
]
