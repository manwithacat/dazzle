"""#1599 — field option aliases for form search-select.

``search_trigger=<pack>`` → ``source=<pack>.<search_op>`` so authors who
wrote the pack-level shorthand still get a real typeahead when a search
operation exists on the pack.
"""

from __future__ import annotations


def resolve_search_trigger_to_source(trigger: str) -> str | None:
    """Map ``search_trigger`` pack (or pack.op) to a ``source=`` pack.op ref.

    Prefer ``search_companies`` (Companies House convention), else the first
    operation whose name starts with ``search_``. Returns ``None`` if the pack
    is missing or has no search-shaped operation.
    """
    if not trigger or not str(trigger).strip():
        return None
    trigger = str(trigger).strip()
    if "." in trigger:
        return trigger
    pack_name = trigger
    try:
        from dazzle.api_kb import load_pack

        pack = load_pack(pack_name)
    except Exception:
        return None
    if not pack:
        return None
    ops = [o.name for o in (getattr(pack, "operations", None) or [])]
    if not ops:
        return None
    if "search_companies" in ops:
        return f"{pack_name}.search_companies"
    for name in ops:
        if name.startswith("search_"):
            return f"{pack_name}.{name}"
    return None
