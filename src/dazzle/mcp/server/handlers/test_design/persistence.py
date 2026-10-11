"""Test design save/load handlers."""

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.ir.test_design import (
    TestDesignAction,
    TestDesignSpec,
    TestDesignStatus,
    TestDesignStep,
    TestDesignTrigger,
)

from ..common import error_response, extract_progress, wrap_handler_errors
from .proposals import _parse_test_design_action, _parse_test_design_trigger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Impl function (no MCP types, explicit params, returns plain dict)
# ---------------------------------------------------------------------------


def test_design_save_impl(
    project_root: Path,
    *,
    designs_data: list[dict[str, Any]],
    overwrite: bool = False,
) -> dict[str, Any]:
    """Save test designs to dsl/tests/designs.json."""
    from dazzle.testing.test_design_persistence import add_test_designs, get_dsl_tests_dir

    designs: list[TestDesignSpec] = []
    for d in designs_data:
        steps = []
        for s in d.get("steps", []):
            steps.append(
                TestDesignStep(
                    action=_parse_test_design_action(s["action"])
                    if s.get("action")
                    else TestDesignAction.CLICK,
                    target=s.get("target", ""),
                    data=s.get("data"),
                    rationale=s.get("rationale"),
                )
            )

        designs.append(
            TestDesignSpec(
                test_id=d["test_id"],
                title=d["title"],
                description=d.get("description"),
                persona=d.get("persona"),
                scenario=d.get("scenario"),
                trigger=_parse_test_design_trigger(d["trigger"])
                if d.get("trigger")
                else TestDesignTrigger.USER_CLICK,
                steps=steps,
                expected_outcomes=d.get("expected_outcomes", []),
                entities=d.get("entities", []),
                surfaces=d.get("surfaces", []),
                tags=d.get("tags", []),
                status=TestDesignStatus(d.get("status", "proposed")),
                notes=d.get("notes"),
            )
        )

    result = add_test_designs(project_root, designs, overwrite=overwrite, to_dsl=True)
    designs_file = get_dsl_tests_dir(project_root) / "designs.json"

    response: dict[str, Any] = {
        "status": "saved",
        "saved_count": result.added_count,
        "total_count": len(result.all_designs),
        "file": str(designs_file),
        "overwrite": overwrite,
    }

    if result.remapped_ids:
        response["remapped_ids"] = result.remapped_ids
        response["warning"] = (
            f"{len(result.remapped_ids)} design(s) had colliding IDs and were "
            "auto-assigned new unique IDs. See remapped_ids for details."
        )

    return response


@wrap_handler_errors
def save_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save test designs to dsl/tests/designs.json."""
    progress = extract_progress(args)

    designs_data = args.get("designs", [])
    if not designs_data:
        return error_response("No designs provided")

    progress.log_sync("Saving test designs...")
    result = test_design_save_impl(
        project_root,
        designs_data=designs_data,
        overwrite=args.get("overwrite", False),
    )
    return json.dumps(result, indent=2)
