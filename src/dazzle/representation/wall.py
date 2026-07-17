"""Attach representation prove summary to agent wall (#1618)."""

from __future__ import annotations

from typing import Any

from dazzle.representation.prove import prove_representation


def attach_representation_to_wall(wall: dict[str, Any], appspec: Any) -> dict[str, Any]:
    """Return a copy of the binding wall with representation prove prefixed."""
    out = dict(wall)
    try:
        proved = prove_representation(appspec)
        result = str(proved.get("result") or "unknown")
        ok = bool(proved.get("ok"))
        line = f"Representation: {'OK' if ok else 'FAIL'} ({result})"
        md = out.get("markdown") or ""
        out["markdown"] = f"{line}\n\n{md}" if md else line
        out["representation"] = {
            "ok": ok,
            "result": result,
            "classify_counts": proved.get("classify_counts"),
            "commands": {
                "classify": "dazzle representation classify -p .",
                "prove": "dazzle prove representation -p .",
            },
        }
        note = out.get("note") or ""
        out["note"] = (
            f"{note} representation = #1617 static hatch integrity."
            if note
            else "representation = #1617 static hatch integrity."
        )
    except Exception as exc:
        out["representation"] = {"ok": False, "error": str(exc)[:160]}
    return out
