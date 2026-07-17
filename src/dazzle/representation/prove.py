"""Prove representation integrity from classify findings (#1617)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.representation.classify import classify_appspec, classify_project
from dazzle.representation.patterns import PatternId

_FAIL_KINDS = frozenset(
    {
        "hand_rolled_poly",
        "exclusive_fk_missing_invariant",
        "exclusive_fk_missing_open",
    }
)


def _partition_findings(
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    failures = [f for f in findings if f.get("kind") in _FAIL_KINDS]
    soft = [
        f for f in findings if f.get("severity") == "warning" and f.get("kind") not in _FAIL_KINDS
    ]
    evidence: list[str] = []
    for f in findings:
        kind = f.get("kind")
        if kind in ("exclusive_fk_set", "open_via_multi_hop_ok"):
            evidence.append(f"ok:{kind}:{f.get('entity')}")
        elif kind == "poly_ref":
            fields = ",".join(f.get("fields") or [])
            evidence.append(f"ok:poly_ref:{f.get('entity')}.{fields}")
    return failures, soft, evidence


def prove_representation(appspec: Any) -> dict[str, Any]:
    """Return pass/fail representation evidence for an AppSpec."""
    classified = classify_appspec(appspec)
    findings = list(classified.get("findings") or [])
    failures, soft, evidence = _partition_findings(findings)

    if failures:
        return {
            "ok": False,
            "result": "fail_representation",
            "evidence_kind": "representation",
            "checked": 1,
            "passed": 0,
            "failed": 1,
            "reasons": [f"{f['kind']}:{f.get('entity')}:{f.get('message')}" for f in failures],
            "evidence": evidence,
            "soft_warnings": [
                {"kind": f["kind"], "entity": f.get("entity"), "message": f.get("message")}
                for f in soft
            ],
            "classify_counts": classified.get("counts"),
            "pattern_ids_seen": sorted(
                {str(f.get("pattern_id")) for f in findings if f.get("pattern_id")}
            ),
            "note": _prove_note(),
        }

    if not evidence:
        evidence = ["no_hatch_findings:default_explicit_ref_posture"]
    return {
        "ok": True,
        "result": "pass_representation",
        "evidence_kind": "representation",
        "checked": 1,
        "passed": 1,
        "failed": 0,
        "reasons": [],
        "evidence": evidence,
        "soft_warnings": [
            {"kind": f["kind"], "entity": f.get("entity"), "message": f.get("message")}
            for f in soft
        ],
        "classify_counts": classified.get("counts"),
        "pattern_ids_seen": sorted(
            {str(f.get("pattern_id")) for f in findings if f.get("pattern_id")}
        ),
        "note": _prove_note(),
    }


def _prove_note() -> str:
    return (
        "Static representation prove (#1617). "
        "Also run `dazzle db verify` for exclusive_conflict row counts. "
        f"Default pattern remains {PatternId.EXPLICIT_REF}."
    )


def prove_representation_project(project_root: Path) -> dict[str, Any]:
    """Load project and prove representation."""
    root = project_root.resolve()
    classified = classify_project(root)
    if not classified.get("ok"):
        return {
            "ok": False,
            "result": "fail_representation",
            "error": classified.get("error"),
            "checked": 0,
            "passed": 0,
            "failed": 1,
        }
    appspec = load_project_appspec(root)
    out = prove_representation(appspec)
    out["project_root"] = str(root)
    out["classify_counts"] = classified.get("counts")
    return out
