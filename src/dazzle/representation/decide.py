"""Executable representation ladder (#1617).

Pure function: signals and/or free text → pattern_id + DSL sketch + reject list.
No I/O. Agents call this before inventing host poly or dual-lock open-via.
"""

from __future__ import annotations

import re
from typing import Any

from dazzle.representation.patterns import PATTERN_CATALOGUE, PatternId

# Keyword → signal flags (OR into decide).
_TEXT_SIGNALS: list[tuple[re.Pattern[str], dict[str, Any]]] = [
    (
        re.compile(
            r"attachable|commentable|taggable|audit\s*log|notification\s*target|"
            r"morphic|subject_type|owner_type|item_type|polymorphic\s+association",
            re.I,
        ),
        {"shared_child_of_many_parents": True, "corpus_poly_prior": True},
    ),
    (
        re.compile(
            r"company\s*(or|/|\|)\s*sole.?trader|sole.?trader|partnership|"
            r"first_non_null|exclusive\s+fk|alternative\s+parents|"
            r"one\s+of\s+(several|a few)\s+parents|client\s+type",
            re.I,
        ),
        {"exclusive_parents": True, "parent_count_hint": 3},
    ),
    (
        re.compile(
            r"\bis.?a\b|subtype|subclass|table.?per.?type|inheritance|"
            r"mixed.?kind\s+list|polymorphic\s+list",
            re.I,
        ),
        {"true_isa_hint": True},
    ),
    (
        re.compile(
            r"custom\s+fields?|tenant.?variable|extension\s+payload|jsonb|"
            r"per.?org\s+fields|feature.?bag",
            re.I,
        ),
        {"tenant_variable_fields": True},
    ),
    (
        re.compile(r"dual.?lock|host\s+schema|host\s+owns|extension\s+schema", re.I),
        {"host_extension": True},
    ),
    (
        re.compile(r"journey|open.?via|client\s+overview|deep.?dive", re.I),
        {"journey_open_via": True},
    ),
]


def _merge_text_signals(text: str | None, signals: dict[str, Any]) -> dict[str, Any]:
    out = dict(signals)
    if not text:
        return out
    for pattern, flags in _TEXT_SIGNALS:
        if pattern.search(text):
            for k, v in flags.items():
                if k == "parent_count_hint" and "parent_count" not in out:
                    out["parent_count"] = v
                elif k != "parent_count_hint":
                    out[k] = out.get(k) or v
    return out


def _flags(sig: dict[str, Any]) -> dict[str, Any]:
    exclusive = bool(sig.get("exclusive_parents"))
    parent_count = int(sig.get("parent_count") or 0)
    if exclusive and parent_count < 2:
        parent_count = max(parent_count, 2)
    return {
        "shared": bool(sig.get("shared_child_of_many_parents")),
        "true_isa": bool(sig.get("true_isa") or sig.get("true_isa_hint")),
        "mixed": bool(sig.get("needs_mixed_kind_list")),
        "exclusive": exclusive,
        "parent_count": parent_count,
        "tenant_json": bool(sig.get("tenant_variable_fields")),
        "journey": bool(sig.get("journey_open_via")),
        "host": bool(sig.get("host_extension")),
        "four_q": bool(sig.get("four_questions_failed")),
        "corpus_poly": bool(sig.get("corpus_poly_prior")),
        "has_text": bool(sig.get("_has_text")),
    }


def _try_host(f: dict[str, Any], sig: dict[str, Any]) -> dict[str, Any] | None:
    if f["host"] and not f["exclusive"] and not f["shared"] and not f["true_isa"]:
        return _finish(
            PatternId.HOST_EXTENSION,
            ["host_extension signal — framework core stays normalized"],
            [],
            sig,
            confidence="medium",
        )
    return None


def _try_poly_ref(f: dict[str, Any], sig: dict[str, Any]) -> dict[str, Any] | None:
    if not f["shared"] or not (f["four_q"] or f["corpus_poly"]):
        return None
    if f["exclusive"] and 2 <= f["parent_count"] <= 4 and not f["four_q"]:
        return None
    why = ["shared child of many parent kinds"]
    if f["four_q"]:
        why.append("four-question interrogation failed — poly_ref sanctioned")
    if f["corpus_poly"]:
        why.append("corpus poly prior — use typed poly_ref, not hand-rolled")
    reject = [
        f"{PatternId.EXCLUSIVE_FKS}: exclusive FKs are for one-row alternative parents, "
        f"not shared children",
        f"{PatternId.EXPLICIT_REF}: single ref cannot express many parent kinds",
    ]
    conf = "high" if f["four_q"] else "medium"
    return _finish(PatternId.POLY_REF, why, reject, sig, confidence=conf)


def _try_tpt(f: dict[str, Any], sig: dict[str, Any]) -> dict[str, Any] | None:
    if not (f["true_isa"] and (f["mixed"] or sig.get("true_isa"))):
        return None
    return _finish(
        PatternId.TPT_SUBTYPE,
        ["true ISA with mixed-kind / polymorphic list need"],
        [
            f"{PatternId.STI}: prefer TPT over single-table inheritance",
            f"{PatternId.EXCLUSIVE_FKS}: exclusive FKs are not inheritance",
        ],
        sig,
        confidence="high",
    )


def _try_exclusive(f: dict[str, Any], sig: dict[str, Any]) -> dict[str, Any] | None:
    if not (
        f["exclusive"] or (f["journey"] and f["parent_count"] >= 2) or 2 <= f["parent_count"] <= 4
    ):
        return None
    why = ["2–4 alternative parent types (sparse exclusive FKs)"]
    if f["journey"]:
        why.append("journey open-via needs first_non_null hop")
    reject = [
        f"{PatternId.POLY_REF}: not a shared-child-to-many-parents association "
        f"— product-layer exclusive parents",
        f"{PatternId.TPT_SUBTYPE}: not true ISA unless parents share a base entity",
        f"{PatternId.HOST_EXTENSION}: do not dual-lock open-via for this shape",
    ]
    return _finish(PatternId.EXCLUSIVE_FKS, why, reject, sig, confidence="high")


