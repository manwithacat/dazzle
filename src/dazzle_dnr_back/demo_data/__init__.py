"""
Demo data generation for Dazzle Bar (v0.8.5).

Provides Faker-based demo data generation and scenario-aware seeding.
"""

from __future__ import annotations

from .generator import DemoDataGenerator
from .loader import DemoDataLoader
from .seeder import DemoDataSeeder

__all__ = [
    "DemoDataGenerator",
    "DemoDataLoader",
    "DemoDataSeeder",
]
