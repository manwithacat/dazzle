"""Site page JavaScript for the Dazzle runtime.

Serves ``static/js/site.js`` for the ``/site.js`` route. The marketing
shell itself renders through the typed Fragment substrate (ADR-0023).
"""


def get_site_js() -> str:
    """
    Get the site page JavaScript content.

    This JS handles theme toggling, Lucide icon initialization,
    and hash-based scrolling for marketing page sections.

    Returns:
        JavaScript content for /site.js route
    """
    from pathlib import Path

    js_path = Path(__file__).resolve().parent.parent / "static" / "js" / "site.js"
    return js_path.read_text(encoding="utf-8")