def _try_json(f: dict[str, Any], sig: dict[str, Any]) -> dict[str, Any] | None:
    if not f["tenant_json"]:
        return None
    return _finish(
        PatternId.JSON_EXTENSION,
        ["tenant/feature-variable shape — keep core columns typed"],
        [f"{PatternId.EAV}: classic EAV joins are last resort; use JSONB bag"],
        sig,
        confidence="medium",
    )


def _default_explicit(f: dict[str, Any], sig: dict[str, Any]) -> dict[str, Any]:
    why = ["default: single typed ref / normalized explicit relations"]
    conf = "high"
    if f["true_isa"] and not f["mixed"]:
        why = ["ISA hint without mixed-kind list — prefer separate entities or state machine first"]
        conf = "low"
        return _finish(
            PatternId.EXPLICIT_REF,
            why,
            [f"{PatternId.TPT_SUBTYPE}: only when mixed list + true ISA + exclusive columns"],
            sig,
            confidence=conf,
        )
    if not any([f["shared"], f["exclusive"], f["tenant_json"], f["true_isa"], f["host"]]):
        why.append("no hatch signals — stay purist")
    if f["has_text"] and conf == "high":
        conf = "medium"
    return _finish(PatternId.EXPLICIT_REF, why, [], sig, confidence=conf)


def decide_representation(
    *,
    text: str | None = None,
    signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose a named representation pattern (ordered ladder, purist first)."""
    sig = _merge_text_signals(text, dict(signals or {}))
    if text:
        sig["_has_text"] = True
    f = _flags(sig)
    for try_fn in (_try_host, _try_poly_ref, _try_tpt, _try_exclusive, _try_json):
        hit = try_fn(f, sig)
        if hit is not None:
            return hit
    return _default_explicit(f, sig)


def _finish(
    pid: PatternId,
    why: list[str],
    reject: list[str],
    sig: dict[str, Any],
    *,
    confidence: str,
) -> dict[str, Any]:
    row = dict(PATTERN_CATALOGUE[pid])
    return {
        "ok": True,
        "pattern_id": str(pid),
        "confidence": confidence,
        "layer": row["layer"],
        "summary": row["summary"],
        "why": why,
        "reject": reject,
        "dsl_sketch": _dsl_sketch(pid),
        "integrity": list(row["integrity"]),
        "render": list(row["render"]),
        "rbac": list(row["rbac"]),
        "docs": list(row["docs"]),
        "counter_prior": row.get("counter_prior"),
        "signals_used": {
            k: v for k, v in sig.items() if k != "_has_text" and v not in (None, False, 0, "")
        },
        "next_steps": _next_steps(pid),
    }


def _dsl_sketch(pid: PatternId) -> str:
    sketches = {
        PatternId.EXCLUSIVE_FKS: (
            'entity Subscription "Subscription":\n'
            "  id: uuid pk\n"
            "  company: ref Company\n"
            "  sole_trader: ref SoleTrader\n"
            "  partnership: ref Partnership\n"
            "  invariant: company != null or sole_trader != null or partnership != null\n"
            "\n"
            'surface subscription_list "Subscriptions":\n'
            "  # … mode: list, uses entity Subscription\n"
            "  open: first_non_null(company, sole_trader, partnership)\n"
        ),
        PatternId.POLY_REF: (
            'entity Comment "Comment":\n'
            "  id: uuid pk\n"
            "  subject: poly_ref [Manuscript, Assessment]\n"
            "  body: text\n"
            "\n"
            "# permit read if subject[Manuscript].school = current_user.school\n"
        ),
        PatternId.TPT_SUBTYPE: (
            'entity Asset "Asset":\n'
            "  id: uuid pk\n"
            "  acquired_at: date required\n"
            "\n"
            'entity Vehicle "Vehicle":\n'
            "  subtype_of: Asset\n"
            "  vin: str(17) required unique\n"
        ),
        PatternId.JSON_EXTENSION: (
            'entity Client "Client":\n'
            "  id: uuid pk\n"
            "  name: text required\n"
            "  extensions: json  # tenant/feature bag only\n"
        ),
        PatternId.HOST_EXTENSION: (
            "# Host extension schema / routes/* dual-lock\n"
            "# Do not reimplement open: first_non_null in host\n"
        ),
    }
    return sketches.get(pid, "field: ref ParentEntity  # explicit single parent\n")


def _next_steps(pid: PatternId) -> list[str]:
    common = [
        "dazzle representation classify -p .",
        "dazzle prove representation -p .",
    ]
    if pid == PatternId.EXCLUSIVE_FKS:
        return [
            "Author invariant: a != null or b != null [or c…]",
            "Author open: first_non_null(a, b, c) on list surfaces",
            "dazzle db verify  # unanchored + exclusive_conflict",
            *common,
        ]
    if pid == PatternId.POLY_REF:
        return [
            "Use poly_ref [T…] — never subject_type + subject_id pair",
            "knowledge counter_prior id=polymorphic_associations",
            "dazzle db explain-scope <Entity> <verb>",
            *common,
        ]
    if pid == PatternId.JSON_EXTENSION:
        return [
            "Keep identity/FKs as typed columns; bag only in extensions: json",
            "dazzle representation gin-sql <Entity> --column extensions",
            "Omit json columns from dense lists (or accept compact summary)",
            *common,
        ]
    return ["dazzle representation decide --text '…'", *common]
