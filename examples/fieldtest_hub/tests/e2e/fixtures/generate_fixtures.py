#!/usr/bin/env python3
"""Generate static demo data fixtures for E2E tests.

This script generates deterministic demo data using the BlueprintDataGenerator
and saves it as a JSON file for use in E2E tests.

Usage:
    python generate_fixtures.py

Output:
    fixtures/demo_data.json
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add the dazzle source to path
DAZZLE_ROOT = Path(__file__).parents[5]  # Go up to Dazzle root
sys.path.insert(0, str(DAZZLE_ROOT / "src"))

from dazzle.core.demo_blueprint_persistence import load_blueprint  # noqa: E402
from dazzle.demo_data.blueprint_generator import BlueprintDataGenerator  # noqa: E402


def generate_fixtures() -> dict:
    """Generate demo data fixtures from the blueprint.

    Returns:
        Dict containing all entity data and test user mappings
    """
    # Load the existing blueprint
    project_root = Path(__file__).parents[3]  # fieldtest_hub directory
    blueprint = load_blueprint(project_root)

    if blueprint is None:
        raise RuntimeError(
            f"No blueprint found at {project_root}. "
            "Ensure dsl/seeds/demo_data/blueprint.json exists."
        )

    # Generate data with fixed seed for reproducibility
    generator = BlueprintDataGenerator(blueprint, seed=42)

    # Generate all entities (in-memory, not to files)
    entities_data: dict[str, list[dict]] = {}

    # Generate tenants first
    tenants = generator._generate_tenants_from_blueprint()
    if tenants:
        entities_data["Tenant"] = tenants
        generator._generated_data["Tenant"] = tenants

    # Find User entity blueprint
    user_blueprints = [e for e in blueprint.entities if e.name.lower() == "user"]
    for entity_bp in user_blueprints:
        users = generator._generate_users_from_blueprint(entity_bp)
        entities_data["User"] = users
        generator._generated_data["User"] = users

    # Find Tester entity and generate it
    tester_blueprints = [e for e in blueprint.entities if e.name == "Tester"]
    for entity_bp in tester_blueprints:
        testers = generator.generate_entity(entity_bp)
        entities_data["Tester"] = testers
        generator._generated_data["Tester"] = testers

    # Generate remaining entities
    for entity_bp in blueprint.entities:
        if entity_bp.name.lower() in ("user", "tenant", "tester"):
            continue
        data = generator.generate_entity(entity_bp)
        entities_data[entity_bp.name] = data
        generator._generated_data[entity_bp.name] = data

    # Create test users mapping (one per persona)
    test_users = {}
    personas = ["engineer", "tester", "manager"]

    # Use Tester entity for test users since that's the user entity in fieldtest_hub
    testers = entities_data.get("Tester", [])
    for i, persona in enumerate(personas):
        if i < len(testers):
            tester = testers[i]
            test_users[persona] = {
                "id": tester["id"],
                "name": tester.get("name", f"Test {persona.title()}"),
                "email": tester.get("email", f"{persona}@example.test"),
                "persona": persona,
            }
        else:
            # Create a placeholder if not enough testers
            test_users[persona] = {
                "id": f"test-{persona}-id",
                "name": f"Test {persona.title()}",
                "email": f"{persona}@example.test",
                "persona": persona,
            }

    # Build the fixtures structure
    fixtures = {
        "version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": 42,
        "project": "fieldtest_hub",
        "entities": entities_data,
        "test_users": test_users,
        "login_matrix": generator.get_login_matrix(),
    }

    return fixtures


def main():
    """Generate and save fixtures."""
    print("Generating demo data fixtures for FieldTest Hub E2E tests...")

    fixtures = generate_fixtures()

    # Save to JSON
    output_file = Path(__file__).parent / "demo_data.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(fixtures, f, indent=2, ensure_ascii=False)

    print(f"\nGenerated fixtures saved to: {output_file}")
    print("\nEntity counts:")
    for entity, data in fixtures["entities"].items():
        print(f"  {entity}: {len(data)} records")

    print("\nTest users:")
    for persona, user in fixtures["test_users"].items():
        print(f"  {persona}: {user['name']} ({user['email']})")


if __name__ == "__main__":
    main()
