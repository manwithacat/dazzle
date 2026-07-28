"""Clarification-question generation for the cognition pass (cycle 1372–1375).

Split from ``spec_analyze`` so the parent module stays MI-rank A while
cardinality / topic probes keep growing quality filters.
"""

from __future__ import annotations

import re
from typing import Any

# Stems the naive "strip trailing s" plural split invents from mass/non-count
# English or from prose that is not a domain noun pair (cycle 1372).
_CARDINALITY_BAD_LEFT = frozenset(
    {
        "progres",  # progress
        "acces",  # access
        "proces",  # process
        "statu",  # status
        "busines",  # business
        "succes",  # success
        "addres",  # address
        "analy",  # analysis (if matched oddly)
        "approve",
        "create",
        "review",
        "manage",
        "assign",
        "operate",
        "send",
        "submit",
        "require",
        "provide",
        "include",
        "ensure",
        "indicator",  # "warning indicators and overdue …" prose noise
        "warning",
        "setting",
        "metric",
        "signal",
        "batche",  # batches → naive strip
        "update",  # "updates and comments" prose
        "sale",
        "org",
        "owner",
        "devop",  # DevOps
        "sre",
    }
)
_CARDINALITY_BAD_RIGHT = frozenset(
    {
        "theirs",
        "wheres",
        "theres",
        "whats",
        "whiches",
        "whoms",
        "thens",
        "ones",
        "tos",
        "thes",
        "ops",
        "overdue",  # adjective / filter language, not an entity
        "workload",  # metric prose next to "progress"
        "filtering",
        "personal",
        "just",  # "… just and …" / "justs" prose fragment
        "assign",  # verb stem → "assigns"
        "approve",  # verb stem → "approves"
        "handle",  # verb stem → "handles"
        "manage",  # "projects and manages" verb fragment
        "send",
        "view",  # UI chrome, not domain noun
        "setting",
        "sre",
        "external",  # "members and externals" tenancy prose
        "auditor",  # role prose, not usually a ref target of "owner"
        "contractor",
        "review",  # lifecycle state / "permission review" / verb noun
        "feedback",  # chrome desk label, not usually a multi-ref child
    }
)

# Orthographic *an* would mis-label these (consonant-sound /juː/ or /w/).
_CONSONANT_SOUND_ONSET = frozenset(
    {
        "user",
        "unique",
        "university",
        "european",
        "one",
        "once",
        "usage",
        "utility",
        "unit",
        "euro",
    }
)


def entity_stems(entities: list[Any]) -> set[str]:
    """Lowercase singular-ish stems of discovered entity names for grounding."""
    stems: set[str] = set()
    for e in entities:
        if not isinstance(e, str):
            continue
        low = e.strip().lower()
        if not low:
            continue
        stems.add(low)
        # Compact multiword ("DesignAsset" already one token from discover)
        if low.endswith("s") and len(low) > 3 and not low.endswith("ss"):
            stems.add(low[:-1])
        else:
            stems.add(low + "s")
    return stems


def plausible_cardinality_token(word: str) -> bool:
    """Letter-only domain-ish token; reject digits and ultra-short stems."""
    return bool(re.fullmatch(r"[a-z]{3,24}", word))


def plural_obj(word2: str) -> str:
    """Avoid ``assignments`` → ``assignmentss`` when the capture already ends in s."""
    if word2.endswith("s"):
        return word2
    return f"{word2}s"


def right_stem(word2: str) -> str:
    if word2.endswith("s") and not word2.endswith("ss") and len(word2) > 3:
        return word2[:-1]
    return word2


def indefinite_article(word: str) -> str:
    """English *a* / *an* for a singular common-noun subject (cycle 1375).

    Orthographic vowel onset plus a small consonant-sound exception list
    (``user``, ``university``, …) — enough for domain stems without a
    full phonetics table.
    """
    if not word:
        return "a"
    w = word.lower()
    if w in _CONSONANT_SOUND_ONSET or w.startswith(("uni", "use", "eur", "one")):
        return "a"
    return "an" if w[0] in "aeiou" else "a"


