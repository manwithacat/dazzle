"""
Demo data generation for scenarios and dev mode.

Provides Faker-based demo data generation and scenario-aware seeding.
"""

from .generator import DemoDataGenerator
from .loader import DemoDataLoader
from .seeder import DemoDataSeeder

__all__ = [
    "DemoDataGenerator",
    "DemoDataLoader",
    "DemoDataSeeder",
]
