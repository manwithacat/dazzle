"""Shared friction schema for ``dazzle qa trial`` and consumer improve loops.

Gen-2+ (#1625): categories, ownership triage, and auto-seed rules so
CyFuture/AegisMark-class agents can close the loop (PENDING seed) without
re-filing harness ghosts.
"""

from __future__ import annotations

from typing import Any

# Product-facing friction categories (agent + human shared).
FRICTION_CATEGORIES: tuple[str, ...] = (
    "bug",
    "missing",
    "confusion",
    "story_gap",
    "aesthetic",
    "praise",
    "other",
)

# Who owns the finding — drives auto-seed filters.
OWNERSHIP_VALUES: tuple[str, ...] = (
    "product",  # real app/framework product issue → auto-seed eligible
    "seed",  # empty/missing demo data, not product
    "rbac_expected",  # expected deny / matrix-correct 403
    "harness",  # lazy IO, actionability timeout, headless artifact
    "framework",  # framework-wide defect (still product for dazzle core)
    "unclear",
)

SEVERITIES: tuple[str, ...] = ("low", "medium", "high")

# Categories that may become improve PENDING when ownership is product.
_AUTO_SEED_CATEGORIES: frozenset[str] = frozenset({"bug", "missing", "confusion", "story_gap"})
_AUTO_SEED_SEVERITIES: frozenset[str] = frozenset({"medium", "high"})


def clamp_category(value: str) -> str:
    return value if value in FRICTION_CATEGORIES else "other"


def clamp_ownership(value: str) -> str:
    return value if value in OWNERSHIP_VALUES else "unclear"


def clamp_severity(value: str) -> str:
    return value if value in SEVERITIES else "medium"


def normalize_friction_entry(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a friction dict to the stable consumer schema."""
    entry = dict(raw)
    entry["category"] = clamp_category(str(entry.get("category") or "other"))
    entry["severity"] = clamp_severity(str(entry.get("severity") or "medium"))
    ownership = entry.get("ownership")
    if not ownership:
        # Back-compat: map gen-2 framework_vs_app → ownership when present.
        fva = str(entry.get("framework_vs_app") or "").lower()
        if fva == "framework":
            ownership = "framework"
        elif fva == "app":
            ownership = "product"
        else:
            ownership = "unclear"
    entry["ownership"] = clamp_ownership(str(ownership))
    entry["description"] = str(entry.get("description") or "").strip()
    entry["url"] = str(entry.get("url") or "").strip()
    entry["evidence"] = str(entry.get("evidence") or "").strip()
    entry["blocks_pilot"] = bool(entry.get("blocks_pilot"))
    # Keep framework_vs_app as soft alias for older triagers.
    if not entry.get("framework_vs_app"):
        if entry["ownership"] == "framework":
            entry["framework_vs_app"] = "framework"
        elif entry["ownership"] == "product":
            entry["framework_vs_app"] = "app"
        else:
            entry["framework_vs_app"] = "unclear"
    return entry


def is_auto_seed_eligible(entry: dict[str, Any]) -> bool:
    """True when a consumer improve loop should seed PENDING from this row.

    Rule (#1625 AegisMark): medium+ product categories only.
    ``ownership=framework`` is eligible when the *consumer* is the framework
    itself (Dazzle core); for downstream apps, prefer ownership=product.
    Callers pass ``allow_framework=True`` for Dazzle's own improve loop.
    """
    e = normalize_friction_entry(entry)
    if e["category"] not in _AUTO_SEED_CATEGORIES:
        return False
    if e["severity"] not in _AUTO_SEED_SEVERITIES:
        return False
    return e["ownership"] == "product"


def friction_cluster_key(entry: dict[str, Any]) -> tuple[str, ...]:
    """Key for pre-seed clustering (category, severity, url, token head)."""
    e = normalize_friction_entry(entry)
    desc = " ".join(e["description"].lower().split())
    # Soft-collapse near-dupes that share URL + first 8 significant tokens
    tokens = [t for t in desc.split() if len(t) > 3][:8]
    url = e.get("url") or ""
    return (e["category"], e["severity"], url, " ".join(tokens))


# Console thrash / headless resource exhaustion — AegisMark harness artifacts.
_HARNESS_EVIDENCE_MARKERS: tuple[str, ...] = (
    "err_insufficient_resources",
    "net::err_insufficient_resources",
    "failed to fetch",
    "htmx:error failed to fetch",
)


def apply_ownership_heuristics(entry: dict[str, Any]) -> dict[str, Any]:
    """Reclassify ownership when evidence matches known harness ghosts.

    Agents often mark product for console storms that are instrument or
    framework thrash (ERR_INSUFFICIENT_RESOURCES, mass htmx Failed to fetch).
    Prefer harness unless the description names a clear user-visible deadend
    *and* lacks thrash markers in evidence.
    """
    e = normalize_friction_entry(entry)
    blob = f"{e.get('description', '')} {e.get('evidence', '')}".lower()
    thrash_hits = sum(1 for m in _HARNESS_EVIDENCE_MARKERS if m in blob)
    if thrash_hits >= 2 and e["ownership"] == "product":
        e["ownership"] = "harness"
        e["framework_vs_app"] = "unclear"
        e["_ownership_note"] = "reclassified product→harness (console/network thrash markers)"
    return e


def filter_auto_seed(
    entries: list[dict[str, Any]],
    *,
    allow_framework: bool = False,
) -> list[dict[str, Any]]:
    """Return friction rows safe to auto-seed into improve PENDING.

    Applies ownership heuristics, eligibility filter, then clusters near-
    duplicates so one UUID-leak or thrash pattern is not 40 PENDING rows.
    """
    eligible: list[dict[str, Any]] = []
    for raw in entries:
        e = apply_ownership_heuristics(raw)
        if e["category"] not in _AUTO_SEED_CATEGORIES:
            continue
        if e["severity"] not in _AUTO_SEED_SEVERITIES:
            continue
        if e["ownership"] == "product":
            eligible.append(e)
        elif allow_framework and e["ownership"] == "framework":
            eligible.append(e)

    # Cluster: keep first of each key
    seen: set[tuple[str, ...]] = set()
    out: list[dict[str, Any]] = []
    for e in eligible:
        key = friction_cluster_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
