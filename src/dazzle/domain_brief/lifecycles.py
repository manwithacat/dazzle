"""Lifecycle identification for founder-spec analysis (agent cognition).

Pure helpers used by ``spec_analyze.identify_lifecycles`` and domain extract.
Goals (agent-domain-prior investigation P0/P1):

- Honour explicit arrow chains with underscore-safe state tokens (``in_progress``).
- Match entity names to workflow templates / keyword patterns **fuzzily**
  (``SupportTicket`` ↔ ticket, ``Invoice`` ↔ invoice).
- Prefer brief-local chains over canned templates.
- Propose process candidates when multi-persona + lifecycle entity co-occur.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Underscore-aware state token (DSL status enums use snake_case).
_STATE_TOKEN = r"[A-Za-z][A-Za-z0-9_]*"
_ARROW = r"(?:->|→|=>)"
_CHAIN_RE = re.compile(rf"\b({_STATE_TOKEN}(?:\s*{_ARROW}\s*{_STATE_TOKEN})+)")
_SPLIT_ARROWS = re.compile(rf"\s*{_ARROW}\s*")

# Built-in fallback when inference_kb.toml is unavailable (tests without package data).
_BUILTIN_PATTERNS: dict[str, list[str]] = {
    "order": ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"],
    "request": ["draft", "submitted", "pending", "approved", "rejected", "completed"],
    "application": ["submitted", "under_review", "accepted", "rejected", "withdrawn"],
    "booking": ["pending", "confirmed", "in_progress", "completed", "cancelled"],
    "payment": ["pending", "processing", "completed", "failed", "refunded"],
    "invoice": ["draft", "submitted", "approved", "rejected", "paid"],
    "task": ["pending", "assigned", "in_progress", "completed", "blocked"],
    "ticket": ["open", "in_progress", "resolved", "closed", "reopened"],
    "issue": ["open", "triaged", "in_progress", "fixed", "verified", "closed"],
    "listing": ["draft", "active", "paused", "sold", "expired"],
    "job": ["open", "assigned", "in_progress", "completed", "cancelled"],
    "alert": ["active", "acknowledged", "resolved"],
    "campaign": ["planning", "active", "completed", "cancelled"],
    "asset": ["draft", "review", "approved", "published", "archived"],
    "firmware": ["draft", "released", "deprecated"],
    "release": ["draft", "released", "deprecated"],
    "device": ["prototype", "active", "retired"],
    "milestone": ["planning", "active", "completed"],
    "integration": ["off", "pending", "live", "revoked"],
    "subscription": ["trialing", "active", "past_due", "paused", "cancelled"],
    "system": ["healthy", "degraded", "critical", "offline"],
}

_TRANSITION_WORD_RE = re.compile(
    r"\b(post|submit|approve|reject|cancel|complete|assign|accept|decline|"
    r"confirm|ship|deliver|pay|review|start|finish|close|escalate|triage|"
    r"acknowledge|resolve|dispute|settle)\w*\b",
    re.I,
)

# Role-ish words that must not receive entity lifecycles when they are only personas.
_PERSONA_LIKE = frozenset(
    {
        "requester",
        "approver",
        "customer",
        "admin",
        "administrator",
        "manager",
        "agent",
        "user",
        "staff",
        "member",
        "owner",
        "provider",
        "employee",
        "engineer",
        "tester",
        "auditor",
        "finance",
        "reviewer",
        "designer",
    }
)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _camel_parts(name: str) -> list[str]:
    if not name:
        return []
    return [p.lower() for p in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name) if p]


def entity_matches_keyword(entity_name: str, keyword: str) -> bool:
    """True when entity name and pattern keyword refer to the same stem."""
    el = _norm(entity_name)
    kl = _norm(keyword)
    if not el or not kl:
        return False
    if el == kl or kl in el or el in kl:
        return True
    parts = set(_camel_parts(entity_name))
    return kl in parts


def best_keyword_match(entity_name: str, keywords: list[str]) -> str | None:
    """Longest keyword that fuzzily matches the entity (specificity wins)."""
    hits = [k for k in keywords if entity_matches_keyword(entity_name, k)]
    if not hits:
        return None
    hits.sort(key=lambda k: len(_norm(k)), reverse=True)
    return hits[0]


def _template_keys(row: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for t in row.get("triggers") or []:
        t = str(t).strip().lower()
        if t and " " not in t and len(t) >= 3:
            keys.append(t)
    name = str(row.get("name") or row.get("id") or "")
    if name:
        first = name.split()[0].lower()
        if len(first) >= 3:
            keys.append(first)
    return keys


def _merge_template_row(patterns: dict[str, list[str]], row: dict[str, Any]) -> None:
    """First-write merge of one workflow_templates row (builtins win)."""
    states = row.get("states") or []
    if not isinstance(states, list) or len(states) < 2:
        return
    state_list = [str(s).strip().lower() for s in states if s]
    for k in _template_keys(row):
        kn = _norm(k)
        if len(kn) < 3:
            continue
        patterns.setdefault(kn, state_list)
        if k.isalpha():
            patterns.setdefault(k, state_list)


@lru_cache(maxsize=1)
def workflow_lifecycle_patterns() -> dict[str, list[str]]:
    """Keyword → states from inference_kb workflow_templates + builtins."""
    patterns = dict(_BUILTIN_PATTERNS)
    toml_path = Path(__file__).resolve().parents[1] / "mcp" / "inference_kb.toml"
    if not toml_path.is_file():
        return patterns
    try:
        import tomllib

        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception:
        return patterns
    for row in data.get("workflow_templates") or []:
        if isinstance(row, dict):
            _merge_template_row(patterns, row)
    return patterns


def parse_arrow_chains(spec_text: str) -> list[tuple[str, list[str]]]:
    """Return (sentence, states) for each explicit arrow chain in the text."""
    out: list[tuple[str, list[str]]] = []
    for sentence in re.split(r"[.;\n]", spec_text):
        for match in _CHAIN_RE.finditer(sentence):
            chain = match.group(1)
            states = [s.strip().lower() for s in _SPLIT_ARROWS.split(chain) if s.strip()]
            # Drop broken mid-word fragments (legacy \w+ split left orphans)
            states = [s for s in states if re.fullmatch(_STATE_TOKEN, s)]
            if len(states) < 2:
                continue
            out.append((sentence, states))
    return out


def attribute_chain_to_entity(
    sentence: str,
    states: list[str],
    entity_names: list[str],
) -> str:
    """Nearest entity in the sentence; fuzzy token match; else UNKNOWN."""
    if not entity_names:
        return "UNKNOWN"
    sentence_lower = sentence.lower()
    chain_pos = sentence_lower.find(states[0]) if states else 0
    best: tuple[float, str] | None = None
    for n in entity_names:
        if not n:
            continue
        pos = sentence_lower.find(n.lower())
        if pos < 0:
            # fuzzy: any camel part or norm stem appears as word
            for part in _camel_parts(n) + [_norm(n)]:
                if len(part) < 3:
                    continue
                m = re.search(rf"\b{re.escape(part)}\b", sentence_lower)
                if m:
                    pos = m.start()
                    break
        if pos < 0:
            continue
        distance = chain_pos - pos if pos <= chain_pos else (pos - chain_pos) + 10_000
        if best is None or distance < best[0]:
            best = (distance, n)
    return best[1] if best else "UNKNOWN"


def match_pattern_lifecycle(entity_name: str) -> tuple[list[str], str] | None:
    """Return (states, source) for a canned/workflow pattern, or None."""
    if not entity_name or _norm(entity_name) in _PERSONA_LIKE:
        return None
    patterns = workflow_lifecycle_patterns()
    # Prefer longest keyword match
    key = best_keyword_match(entity_name, list(patterns.keys()))
    if key is None:
        return None
    states = patterns[key]
    return list(states), "pattern_match"


def resolve_lifecycle_for_name(
    name: str,
    life_by_entity: dict[str, list[str]],
) -> list[str]:
    """Exact then fuzzy lookup of lifecycle states for a domain noun.

    Prefer life-map keys that are *stems* of the noun (Ticket → SupportTicket),
    not the reverse (TicketClassification must not paint Classification).
    """
    if not name:
        return []
    if name in life_by_entity and life_by_entity[name]:
        return list(life_by_entity[name])
    nl = _norm(name)
    best_states: list[str] = []
    best_score = 0
    for key, states in life_by_entity.items():
        if not states or key in ("UNKNOWN", ""):
            continue
        kl = _norm(key)
        if nl == kl:
            return list(states)
        # Key is a stem/token of the noun (SupportTicket ← Ticket)
        if kl and kl != nl and (kl in nl or entity_matches_keyword(name, key)):
            # Reject reverse containment (noun shorter than key)
            if len(kl) > len(nl):
                continue
            score = len(kl)
            if score > best_score:
                best_score = score
                best_states = list(states)
    return best_states


def _entity_names(entities: list[Any]) -> list[str]:
    names = [(e if isinstance(e, str) else str(e.get("name") or "")) for e in (entities or [])]
    return [n for n in names if n]


def _arrow_lifecycles(spec_text: str, entity_names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "entity": attribute_chain_to_entity(sentence, states, entity_names),
            "status_field": "status",
            "states": states,
            "source": "arrow_chain",
        }
        for sentence, states in parse_arrow_chains(spec_text)
    ]


def _pattern_lifecycle_for_entity(
    entity_name: str, arrow_entities: set[str]
) -> dict[str, Any] | None:
    if entity_name in arrow_entities:
        return None
    if any(entity_matches_keyword(entity_name, ae) for ae in arrow_entities):
        return None
    matched = match_pattern_lifecycle(entity_name)
    if matched:
        states, source = matched
        return {
            "entity": entity_name,
            "status_field": "status",
            "states": states,
            "source": source,
        }
    el = entity_name.lower()
    if any(w in el for w in ("request", "order", "booking", "job")):
        return {
            "entity": entity_name,
            "status_field": "status",
            "states": ["pending", "active", "completed", "cancelled"],
            "source": "generic_pattern",
        }
    return None


def identify_lifecycles(
    spec_text: str,
    entities: list[Any],
) -> dict[str, Any]:
    """Core lifecycle identification (JSON-serialisable dict)."""
    entity_names = _entity_names(entities)
    transition_words = [m.group(0).lower() for m in _TRANSITION_WORD_RE.finditer(spec_text)]
    lifecycles = _arrow_lifecycles(spec_text, entity_names)
    arrow_entities = {lc["entity"] for lc in lifecycles if lc["entity"] != "UNKNOWN"}
    for name in entity_names:
        row = _pattern_lifecycle_for_entity(name, arrow_entities)
        if row:
            lifecycles.append(row)
    if transition_words and not lifecycles:
        lifecycles.append(
            {
                "entity": "UNKNOWN",
                "status_field": "status",
                "suggested_transitions": list(set(transition_words)),
                "hint": "These actions suggest state transitions. Assign to appropriate entities.",
            }
        )
    return {
        "lifecycles": lifecycles,
        "detected_transitions": sorted(set(transition_words)),
        "process_candidates": propose_process_candidates(
            spec_text=spec_text,
            entity_names=entity_names,
            lifecycles=lifecycles,
        ),
        "hint": (
            "Add state machines to entities with clear lifecycles. "
            "Not every entity needs one. Prefer process blocks when "
            "multiple personas share a lifecycle entity."
        ),
    }


_PERSONA_SIGNAL_RES: list[tuple[str, str]] = [
    ("requester", r"\brequesters?\b"),
    ("approver", r"\bapprovers?\b"),
    ("manager", r"\bmanagers?\b"),
    ("agent", r"\b(?:support\s+)?agents?\b"),
    ("finance", r"\bfinance\b"),
    ("customer", r"\bcustomers?\b"),
    ("engineer", r"\bengineers?\b"),
    ("tester", r"\btesters?\b"),
]


def _persona_signals(text_l: str) -> dict[str, bool]:
    return {name: bool(re.search(pat, text_l)) for name, pat in _PERSONA_SIGNAL_RES}


def _process_eligible(text_l: str, signals: dict[str, bool]) -> bool:
    if sum(1 for v in signals.values() if v) >= 2:
        return True
    if signals.get("requester") and signals.get("approver"):
        return True
    return bool(re.search(r"\b(approv|escalat|assign|settle|triage)\w*\b", text_l))


def _want_approval(text_l: str, signals: dict[str, bool], pn: str) -> bool:
    if not re.search(r"\b(approv|reject|submit)\w*\b", text_l):
        return False
    return bool(signals["approver"] or signals["requester"] or "invoice" in pn or "request" in pn)


def _want_escalation(text_l: str, signals: dict[str, bool]) -> bool:
    if re.search(r"\b(escalat|sla|manager)\w*\b", text_l):
        return True
    return bool(signals["manager"] and (signals["agent"] or signals["customer"]))


def _want_settlement(text_l: str, signals: dict[str, bool], pn: str) -> bool:
    if not re.search(r"\b(pay|settled?|payment|remit)\w*\b", text_l):
        return False
    return bool(signals["finance"] or "invoice" in pn or "payment" in pn)


def _process_rule_hits(text_l: str, signals: dict[str, bool], primary: str) -> list[dict[str, Any]]:
    """Table-driven process candidate rules (low cyclomatic)."""
    pn = _norm(primary)
    agentish = signals["agent"]
    rules: list[tuple[str, str, list[str], bool]] = [
        (
            "approval_flow",
            f"{primary}: requester submits, approver decides (approve/reject)",
            ["requester", "approver"],
            _want_approval(text_l, signals, pn),
        ),
        (
            "escalation",
            f"{primary}: worker escalates to manager when blocked or SLA risk",
            ["agent", "manager"] if agentish else ["member", "manager"],
            _want_escalation(text_l, signals),
        ),
        (
            "assignment",
            f"{primary}: auto or manager assignment to a worker",
            ["manager", "agent"] if agentish else ["manager", "member"],
            bool(re.search(r"\b(assign|queue|triage)\w*\b", text_l)),
        ),
        (
            "settlement",
            f"{primary}: finance settles / pays after approval",
            ["finance", "approver"],
            _want_settlement(text_l, signals, pn),
        ),
        (
            "triage",
            f"{primary}: intake triage before deep work",
            ["agent", "engineer"] if signals["engineer"] else ["agent", "manager"],
            bool(re.search(r"\b(triage|intake|prioritis|prioritiz)\w*\b", text_l)),
        ),
    ]
    return [
        {
            "id_hint": rid,
            "summary": summary,
            "personas": personas,
            "entity_hint": primary,
            "status": "hypothesis",
        }
        for rid, summary, personas, when in rules
        if when
    ]


def propose_process_candidates(
    *,
    spec_text: str,
    entity_names: list[str],
    lifecycles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Structured process hypotheses for multi-party domains (P1)."""
    text_l = (spec_text or "").lower()
    life_entities = [
        str(lc.get("entity") or "")
        for lc in lifecycles
        if isinstance(lc, dict) and lc.get("states") and lc.get("entity") not in ("UNKNOWN", "")
    ]
    if not life_entities and not entity_names:
        return []
    signals = _persona_signals(text_l)
    if not _process_eligible(text_l, signals):
        return []
    primary = life_entities[0] if life_entities else entity_names[0]
    if not primary:
        return []
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in _process_rule_hits(text_l, signals, primary):
        if c["id_hint"] in seen:
            continue
        seen.add(c["id_hint"])
        unique.append(c)
    return unique
