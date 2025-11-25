"""
Next.js Onebox Stack for DAZZLE.

Generates a modern Next.js 14+ App Router application with:
- Prisma ORM with PostgreSQL
- Tailwind CSS + Mantine DataTable
- Lucide icons
- Full UX Semantic Layer support
- Simple built-in authentication
- Single Docker container deployment
"""

from .backend import NextJSOneboxBackend

__all__ = ["NextJSOneboxBackend"]
