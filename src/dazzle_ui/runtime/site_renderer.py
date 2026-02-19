"""
Site page renderer for DNR runtime.

Primary rendering is now handled by Jinja2 templates in ``templates/site/``.
This module retains:
- Task context injection functions (used by human task workflow)
- ``get_shared_head_html()`` (used by task surface pages)
- ``get_site_js()`` (serves the site.js static file)
"""

from __future__ import annotations

import json

from dazzle_ui.runtime.task_context import TaskContext


def get_shared_head_html(title: str, *, custom_css: bool = False) -> str:
    """
    Return shared <head> content for all DNR pages.

    Provides unified styling between site pages and workspace pages by including
    the same DaisyUI + Tailwind CSS/JS as the workspace renderer.

    Args:
        title: Page title
        custom_css: If True, include a link to ``/static/css/custom.css`` after
            the Dazzle design-system stylesheet.  The caller is responsible for
            checking that the file actually exists on disk.

    Returns:
        HTML string for the <head> section (without opening/closing tags)
    """
    custom_css_link = (
        '\n    <!-- Project custom CSS -->\n    <link rel="stylesheet" href="/static/css/custom.css">'
        if custom_css
        else ""
    )
    return f"""<meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="icon" href="/static/assets/dazzle-favicon.svg" type="image/svg+xml">
    <!-- Inter font -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <!-- DaisyUI - semantic component classes (same as workspace) -->
    <link href="https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css" rel="stylesheet" type="text/css" />
    <!-- Tailwind Browser - minimal utilities for layout -->
    <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
    <!-- DAZZLE design system layer -->
    <link rel="stylesheet" href="/styles/dazzle.css">{custom_css_link}
    <!-- Lucide icons for feature/section icons -->
    <script src="https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js"></script>"""


# =========================================================================
# Task Context Injection Functions
# =========================================================================


def render_task_context_script(task_context: TaskContext | None) -> str:
    """
    Render a script tag containing task context data.

    This script tag is injected into pages that are rendered as part
    of a human task workflow, enabling the task-header.js component
    to display task information and outcome buttons.

    Args:
        task_context: TaskContext instance or None

    Returns:
        HTML script tag with task context JSON, or empty string
    """
    if not task_context:
        return ""

    context_json = json.dumps(task_context.to_dict())

    return f"""<script type="application/json" id="task-context">
{context_json}
</script>
<script src="/js/components/task-header.js" type="module"></script>"""


def render_task_surface_page(
    surface_name: str,
    entity_id: str,
    task_context: TaskContext,
    surface_html: str,
    product_name: str = "My App",
) -> str:
    """
    Render a surface page with task context for human task workflow.

    This wraps a surface's HTML content with task header/footer components
    and injects the TaskContext for JavaScript to use.

    Args:
        surface_name: Name of the surface being rendered
        entity_id: ID of the entity being displayed
        task_context: TaskContext with task information and outcomes
        surface_html: The rendered surface HTML content
        product_name: Application name for title

    Returns:
        Complete HTML page with task context injection
    """
    task_script = render_task_context_script(task_context)
    title = f"Task: {task_context.step_name} - {product_name}"

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    {get_shared_head_html(title)}
</head>
<body class="dz-site bg-base-100">
    <header class="dz-site-header">
        <nav class="dz-site-nav">
            <a href="/workspaces/tasks" class="dz-site-logo">{product_name}</a>
            <div class="dz-nav-items">
                <a href="/workspaces/tasks" class="dz-nav-link">My Tasks</a>
            </div>
        </nav>
    </header>

    <main class="dz-task-surface-container">
        <div class="surface-container" data-surface="{surface_name}" data-entity-id="{entity_id}">
            {surface_html}
        </div>
    </main>

    {task_script}
</body>
</html>"""


def get_task_header_script_tag() -> str:
    """
    Get script tag for task header component.

    Include this in pages that may render with task context.
    """
    return '<script src="/js/components/task-header.js" type="module" defer></script>'


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
