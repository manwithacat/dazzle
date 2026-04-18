"""Realistic seed-value generation for UX verification and form-filling.

Shared helper used by :mod:`dazzle.testing.ux.fixtures` (the
``/__test__/seed`` payload generator) and :mod:`dazzle.testing.ux.runner`
(the Playwright form-filler). Both previously emitted obviously
artificial strings like ``"Test first_name 1"`` and
``"UX first_name 2f828c"``, which trials consistently flagged as
"unprofessional" (#809).

This helper uses :mod:`faker` with field-name hints so the same field
name (``first_name``, ``email``, ``title``, …) gets the same kind of
realistic value across seed and form-fill paths. The mapping is a
subset of the one in :class:`dazzle_back.demo_data.generator.DemoDataGenerator`
— we deliberately don't share code with that module because it takes
full ``FieldSpec`` objects while the UX paths only have ``(name,
max_length)`` by the time they need a value.
"""

from __future__ import annotations

try:
    from faker import Faker

    _faker: Faker | None = Faker()
except ImportError:  # pragma: no cover — dep is required in pyproject
    _faker = None


# Deterministic per-process so reports/snapshots don't churn.
# Callers that need per-run entropy can instantiate their own Faker.
if _faker is not None:
    Faker.seed(0)


# ---------------------------------------------------------------------------
# Field-name → faker-method mapping
# ---------------------------------------------------------------------------

# Intentionally a dict-of-tuples rather than if-elif so the coverage
# is visible at a glance. Keys are lower-cased exact field names and
# common variants.
_NAME_HINTS: dict[tuple[str, ...], str] = {
    ("name", "full_name", "fullname"): "name",
    ("first_name", "firstname", "given_name"): "first_name",
    ("last_name", "lastname", "surname", "family_name"): "last_name",
    ("company", "company_name", "organization", "organisation", "org"): "company",
    ("email", "email_address"): "email",
    ("phone", "phone_number", "telephone", "mobile", "tel"): "phone",
    ("address", "street_address", "street"): "street_address",
    ("city", "town"): "city",
    ("state", "province", "region"): "state",
    ("country", "country_name"): "country",
    ("zip", "zip_code", "postal_code", "postcode"): "postcode",
    ("title", "subject", "heading", "headline"): "sentence_short",
    ("description", "summary", "notes", "content", "body", "details"): "paragraph",
    ("url", "website", "link", "homepage"): "url",
    ("username", "user_name", "login", "handle"): "user_name",
}


def _lookup_faker_method(field_name: str) -> str | None:
    lname = field_name.lower()
    for keys, method in _NAME_HINTS.items():
        if lname in keys:
            return method
    return None


def realistic_str(
    field_name: str,
    index: int = 0,
    max_length: int | None = None,
) -> str:
    """Return a realistic-looking string for a field.

    Args:
        field_name: Raw field name from the DSL (case is normalised).
        index: Used as a fallback ordinal when the field has no name
            hint — keeps multiple rows distinguishable.
        max_length: Optional ceiling; result is truncated if exceeded.

    Falls back to ``f"Example {field_name} {index+1}"`` when faker is
    unavailable or no name hint matched. This fallback is still more
    readable than the old ``"Test first_name 1"`` / ``"UX Edited Value"``
    strings — the key word "Example" signals demo-ness without looking
    like a placeholder a developer forgot to replace.
    """
    if _faker is not None:
        method = _lookup_faker_method(field_name)
        if method == "name":
            value = _faker.name()
        elif method == "first_name":
            value = _faker.first_name()
        elif method == "last_name":
            value = _faker.last_name()
        elif method == "company":
            value = _faker.company()
        elif method == "email":
            value = _faker.email()
        elif method == "phone":
            value = _faker.phone_number()[:20]
        elif method == "street_address":
            value = _faker.street_address()
        elif method == "city":
            value = _faker.city()
        elif method == "state":
            value = _faker.state() if hasattr(_faker, "state") else _faker.city()
        elif method == "country":
            value = _faker.country()
        elif method == "postcode":
            value = _faker.postcode()
        elif method == "sentence_short":
            value = _faker.sentence(nb_words=4).rstrip(".")
        elif method == "paragraph":
            value = _faker.paragraph()
        elif method == "url":
            value = _faker.url()
        elif method == "user_name":
            value = _faker.user_name()
        else:
            # Faker available but no name hint — use a short sentence
            # which reads as realistic-but-generic.
            value = _faker.sentence(nb_words=3).rstrip(".")
    else:
        # Faker missing — use the "Example" prefix so strings look
        # intentional rather than leaked from a fixture.
        pretty = field_name.replace("_", " ").title()
        value = f"Example {pretty} {index + 1}"

    if max_length is not None and len(value) > max_length:
        value = value[:max_length]
    return value


def realistic_email(entity_name: str, index: int = 0) -> str:
    """Return a realistic-looking email address.

    Uses faker when available. Keeps the entity name in the domain so
    seed fixtures per entity remain visually distinguishable — a nod
    to the previous ``uxv-1@{entity}.test`` pattern that was useful
    for debugging even if it looked artificial.
    """
    if _faker is not None:
        # Faker gives us a plausible local-part; we pin the domain so
        # each entity's rows cluster visually in the UI.
        local = _faker.user_name()
        return f"{local}@{entity_name.lower()}.test"
    return f"example{index + 1}@{entity_name.lower()}.test"
