"""
Simple markdown to HTML converter for DNR container runtime.

Provides basic markdown conversion without external dependencies.
"""

from __future__ import annotations

import re


def markdown_to_html(text: str) -> str:
    """
    Convert basic markdown to HTML.

    Supports:
    - Headers (h1, h2, h3)
    - Unordered lists
    - Bold and italic
    - Links
    - Code blocks
    - Paragraphs

    Args:
        text: Markdown text to convert

    Returns:
        HTML string
    """
    lines = text.split("\n")
    html_lines: list[str] = []
    in_list = False
    in_code = False

    for line in lines:
        # Code blocks
        if line.strip().startswith("```"):
            if in_code:
                html_lines.append("</pre></code>")
                in_code = False
            else:
                html_lines.append("<code><pre>")
                in_code = True
            continue
        if in_code:
            html_lines.append(line)
            continue

        # Headers
        if line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        # Unordered lists
        elif line.strip().startswith("- ") or line.strip().startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            content = line.strip()[2:]
            html_lines.append(f"<li>{content}</li>")
        else:
            if in_list and line.strip() == "":
                html_lines.append("</ul>")
                in_list = False
            # Bold and italic
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
            # Links
            line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', line)
            # Paragraphs
            if line.strip():
                html_lines.append(f"<p>{line}</p>")
            else:
                html_lines.append("")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)
