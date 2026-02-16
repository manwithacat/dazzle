"""Test design save/load handlers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..common import extract_progress, handler_error_json
from ..serializers import serialize_test_design, serialize_test_design_summary
from .proposals import _parse_test_design_action, _parse_test_design_trigger

logger = logging.getLogger("dazzle.mcp")


@handler_error_json
def save_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save test designs to dsl/tests/designs.json."""
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.testing.test_design_persistence import add_test_designs, get_dsl_tests_dir

    progress = extract_progress(args)

    designs_data = args.get("designs", [])
    overwrite = args.get("overwrite", False)

    if not designs_data:
        return json.dumps({"error": "No designs provided"})

    progress.log_sync("Saving test designs...")
    # Convert dict data to TestDesignSpec objects
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

    # Save designs
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

    return json.dumps(response, indent=2)


@handler_error_json
def get_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve test designs from storage.

    Returns compact summaries by default. When ``test_ids`` is provided,
    returns full content for those specific designs only.
    """
    from dazzle.core.ir.test_design import TestDesignStatus
    from dazzle.testing.test_design_persistence import (
        get_dsl_tests_dir,
        get_test_designs_by_status,
    )

    progress = extract_progress(args)

    status_filter = args.get("status_filter")
    test_ids = args.get("test_ids")

    progress.log_sync("Retrieving test designs...")
    status = TestDesignStatus(status_filter) if status_filter and status_filter != "all" else None
    designs = get_test_designs_by_status(project_root, status)
    designs_file = get_dsl_tests_dir(project_root) / "designs.json"

    if test_ids:
        # Return full content for requested designs only
        filtered = [d for d in designs if d.test_id in test_ids]
        return json.dumps(
            {
                "count": len(filtered),
                "filter": status_filter or "all",
                "file": str(designs_file) if designs_file.exists() else None,
                "designs": [serialize_test_design(d) for d in filtered],
            },
            indent=2,
        )

    # Default: return compact summaries
    return json.dumps(
        {
            "count": len(designs),
            "filter": status_filter or "all",
            "file": str(designs_file) if designs_file.exists() else None,
            "designs": [serialize_test_design_summary(d) for d in designs],
            "guidance": "Use test_design(operation='get', test_ids=['TD-001']) to fetch full details.",
        },
        indent=2,
    )
