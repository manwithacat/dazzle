"""Type-evidence helpers for domain noun recovery (cycle 1383).

Keeps ``extract.py`` MI under the complexity ratchet while hosting the
canonical-case / bold-inventory rules that recover Task/Milestone without
re-admitting Email/Phone field chrome.
"""

from __future__ import annotations

import re

# Bullet domain inventory: "- **Tasks** — the units of work" (project_tracker)
_BULLET_ENTITY_RE = re.compile(
    r"^[\-\*]\s+\*{1,2}([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\*{1,2}\s*[—–\-:]",
    re.M,
)
# Sections that list *domain types* as bold bullets (not workspace/desk maps).
# Body ends at the next H2 so UI sections never leak Mobile/Dashboard bullets.
_DOMAIN_BULLET_SECTION_RE = re.compile(
    r"(?is)##\s*(?:what\s+it\s+does|domain\s+model|core\s+entities|"
    r"entities|data\s+model|domain\s+nouns?)\b"
    r"(.*?)(?=\n##\s+|\Z)"
)
_WORKSPACE_COMPOUND_RE = re.compile(
    r"(board|dashboard|desk|plan|ops|roster|pipeline|catalog|queue)$",
    re.I,
)


def singular_type_label(label: str) -> str:
    """Strip a trailing plural ``s``/``es`` for bold-list domain types.

    ``Tasks`` → ``Task``, ``Milestones`` → ``Milestone``, ``Attachments`` →
    ``Attachment``. Leaves CamelCase compounds and short tokens alone.
    """
    if " " in label:
        parts = label.split()
        if len(parts) >= 2 and parts[-1].endswith("s") and len(parts[-1]) > 3:
            last = parts[-1]
            if last.lower().endswith("ies") and len(last) > 4:
                parts[-1] = last[:-3] + "y"
            elif last.lower().endswith("es") and last[-3].lower() in "shx":
                parts[-1] = last[:-2]
            else:
                parts[-1] = last[:-1]
            return " ".join(parts)
        return label
    if len(label) <= 4 or not label.endswith("s"):
        return label
    if label.endswith("ss"):
        return label
    if label.lower().endswith("ies") and len(label) > 4:
        return label[:-3] + "y"
    if label.lower().endswith(("ches", "shes", "xes", "zes")):
        return label[:-2]
    return label[:-1]


def bullet_entities(text: str, noun_deny: frozenset[str]) -> set[str]:
    """Bold inventory bullets under domain sections only.

    ``- **Tasks** — the units of work`` under *What it does* is a type.
    ``- **Dashboard** — manager portfolio`` under *Where work happens* is a
    workspace — must not become a grounded noun.
    """
    out: set[str] = set()
    sections = _DOMAIN_BULLET_SECTION_RE.findall(text)
    if not sections:
        return out
    for body in sections:
        for m in _BULLET_ENTITY_RE.finditer(body):
            label = singular_type_label(m.group(1).strip())
            compact = re.sub(r"\s+", "", label)
            if len(compact) < 3 or compact.lower() in noun_deny:
                continue
            if _WORKSPACE_COMPOUND_RE.search(compact):
                continue
            out.add(compact)
            if " " not in label:
                out.add(label)
    return out


def type_evidence_capitalized(cap: str, text: str) -> bool:
    """True when *cap* is introduced as a domain type, not a field/table label.

    Capitalized field names (Email, Phone, Unique) flood SPECs; core types
    show up as ``**Task**``, ``A Task moves…``, ``### Entity: Contact``, or
    inventory bullets ``- **Milestones** — …``.
    """
    if re.search(rf"\*\*{re.escape(cap)}s?\*\*", text):
        return True
    if re.search(rf"\b(?:A|An)\s+\*{{0,2}}{re.escape(cap)}\*{{0,2}}\s+", text):
        return True
    if re.search(
        rf"(?im)^(?:\#{{2,4}}\s+)?(?:entity|record|type|model)\s*:?\s+"
        rf"\*{{0,2}}{re.escape(cap)}\*{{0,2}}\b",
        text,
    ):
        return True
    if re.search(
        rf"(?m)^[\-\*]\s+\*{{1,2}}{re.escape(cap)}s?\*{{1,2}}\s*[—–\-:]",
        text,
    ):
        return True
    return False


def split_camel_tokens(name: str) -> list[str]:
    """Split CamelCase including leading acronyms.

    ``SupportTicket`` → ``Support``, ``Ticket`` (lower→Upper).
    ``SLAWaiver`` → ``SLA``, ``Waiver`` (ACRONYM + Capitalized — cycle 1385).
    Plain words and spaced labels pass through.
    """
    if not name:
        return []
    if " " in name:
        return name.split()
    # ACRONYMRest → ACRONYM Rest, then lowerUpper → lower Upper
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name)
    spaced = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", spaced)
    return spaced.split()


def canonical_case(name: str, text: str) -> str:
    """Recover brief casing when offline discover emits lowercased types.

    Cycle 1383: project_tracker discover emitted ``task``/``milestone``;
    first case-insensitive hit was mid-prose lowercase (\"day-to-day task\"),
    so Title-case entities were rejected as ``lowercase`` and Comment/
    Attachment crowded out Task/Milestone.

    Prefer CamelCase, then Capitalized forms **with type-level evidence**
    (bold / definitional / entity header / inventory bullet). Bare
    Capitalized table fields (Email, Phone, Unique) must NOT upgrade a
    lowercase discover hit — those stay lowercase and fail the gate.
    """
    if not name:
        return name
    matches = [m.group(1) for m in re.finditer(rf"\b({re.escape(name)})\b", text, re.I)]
    if not matches:
        return name
    for tok in matches:
        if re.search(r"[a-z][A-Z]", tok):
            return tok
    for tok in matches:
        if tok[0].isupper() and type_evidence_capitalized(tok, text):
            return tok
    return matches[0]
