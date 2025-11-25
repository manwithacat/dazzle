"""
Next.js Onebox generators.

Each generator is responsible for a specific part of the generated application:
- ConfigGenerator: package.json, tsconfig.json, next.config.ts, etc.
- PrismaGenerator: Prisma schema from entities
- TypesGenerator: TypeScript types from IR
- LibGenerator: Utility libraries (db, auth, persona, attention)
- ComponentsGenerator: UI components
- ActionsGenerator: Server Actions for CRUD
- AuthGenerator: Authentication pages
- LayoutGenerator: Root layout and providers
- MiddlewareGenerator: Next.js middleware for auth/persona
- PagesGenerator: App Router pages from surfaces
- StylesGenerator: Tailwind config and global CSS
- DockerGenerator: Dockerfile and scripts
"""

from .actions import ActionsGenerator
from .auth import AuthGenerator
from .components import ComponentsGenerator
from .config import ConfigGenerator
from .docker import DockerGenerator
from .layout import LayoutGenerator
from .lib import LibGenerator
from .middleware import MiddlewareGenerator
from .pages import PagesGenerator
from .prisma import PrismaGenerator
from .styles import StylesGenerator
from .types import TypesGenerator

__all__ = [
    "ConfigGenerator",
    "PrismaGenerator",
    "TypesGenerator",
    "LibGenerator",
    "ComponentsGenerator",
    "ActionsGenerator",
    "AuthGenerator",
    "LayoutGenerator",
    "MiddlewareGenerator",
    "PagesGenerator",
    "StylesGenerator",
    "DockerGenerator",
]
