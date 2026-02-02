"""
String utility functions for DNR container.

Provides pluralization for API route generation.
This is a standalone copy to avoid dazzle package dependency in containers.
"""

from __future__ import annotations

import re

# Irregular plurals that don't follow standard rules
_IRREGULAR_PLURALS = {
    "person": "people",
    "child": "children",
    "man": "men",
    "woman": "women",
    "foot": "feet",
    "tooth": "teeth",
    "goose": "geese",
    "mouse": "mice",
    "ox": "oxen",
    "datum": "data",
    "medium": "media",
    "criterion": "criteria",
    "phenomenon": "phenomena",
    "index": "indices",
    "appendix": "appendices",
    "matrix": "matrices",
    "vertex": "vertices",
    # Common domain-specific terms
    "status": "statuses",
    "address": "addresses",
}


def pluralize(word: str) -> str:
    """
    Convert a singular English word to its plural form.

    Handles common English pluralization rules including:
    - Words ending in -y (policy -> policies, but key -> keys)
    - Words ending in -s, -x, -z, -ch, -sh (bus -> buses)
    - Words ending in -f/-fe (leaf -> leaves)
    - Irregular plurals (person -> people)

    Args:
        word: Singular word to pluralize

    Returns:
        Plural form of the word
    """
    if not word:
        return word

    # Preserve original case for checking, work with lowercase
    lower_word = word.lower()

    # Check irregular plurals
    if lower_word in _IRREGULAR_PLURALS:
        plural = _IRREGULAR_PLURALS[lower_word]
        # Preserve original capitalization pattern
        if word[0].isupper():
            return plural.capitalize()
        return plural

    # Handle CamelCase - extract the last word for pluralization
    # e.g., IBGPolicy -> IBG + Policy -> IBG + Policies
    camel_match = re.match(r"^(.+)([A-Z][a-z]+)$", word)
    if camel_match:
        prefix, last_word = camel_match.groups()
        if prefix and last_word != word:
            return prefix + pluralize(last_word)

    # Standard pluralization rules
    if lower_word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    elif lower_word.endswith("y"):
        if len(word) > 1 and lower_word[-2] in "aeiou":
            return word + "s"
        else:
            return word[:-1] + "ies"
    elif lower_word.endswith("f"):
        if lower_word.endswith(("elf", "alf", "olf", "eaf", "oaf", "arf")):
            return word[:-1] + "ves"
        return word + "s"
    elif lower_word.endswith("fe"):
        return word[:-2] + "ves"
    elif lower_word.endswith("o"):
        if lower_word.endswith(("hero", "potato", "tomato", "echo", "veto")):
            return word + "es"
        return word + "s"
    else:
        return word + "s"


def to_api_plural(entity_name: str) -> str:
    """
    Convert an entity name to its API endpoint plural form.

    Args:
        entity_name: Entity name (e.g., "Task", "IBGPolicy")

    Returns:
        Lowercase plural for API routes (e.g., "tasks", "ibgpolicies")
    """
    return pluralize(entity_name).lower()
