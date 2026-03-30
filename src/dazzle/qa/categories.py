"""Evaluation categories for the Dazzle visual QA toolkit."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """A named evaluation category for visual QA inspection."""

    id: str
    definition: str
    example: str
    severity_default: str


CATEGORIES: list[Category] = [
    Category(
        id="text_wrapping",
        definition="Text that wraps awkwardly, breaking words or names across lines",
        example="A student name like 'Jonathan Bartholomew' split across two lines inside a narrow badge",
        severity_default="medium",
    ),
    Category(
        id="truncation",
        definition="Content cut off or hidden by container boundaries",
        example="A task title ending in '...' with no tooltip or way to reveal the full text",
        severity_default="medium",
    ),
    Category(
        id="title_formatting",
        definition="Card or region titles inline with content instead of above",
        example="A card header 'Assignments' appearing on the same line as the first assignment row",
        severity_default="high",
    ),
    Category(
        id="column_layout",
        definition="Columns too narrow, data cramped or overlapping",
        example="A date column wide enough only for 'MM/DD' showing '03/28' and cutting off the year",
        severity_default="medium",
    ),
    Category(
        id="empty_state",
        definition="Regions showing no data without helpful messaging",
        example="A table body that is completely blank with no 'No results found' message",
        severity_default="low",
    ),
    Category(
        id="alignment",
        definition="Misaligned elements, uneven spacing between components",
        example="Action buttons at inconsistent vertical positions across a list of cards",
        severity_default="low",
    ),
    Category(
        id="readability",
        definition="Font too small, poor contrast, or information density too high",
        example="Secondary metadata rendered at 10px in light grey on a white background",
        severity_default="medium",
    ),
    Category(
        id="data_quality",
        definition="Raw UUIDs, None values, internal field names, or raw dicts visible to users",
        example="A Student column displaying '3fa85f64-5717-4562-b3fc-2c963f66afa6' instead of the student name",
        severity_default="high",
    ),
]

_CATEGORY_INDEX: dict[str, Category] = {c.id: c for c in CATEGORIES}


def get_category(category_id: str) -> Category | None:
    """Look up a category by its id. Returns None if not found."""
    return _CATEGORY_INDEX.get(category_id)
