"""
Generators for Next.js Semantic UI stack.

Each generator handles a specific aspect of the Next.js application:
- PackageJsonGenerator: package.json with dependencies
- ConfigGenerator: Next.js and TypeScript configs
- TailwindConfigGenerator: Tailwind CSS configuration
- LayoutTypesGenerator: TypeScript types from IR
- ArchetypeComponentsGenerator: React components for 5 archetypes
- PagesGenerator: Next.js pages/routes
- HooksGenerator: Custom hooks for data fetching and prefetching
"""

from .archetypes import ArchetypeComponentsGenerator
from .config import ConfigGenerator, PackageJsonGenerator, TailwindConfigGenerator
from .hooks import HooksGenerator
from .pages import PagesGenerator
from .types import LayoutTypesGenerator

__all__ = [
    "PackageJsonGenerator",
    "ConfigGenerator",
    "TailwindConfigGenerator",
    "LayoutTypesGenerator",
    "ArchetypeComponentsGenerator",
    "PagesGenerator",
    "HooksGenerator",
]
