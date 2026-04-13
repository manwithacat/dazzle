"""Dev persona provisioning for QA mode (#768).

Called from serve_command when --local is active. Creates a dev user
for each DSL persona so testers can log in as any of them via magic
links.

Dev personas:
- Email: {persona_id}@example.test (RFC2606 reserved TLD)
- Role: persona_id (used as the role name — Dazzle apps typically
  name roles after their persona slugs)
- Password: None (magic link only — there's no way to log in without
  hitting the dev-gated generator endpoint)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProvisionedPersona:
    """A dev user that was provisioned (or already existed) for a persona."""

    persona_id: str
    display_name: str
    email: str
    user_id: str
    description: str
    stories: list[str] = field(default_factory=list)


def provision_dev_personas(
    appspec: Any,
    auth_store: Any,
) -> list[ProvisionedPersona]:
    """Ensure a dev user exists for every DSL persona. Idempotent.

    Returns the list of (new or existing) dev personas for the QA panel.
    Failures are logged to stderr but don't raise — a broken persona
    shouldn't block the dev workflow.
    """
    personas = getattr(appspec, "personas", None) or []
    if not personas:
        return []

    provisioned: list[ProvisionedPersona] = []
    for persona in personas:
        try:
            result = _provision_one(persona, appspec, auth_store)
            if result is not None:
                provisioned.append(result)
        except Exception as err:
            print(
                f"Warning: failed to provision dev persona '{getattr(persona, 'id', '?')}': {err}",
                file=sys.stderr,
            )
            continue

    return provisioned


def _provision_one(
    persona: Any,
    appspec: Any,
    auth_store: Any,
) -> ProvisionedPersona | None:
    """Provision a single persona; return None if skipped."""
    persona_id = getattr(persona, "id", None)
    if not persona_id:
        return None

    display_name = _persona_display_name(persona)
    description = _derive_description(persona)
    email = f"{persona_id}@example.test"

    existing = auth_store.get_user_by_email(email)
    if existing is not None:
        return ProvisionedPersona(
            persona_id=persona_id,
            display_name=display_name,
            email=email,
            user_id=str(existing.id),
            description=description,
            stories=_derive_stories(appspec, persona_id),
        )

    user = auth_store.create_user(
        email=email,
        password=None,  # magic-link only — no password
        username=display_name,
        is_superuser=False,
        roles=[persona_id],
    )
    return ProvisionedPersona(
        persona_id=persona_id,
        display_name=display_name,
        email=email,
        user_id=str(user.id),
        description=description,
        stories=_derive_stories(appspec, persona_id),
    )


def _persona_display_name(persona: Any) -> str:
    """Return the persona's display name. Uses label, falls back to id."""
    label = getattr(persona, "label", None)
    if label:
        return str(label)
    persona_id = getattr(persona, "id", "unknown")
    return str(persona_id).replace("_", " ").title()


def _derive_description(persona: Any) -> str:
    """Return persona description from DSL or a sensible fallback."""
    description = getattr(persona, "description", None)
    if description:
        return str(description)
    return "Test persona — explore the app with this role's permissions"


def _derive_stories(appspec: Any, persona_id: str) -> list[str]:
    """Return up to 2 story titles where this persona is the actor."""
    stories = getattr(appspec, "stories", None) or []
    relevant: list[str] = []
    for story in stories:
        actor = getattr(story, "actor", None)
        if actor != persona_id:
            continue
        title = getattr(story, "title", None) or getattr(story, "story_id", None)
        if title:
            relevant.append(title)
        if len(relevant) >= 2:
            break
    return relevant
