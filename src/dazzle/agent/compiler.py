"""CRUD-action inference for discovery gaps.

``infer_crud_action`` names the CRUD verb a gap description refers to; the
headless persona-journey analysis (``discovery(operation=coherence)``) uses it
to label missing-surface gaps.
"""


def infer_crud_action(text: str) -> str:
    """Infer which CRUD action is referenced in descriptive text."""
    text = text.lower()
    if "delete" in text or "remove" in text:
        return "delete"
    if "create" in text or "add" in text or "new" in text:
        return "create"
    if "edit" in text or "update" in text or "modify" in text:
        return "edit"
    if "list" in text or "browse" in text or "index" in text:
        return "list"
    if "view" in text or "detail" in text or "show" in text:
        return "view"
    return "CRUD"
