"""
Static page serving for DNR container runtime.

Provides endpoints for serving static pages (privacy, terms, etc.)
from the UI spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from .markdown import markdown_to_html


def register_page_routes(
    app: FastAPI,
    ui_spec: dict[str, Any],
    static_pages_dir: Path = Path("/app/static/pages"),
) -> None:
    """
    Register static page routes on the FastAPI app.

    Args:
        app: FastAPI application instance
        ui_spec: UI specification dict
        static_pages_dir: Directory containing static page files
    """
    pages = ui_spec.get("shell", {}).get("pages", [])

    def get_static_page(route: str) -> dict[str, Any] | None:
        """Find static page by route."""
        for page in pages:
            if page.get("route") == route:
                result: dict[str, Any] = page
                return result
        return None

    @app.get("/pages/{path:path}", tags=["Pages"], summary="Get page content")
    async def serve_static_page(path: str) -> dict[str, Any]:
        """Serve static page content."""
        route = f"/{path}"
        page = get_static_page(route)

        if not page:
            raise HTTPException(status_code=404, detail="Page not found")

        # Check if we have inline content
        content = page.get("content")
        if content:
            # Content is already HTML or markdown
            if not content.strip().startswith("<"):
                content = markdown_to_html(content)
            return {"title": page.get("title", ""), "content": content}

        # Check for source file (in static/pages/)
        src = page.get("src")
        if src:
            # Try to find the source file
            page_file = static_pages_dir / Path(src).name
            if page_file.exists():
                file_content = page_file.read_text()
                # Convert markdown if needed
                if src.endswith(".md"):
                    file_content = markdown_to_html(file_content)
                return {"title": page.get("title", ""), "content": file_content}

        # Return placeholder content
        return {
            "title": page.get("title", "Page"),
            "content": f"<p>Content for {route} is not yet available.</p>",
        }
