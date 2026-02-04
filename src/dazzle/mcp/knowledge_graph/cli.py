"""
CLI for Knowledge Graph operations.

Usage:
    python -m dazzle.mcp.knowledge_graph.cli auto-populate /path/to/code
    python -m dazzle.mcp.knowledge_graph.cli stats
    python -m dazzle.mcp.knowledge_graph.cli query "MetricsMiddleware"
    python -m dazzle.mcp.knowledge_graph.cli deps file:src/dazzle/core/parser.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .handlers import KnowledgeGraphHandlers
from .store import KnowledgeGraph


def get_default_db_path() -> Path:
    """Get default database path."""
    # Use project root's .dazzle directory
    return Path.cwd() / ".dazzle" / "knowledge_graph.db"


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Knowledge Graph CLI")
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Database path (default: .dazzle/knowledge_graph.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # auto-populate command
    pop_parser = subparsers.add_parser("auto-populate", help="Populate graph from code")
    pop_parser.add_argument("root_path", type=str, help="Root directory to scan")
    pop_parser.add_argument("--max-files", type=int, default=500)

    # stats command
    subparsers.add_parser("stats", help="Show graph statistics")

    # query command
    query_parser = subparsers.add_parser("query", help="Search entities")
    query_parser.add_argument("text", type=str, help="Search text")
    query_parser.add_argument("--type", type=str, help="Filter by type")
    query_parser.add_argument("--limit", type=int, default=20)

    # deps command
    deps_parser = subparsers.add_parser("deps", help="Get dependencies")
    deps_parser.add_argument("entity_id", type=str, help="Entity ID")
    deps_parser.add_argument("--transitive", action="store_true")

    # dependents command
    depts_parser = subparsers.add_parser("dependents", help="Get dependents")
    depts_parser.add_argument("entity_id", type=str, help="Entity ID")
    depts_parser.add_argument("--transitive", action="store_true")

    # neighbourhood command
    neigh_parser = subparsers.add_parser("neighbourhood", help="Get neighbourhood")
    neigh_parser.add_argument("entity_id", type=str, help="Entity ID")
    neigh_parser.add_argument("--depth", type=int, default=1)

    # paths command
    paths_parser = subparsers.add_parser("paths", help="Find paths between entities")
    paths_parser.add_argument("source_id", type=str, help="Source entity ID")
    paths_parser.add_argument("target_id", type=str, help="Target entity ID")
    paths_parser.add_argument("--max-depth", type=int, default=5)

    # list command
    list_parser = subparsers.add_parser("list", help="List entities")
    list_parser.add_argument("--type", type=str, help="Filter by type")
    list_parser.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Initialize graph
    db_path = Path(args.db) if args.db else get_default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    graph = KnowledgeGraph(db_path)
    handlers = KnowledgeGraphHandlers(graph)

    # Execute command
    if args.command == "auto-populate":
        result = handlers.handle_auto_populate(
            root_path=args.root_path,
            max_files=args.max_files,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "stats":
        result = handlers.handle_get_stats()
        print(json.dumps(result, indent=2))

    elif args.command == "query":
        entity_types = [args.type] if args.type else None
        result = handlers.handle_query(
            text=args.text,
            entity_types=entity_types,
            limit=args.limit,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "deps":
        result = handlers.handle_get_dependencies(
            entity_id=args.entity_id,
            transitive=args.transitive,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "dependents":
        result = handlers.handle_get_dependents(
            entity_id=args.entity_id,
            transitive=args.transitive,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "neighbourhood":
        result = handlers.handle_get_neighbourhood(
            entity_id=args.entity_id,
            depth=args.depth,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "paths":
        result = handlers.handle_find_paths(
            source_id=args.source_id,
            target_id=args.target_id,
            max_depth=args.max_depth,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        result = handlers.handle_list_entities(
            entity_type=args.type,
            limit=args.limit,
        )
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
