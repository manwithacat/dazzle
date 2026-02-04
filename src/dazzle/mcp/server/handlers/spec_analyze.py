"""
Spec Analysis handlers for the cognition pass.

Transforms a rough narrative spec into structured requirements
before DSL generation. Operations:

- discover_entities: Extract nouns and relationships from narrative
- identify_lifecycles: Identify state transitions for entities
- extract_personas: Identify user roles and their needs
- surface_rules: Extract implicit business rules
- generate_questions: Surface ambiguities that need clarification
- refine_spec: Produce a structured refined spec from narrative
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def handle_spec_analyze(arguments: dict[str, Any]) -> str:
    """Handle spec_analyze tool calls."""
    operation = arguments.get("operation")

    if operation == "discover_entities":
        return _discover_entities(arguments)
    elif operation == "identify_lifecycles":
        return _identify_lifecycles(arguments)
    elif operation == "extract_personas":
        return _extract_personas(arguments)
    elif operation == "surface_rules":
        return _surface_rules(arguments)
    elif operation == "generate_questions":
        return _generate_questions(arguments)
    elif operation == "refine_spec":
        return _refine_spec(arguments)
    else:
        return json.dumps({"error": f"Unknown operation: {operation}"})


def _discover_entities(arguments: dict[str, Any]) -> str:
    """
    Extract potential entities from narrative spec text.

    Uses pattern matching to identify:
    - Nouns that appear as subjects/objects (potential entities)
    - Relationships between nouns (ref fields)
    - User roles (special entity type)
    - Actions (potential state transitions or services)
    """
    spec_text = arguments.get("spec_text", "")

    if not spec_text:
        return json.dumps({"error": "spec_text is required"})

    # Common patterns for entity discovery
    # These are heuristics, not perfect NLP

    # Find capitalized nouns (likely entity names)
    capitalized = set(re.findall(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)*)\b", spec_text))

    # Find nouns after articles (a/an/the) - likely entities
    article_nouns = set(re.findall(r"\b(?:a|an|the)\s+([a-z]+(?:\s+[a-z]+)?)\b", spec_text.lower()))

    # Find role-like words (owner, user, admin, customer, etc.)
    role_patterns = re.findall(
        r"\b(owner|user|admin|customer|seller|buyer|manager|staff|employee|member|guest|visitor|sitter|driver|host)\w*\b",
        spec_text.lower(),
    )
    roles = set(role_patterns)

    # Find action verbs that suggest state transitions
    action_patterns = re.findall(
        r"\b(create|post|submit|approve|reject|cancel|complete|assign|accept|decline|review|pay|ship|deliver)\w*\b",
        spec_text.lower(),
    )
    actions = set(action_patterns)

    # Find relationship patterns (X's Y, X has Y, X belongs to Y)
    possessives = re.findall(r"(\w+)'s\s+(\w+)", spec_text.lower())
    has_relations = re.findall(r"(\w+)\s+(?:has|have|contain|include)\s+(\w+)", spec_text.lower())
    belongs_relations = re.findall(
        r"(\w+)\s+(?:belongs?\s+to|owned?\s+by)\s+(\w+)", spec_text.lower()
    )

    # Build entity candidates
    entities = []

    # Add roles as User-type entities
    for role in roles:
        entities.append(
            {
                "name": role.title(),
                "type": "user_role",
                "source": "role_pattern",
                "suggested_fields": ["email", "name", "created_at"],
            }
        )

    # Add capitalized nouns as potential entities
    skip_words = {"App", "The", "This", "We", "They", "Our", "And", "For", "With"}
    for noun in capitalized:
        if noun not in skip_words and noun.lower() not in roles:
            entities.append(
                {
                    "name": noun,
                    "type": "domain_entity",
                    "source": "capitalized_noun",
                    "suggested_fields": ["id", "created_at"],
                }
            )

    # Add article nouns that look like entities
    common_words = {"app", "system", "platform", "way", "time", "day", "week", "side", "job"}
    for noun in article_nouns:
        normalized = noun.replace(" ", "_")
        if normalized not in common_words and normalized not in [
            e["name"].lower() for e in entities
        ]:
            entities.append(
                {
                    "name": normalized.title().replace("_", ""),
                    "type": "domain_entity",
                    "source": "article_noun",
                    "suggested_fields": ["id", "created_at"],
                }
            )

    # Build relationships
    relationships = []
    for owner, owned in possessives + has_relations:
        relationships.append(
            {
                "from": owner.title(),
                "to": owned.title(),
                "type": "has_many" if owned.endswith("s") else "has_one",
            }
        )

    for child, parent in belongs_relations:
        relationships.append(
            {
                "from": child.title(),
                "to": parent.title(),
                "type": "belongs_to",
            }
        )

    return json.dumps(
        {
            "entities": entities,
            "relationships": relationships,
            "actions": list(actions),
            "hint": "Review and refine these candidates. Remove false positives, add missing entities.",
        },
        indent=2,
    )


def _identify_lifecycles(arguments: dict[str, Any]) -> str:
    """
    Identify state transitions for entities.

    Takes discovered entities and the spec text, returns
    suggested state machines.
    """
    spec_text = arguments.get("spec_text", "")
    entities = arguments.get("entities", [])

    if not spec_text:
        return json.dumps({"error": "spec_text is required"})

    # Common lifecycle patterns
    lifecycle_keywords = {
        "order": ["pending", "confirmed", "processing", "shipped", "delivered", "cancelled"],
        "request": ["draft", "submitted", "pending", "approved", "rejected", "completed"],
        "application": ["submitted", "under_review", "accepted", "rejected", "withdrawn"],
        "booking": ["pending", "confirmed", "in_progress", "completed", "cancelled"],
        "payment": ["pending", "processing", "completed", "failed", "refunded"],
        "task": ["pending", "assigned", "in_progress", "completed", "blocked"],
        "ticket": ["open", "in_progress", "resolved", "closed", "reopened"],
        "listing": ["draft", "active", "paused", "sold", "expired"],
        "job": ["open", "assigned", "in_progress", "completed", "cancelled"],
    }

    # Find action words that suggest transitions
    transition_words = re.findall(
        r"\b(post|submit|approve|reject|cancel|complete|assign|accept|decline|confirm|ship|deliver|pay|review|start|finish|close)\w*\b",
        spec_text.lower(),
    )

    lifecycles = []

    for entity in entities:
        entity_name = entity if isinstance(entity, str) else entity.get("name", "")
        entity_lower = entity_name.lower()

        # Check if entity matches known lifecycle patterns
        matched_pattern = None
        for pattern_name, states in lifecycle_keywords.items():
            if pattern_name in entity_lower or entity_lower in pattern_name:
                matched_pattern = states
                break

        if matched_pattern:
            lifecycles.append(
                {
                    "entity": entity_name,
                    "status_field": "status",
                    "states": matched_pattern,
                    "source": "pattern_match",
                }
            )
        elif any(word in entity_lower for word in ["request", "order", "booking", "job"]):
            # Generic request-like lifecycle
            lifecycles.append(
                {
                    "entity": entity_name,
                    "status_field": "status",
                    "states": ["pending", "active", "completed", "cancelled"],
                    "source": "generic_pattern",
                }
            )

    # Also suggest lifecycles based on transition words found
    if transition_words and not lifecycles:
        lifecycles.append(
            {
                "entity": "UNKNOWN",
                "status_field": "status",
                "suggested_transitions": list(set(transition_words)),
                "hint": "These actions suggest state transitions. Assign to appropriate entities.",
            }
        )

    return json.dumps(
        {
            "lifecycles": lifecycles,
            "detected_transitions": list(set(transition_words)),
            "hint": "Add state machines to entities with clear lifecycles. Not every entity needs one.",
        },
        indent=2,
    )


def _extract_personas(arguments: dict[str, Any]) -> str:
    """
    Identify user personas from the spec.

    Personas include their goals, primary actions, and information needs.
    """
    spec_text = arguments.get("spec_text", "")

    if not spec_text:
        return json.dumps({"error": "spec_text is required"})

    # Role patterns
    role_patterns = [
        (r"\b(owner)s?\b", "Owner", "Person who owns/creates primary content"),
        (r"\b(customer)s?\b", "Customer", "Person who purchases/consumes"),
        (r"\b(seller)s?\b", "Seller", "Person who sells/provides"),
        (r"\b(buyer)s?\b", "Buyer", "Person who purchases"),
        (r"\b(admin)(?:istrator)?s?\b", "Admin", "System administrator"),
        (r"\b(manager)s?\b", "Manager", "Oversees operations"),
        (r"\b(staff|employee)s?\b", "Staff", "Internal team member"),
        (r"\b(user)s?\b", "User", "Generic system user"),
        (r"\b(guest|visitor)s?\b", "Guest", "Unauthenticated visitor"),
        (r"\b(host)s?\b", "Host", "Person who hosts/provides space"),
        (r"\b(sitter)s?\b", "Sitter", "Person who provides sitting services"),
        (r"\b(driver)s?\b", "Driver", "Person who provides transport"),
        (r"\b(provider)s?\b", "Provider", "Person who provides services"),
        (r"\b(member)s?\b", "Member", "Registered community member"),
    ]

    found_personas = []
    for pattern, name, description in role_patterns:
        if re.search(pattern, spec_text.lower()):
            # Find actions associated with this role
            role_sentences = [s for s in spec_text.split(".") if re.search(pattern, s.lower())]
            actions = []
            for sentence in role_sentences:
                verbs = re.findall(
                    r"\b(create|post|browse|search|apply|select|pay|review|manage|view|edit|delete|approve|reject)\w*\b",
                    sentence.lower(),
                )
                actions.extend(verbs)

            found_personas.append(
                {
                    "name": name,
                    "description": description,
                    "primary_actions": list(set(actions)) or ["view", "manage"],
                    "suggested_workspace": f"{name.lower()}_dashboard",
                }
            )

    # Always suggest admin if not found
    if not any(p["name"] == "Admin" for p in found_personas):
        found_personas.append(
            {
                "name": "Admin",
                "description": "Platform administrator (implicit)",
                "primary_actions": ["monitor", "manage", "configure"],
                "suggested_workspace": "admin_dashboard",
            }
        )

    return json.dumps(
        {
            "personas": found_personas,
            "hint": "Each persona should have a workspace with surfaces tailored to their needs.",
        },
        indent=2,
    )


def _surface_rules(arguments: dict[str, Any]) -> str:
    """
    Extract business rules from the spec.

    Looks for:
    - Percentage/fee calculations
    - Constraints (must, cannot, only)
    - Validation rules
    - Derived values
    """
    spec_text = arguments.get("spec_text", "")

    if not spec_text:
        return json.dumps({"error": "spec_text is required"})

    rules = []

    # Percentage patterns (e.g., "15% fee", "take 20%")
    percentages = re.findall(r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(\w+)?", spec_text)
    for pct, context in percentages:
        rules.append(
            {
                "type": "fee_calculation",
                "value": f"{pct}%",
                "context": context or "unknown",
                "dsl_hint": f"computed field with formula: amount * {float(pct) / 100}",
            }
        )

    # Constraint patterns
    must_patterns = re.findall(r"must\s+(\w+(?:\s+\w+){0,5})", spec_text.lower())
    cannot_patterns = re.findall(
        r"(?:cannot|can't|must not)\s+(\w+(?:\s+\w+){0,5})", spec_text.lower()
    )
    only_patterns = re.findall(r"only\s+(\w+(?:\s+\w+){0,5})", spec_text.lower())

    for constraint in must_patterns:
        rules.append(
            {
                "type": "constraint",
                "rule": f"must {constraint}",
                "dsl_hint": "Consider invariant or guard",
            }
        )

    for constraint in cannot_patterns:
        rules.append(
            {
                "type": "constraint",
                "rule": f"cannot {constraint}",
                "dsl_hint": "Consider invariant with negation",
            }
        )

    for constraint in only_patterns:
        rules.append(
            {
                "type": "constraint",
                "rule": f"only {constraint}",
                "dsl_hint": "Consider permission or guard",
            }
        )

    # Time-based rules
    time_patterns = re.findall(
        r"(?:within|after|before)\s+(\d+)\s*(hour|day|week|minute)s?",
        spec_text.lower(),
    )
    for value, unit in time_patterns:
        rules.append(
            {
                "type": "time_constraint",
                "value": f"{value} {unit}s",
                "dsl_hint": "Consider timeout in process or computed date field",
            }
        )

    # Payment/money patterns
    if re.search(r"\b(pay|payment|charge|fee|cost|price|amount)\b", spec_text.lower()):
        rules.append(
            {
                "type": "financial",
                "rule": "System handles payments",
                "dsl_hint": "Use money field type, consider ledger for complex transactions",
            }
        )

    return json.dumps(
        {
            "business_rules": rules,
            "hint": "Translate these rules into invariants, computed fields, or process guards.",
        },
        indent=2,
    )


def _generate_questions(arguments: dict[str, Any]) -> str:
    """
    Generate clarification questions for ambiguities.

    These are genuine questions that affect implementation,
    not obvious things.
    """
    spec_text = arguments.get("spec_text", "")
    entities = arguments.get("entities", [])

    if not spec_text:
        return json.dumps({"error": "spec_text is required"})

    questions = []

    # Check for plural ambiguity (one-to-many vs one-to-one)
    plurals = re.findall(r"\b(\w+)s\s+(?:and|or)\s+(\w+)s?\b", spec_text.lower())
    for word1, word2 in plurals:
        questions.append(
            {
                "topic": "cardinality",
                "question": f"Can a {word1} have multiple {word2}s, or just one?",
                "impact": "Affects whether to use ref() or list of refs",
            }
        )

    # Check for missing payment flow details
    if re.search(r"\b(pay|payment)\b", spec_text.lower()):
        if not re.search(r"\b(escrow|upfront|completion|booking)\b", spec_text.lower()):
            questions.append(
                {
                    "topic": "payment_flow",
                    "question": "When is payment collected - at booking, at start of service, or at completion?",
                    "impact": "Affects payment state machine and process flow",
                }
            )

    # Check for missing cancellation handling
    if re.search(r"\b(book|request|order)\b", spec_text.lower()):
        if not re.search(r"\b(cancel|refund)\b", spec_text.lower()):
            questions.append(
                {
                    "topic": "cancellation",
                    "question": "What happens if someone cancels? Are there refund rules?",
                    "impact": "Affects state machine transitions and financial rules",
                }
            )

    # Check for notification ambiguity
    if len(entities) >= 2:
        questions.append(
            {
                "topic": "notifications",
                "question": "Should users receive email/push notifications for key events?",
                "impact": "Affects whether to add notification triggers",
            }
        )

    # Check for rating/review system
    if re.search(r"\b(review|rating|feedback)\b", spec_text.lower()):
        questions.append(
            {
                "topic": "reviews",
                "question": "Can both parties leave reviews, or just one side?",
                "impact": "Affects Review entity design and who can create",
            }
        )

    # Check for messaging
    if not re.search(r"\b(message|chat|communicate)\b", spec_text.lower()):
        questions.append(
            {
                "topic": "communication",
                "question": "Do users need to message each other within the app?",
                "impact": "Major feature decision - adds Message entity and real-time requirements",
            }
        )

    return json.dumps(
        {
            "questions": questions,
            "hint": "Answer these before generating DSL. Assumptions affect architecture.",
        },
        indent=2,
    )


def _refine_spec(arguments: dict[str, Any]) -> str:
    """
    Produce a structured refined spec from all analyses.

    This combines the outputs of other operations into
    a coherent specification document.
    """
    spec_text = arguments.get("spec_text", "")
    answers = arguments.get("answers", {})  # Answers to generated questions

    if not spec_text:
        return json.dumps({"error": "spec_text is required"})

    # Run all analyses
    entities_result = json.loads(_discover_entities({"spec_text": spec_text}))
    lifecycles_result = json.loads(
        _identify_lifecycles(
            {
                "spec_text": spec_text,
                "entities": entities_result.get("entities", []),
            }
        )
    )
    personas_result = json.loads(_extract_personas({"spec_text": spec_text}))
    rules_result = json.loads(_surface_rules({"spec_text": spec_text}))

    # Build refined spec
    refined = {
        "original_spec": spec_text,
        "entities": [],
        "state_machines": [],
        "personas": personas_result.get("personas", []),
        "business_rules": rules_result.get("business_rules", []),
        "answered_questions": answers,
    }

    # Process entities
    for entity in entities_result.get("entities", []):
        entity_name = entity.get("name", "")

        # Find lifecycle for this entity
        lifecycle = None
        for lc in lifecycles_result.get("lifecycles", []):
            if lc.get("entity") == entity_name:
                lifecycle = lc
                break

        refined_entity = {
            "name": entity_name,
            "type": entity.get("type", "domain_entity"),
            "fields": entity.get("suggested_fields", []),
        }

        if lifecycle:
            refined_entity["has_lifecycle"] = True
            refined_entity["status_states"] = lifecycle.get("states", [])
            refined["state_machines"].append(
                {
                    "entity": entity_name,
                    "field": "status",
                    "states": lifecycle.get("states", []),
                }
            )

        refined["entities"].append(refined_entity)

    # Add relationships
    refined["relationships"] = entities_result.get("relationships", [])

    return json.dumps(refined, indent=2)