def is_bad_cardinality_pair(word1: str, word2: str) -> bool:
    """True when either side is a known prose/verb stem, not a domain noun."""
    w2_stem = right_stem(word2)
    return (
        word1 in _CARDINALITY_BAD_LEFT
        or word2 in _CARDINALITY_BAD_RIGHT
        or w2_stem in _CARDINALITY_BAD_RIGHT
        or word1 in _CARDINALITY_BAD_RIGHT
    )


def cardinality_questions(spec_text: str, entities: list[Any]) -> list[dict[str, str]]:
    """Emit grounded one-to-many clarification questions from ``Xs and/or Ys`` prose.

    Letter-only tokens only; when ``entities`` is non-empty the *subject* (left)
    must match a discovered entity stem so "members and 7 tasks" / verb pairs drop.
    """
    ent_stems = entity_stems(entities)
    plurals = re.findall(
        r"\b([a-z]{3,24})s\s+(?:and|or)\s+([a-z]{3,24})s?\b",
        spec_text.lower(),
    )
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for word1, word2 in plurals:
        if not plausible_cardinality_token(word1) or not plausible_cardinality_token(word2):
            continue
        if is_bad_cardinality_pair(word1, word2):
            continue
        if ent_stems and word1 not in ent_stems:
            continue
        key = (word1, word2)
        if key in seen:
            continue
        seen.add(key)
        art = indefinite_article(word1)
        out.append(
            {
                "topic": "cardinality",
                "question": (f"Can {art} {word1} have multiple {plural_obj(word2)}, or just one?"),
                "impact": "Affects whether to use ref() or list of refs",
            }
        )
    return out


def bilateral_review_signal(low: str) -> bool:
    """True when prose means product/peer ratings — not lifecycle or permission review.

    Bare ``review`` is common in task flows (todo→review→done), desk labels
    (Compensation Review), and verbs (review invoices). Bare ``feedback`` is
    also noisy (\"feedback is scattered across Slack\"). Fire only on ratings
    or marketplace / design-review language that implies a Review entity.
    """
    if re.search(r"\b(rating|ratings|star\s*rating)\b", low):
        return True
    if re.search(
        r"\b(design|customer|peer|product|user|buyer|seller)\s+feedback\b",
        low,
    ):
        return True
    if re.search(
        r"\b(leave|write|post|submit|give)\s+(a\s+)?(reviews?|feedback)\b",
        low,
    ):
        return True
    if re.search(r"\b(customer|peer|product|user|buyer|seller)\s+reviews?\b", low):
        return True
    return False


def topic_questions(spec_text: str, entities: list[Any]) -> list[dict[str, str]]:
    """Payment / cancel / notify / review / messaging topic probes (non-cardinality)."""
    low = spec_text.lower()
    questions: list[dict[str, str]] = []
    if re.search(r"\b(pay|payment)\b", low) and not re.search(
        r"\b(escrow|upfront|completion|booking)\b", low
    ):
        questions.append(
            {
                "topic": "payment_flow",
                "question": (
                    "When is payment collected - at booking, at start of service, or at completion?"
                ),
                "impact": "Affects payment state machine and process flow",
            }
        )
    if re.search(r"\b(book|request|order)\b", low) and not re.search(r"\b(cancel|refund)\b", low):
        questions.append(
            {
                "topic": "cancellation",
                "question": "What happens if someone cancels? Are there refund rules?",
                "impact": "Affects state machine transitions and financial rules",
            }
        )
    if isinstance(entities, list) and len(entities) >= 2:
        questions.append(
            {
                "topic": "notifications",
                "question": "Should users receive email/push notifications for key events?",
                "impact": "Affects whether to add notification triggers",
            }
        )
    if bilateral_review_signal(low):
        questions.append(
            {
                "topic": "reviews",
                "question": "Can both parties leave reviews, or just one side?",
                "impact": "Affects Review entity design and who can create",
            }
        )
    if not re.search(r"\b(message|chat|communicate)\b", low):
        questions.append(
            {
                "topic": "communication",
                "question": "Do users need to message each other within the app?",
                "impact": "Major feature decision - adds Message entity and real-time requirements",
            }
        )
    return questions


def build_clarification_questions(
    spec_text: str, entities: list[Any] | None = None
) -> list[dict[str, str]]:
    """Cardinality + topic probes for a founder brief / narrative spec."""
    entity_list = entities if isinstance(entities, list) else []
    return cardinality_questions(spec_text, entity_list) + topic_questions(spec_text, entity_list)
