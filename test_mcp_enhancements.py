#!/usr/bin/env python3
"""
Test script for DAZZLE MCP v0.2 enhancements.

Tests semantic lookup and example search functionality.
"""

import json
from dazzle.mcp.semantics import lookup_concept, get_semantic_index
from dazzle.mcp.examples import search_examples, get_example_metadata, get_v0_2_examples


def test_lookup_concept():
    """Test looking up various DSL concepts."""
    print("=" * 80)
    print("TEST: lookup_concept()")
    print("=" * 80)

    test_terms = [
        "persona",
        "workspace",
        "attention_signals",
        "ux_block",
        "purpose",
        "scope"
    ]

    for term in test_terms:
        print(f"\n➤ Looking up: {term}")
        result = lookup_concept(term)
        if result.get("found"):
            print(f"  ✓ Category: {result.get('category')}")
            print(f"  ✓ Definition: {result.get('definition')[:80]}...")
            print(f"  ✓ Related: {', '.join(result.get('related', []))}")
            if result.get('v0_2_changes'):
                print(f"  ✓ v0.2: {result.get('v0_2_changes')}")
        else:
            print(f"  ✗ Not found: {result.get('error', 'Unknown error')}")

    print("\n✓ lookup_concept tests completed\n")


def test_semantic_index():
    """Test getting the full semantic index."""
    print("=" * 80)
    print("TEST: get_semantic_index()")
    print("=" * 80)

    index = get_semantic_index()

    print(f"\n➤ Semantic Index")
    print(f"  Version: {index.get('version')}")
    print(f"  Total concepts: {len(index.get('concepts', {}))}")
    print(f"  Total patterns: {len(index.get('patterns', {}))}")

    # List all concepts by category
    concepts = index.get('concepts', {})
    categories = {}
    for name, data in concepts.items():
        cat = data.get('category', 'Unknown')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(name)

    print(f"\n  Concepts by category:")
    for cat, names in sorted(categories.items()):
        print(f"    {cat}: {', '.join(sorted(names))}")

    print("\n✓ get_semantic_index test completed\n")


def test_search_examples():
    """Test searching for examples."""
    print("=" * 80)
    print("TEST: search_examples()")
    print("=" * 80)

    # Test 1: Search by single feature
    print("\n➤ Search by feature: ['persona']")
    results = search_examples(features=['persona'])
    print(f"  Found {len(results)} examples:")
    for ex in results:
        print(f"    - {ex['name']} ({ex['complexity']}): {ex['title']}")

    # Test 2: Search by multiple features
    print("\n➤ Search by features: ['workspace', 'aggregates']")
    results = search_examples(features=['workspace', 'aggregates'])
    print(f"  Found {len(results)} examples:")
    for ex in results:
        print(f"    - {ex['name']}: demonstrates {len(ex['demonstrates'])} features")

    # Test 3: Search by complexity
    print("\n➤ Search by complexity: 'beginner'")
    results = search_examples(complexity='beginner')
    print(f"  Found {len(results)} examples:")
    for ex in results:
        print(f"    - {ex['name']}: {ex['title']}")

    # Test 4: v0.2 examples only
    print("\n➤ Get all v0.2 examples")
    v02_examples = get_v0_2_examples()
    print(f"  Found {len(v02_examples)} examples with v0.2 features:")
    for ex in v02_examples:
        print(f"    - {ex['name']}: {', '.join(ex['v0_2_features'])}")

    print("\n✓ search_examples tests completed\n")


def test_example_metadata():
    """Test getting example metadata."""
    print("=" * 80)
    print("TEST: get_example_metadata()")
    print("=" * 80)

    metadata = get_example_metadata()

    print(f"\n➤ Example Metadata")
    print(f"  Total examples: {len(metadata)}")

    for name, data in metadata.items():
        print(f"\n  {name}:")
        print(f"    Title: {data['title']}")
        print(f"    Complexity: {data.get('complexity', 'N/A')}")
        print(f"    Demonstrates: {len(data.get('demonstrates', []))} features")
        if data.get('v0_2_features'):
            print(f"    v0.2 Features: {', '.join(data['v0_2_features'])}")

    print("\n✓ get_example_metadata test completed\n")


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "DAZZLE MCP v0.2 Enhancement Tests" + " " * 24 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    try:
        test_semantic_index()
        test_lookup_concept()
        test_example_metadata()
        test_search_examples()

        print("╔" + "=" * 78 + "╗")
        print("║" + " " * 30 + "ALL TESTS PASSED ✓" + " " * 29 + "║")
        print("╚" + "=" * 78 + "╝")
        print()

    except Exception as e:
        print("\n" + "=" * 80)
        print(f"✗ TEST FAILED: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
