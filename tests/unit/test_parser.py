#!/usr/bin/env python3
"""Test parser implementation."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl

# Test entity parsing
test_dsl = """
module test.core

app test_app "Test Application"

entity User "User":
  id: uuid pk
  email: email unique required
  name: str(120) required
  age: int optional
  created_at: datetime auto_add

  index email
  unique email

entity Post "Post":
  id: uuid pk
  author: ref User required
  title: str(200) required
  content: text
  status: enum[draft,published,archived]=draft
  views: int=0
  metadata: json

  index author
"""


def main():
    print("Testing lexer and parser...")
    print("=" * 60)

    module_name, app_name, app_title, uses, fragment = parse_dsl(test_dsl, Path("test.dsl"))

    print(f"Module: {module_name}")
    print(f"App: {app_name} - {app_title}")
    print(f"Uses: {uses}")
    print()

    print(f"Entities parsed: {len(fragment.entities)}")
    for entity in fragment.entities:
        print(f"\n  Entity: {entity.name} ({entity.title})")
        print(f"    Fields: {len(entity.fields)}")
        for field in entity.fields:
            print(
                f"      - {field.name}: {field.type.kind.value} "
                + f"(modifiers: {[m.value for m in field.modifiers]}, "
                + f"default: {field.default})"
            )
        print(f"    Constraints: {len(entity.constraints)}")
        for constraint in entity.constraints:
            print(f"      - {constraint.kind.value}: {constraint.fields}")

    print("\n" + "=" * 60)
    print("✅ Parser test passed!")


if __name__ == "__main__":
    main()
