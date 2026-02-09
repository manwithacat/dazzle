#!/usr/bin/env python3
"""Integration tests for GraphQL BFF layer with real queries."""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# Check if Strawberry is available
try:
    from importlib.util import find_spec

    STRAWBERRY_AVAILABLE = find_spec("strawberry") is not None
except ImportError:
    STRAWBERRY_AVAILABLE = False

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set")


@pytest.fixture(scope="module")
def graphql_server():
    """Start a GraphQL server for the simple_task example."""
    database_url = os.environ["DATABASE_URL"]

    # Start server with GraphQL enabled
    example_path = Path(__file__).parent.parent.parent / "examples" / "simple_task"

    cmd = [
        sys.executable,
        "-m",
        "dazzle.cli",
        "serve",
        "--local",
        "--backend-only",
        "--graphql",
        "--api-port",
        "8765",
        "-m",
        str(example_path / "dazzle.toml"),
    ]

    env = {**os.environ, "DATABASE_URL": database_url}

    # Start with stdout/stderr going to devnull to avoid blocking
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(example_path),
        env=env,
    )

    # Wait for server to be ready
    base_url = "http://127.0.0.1:8765"
    max_wait = 20
    for _ in range(max_wait * 2):
        try:
            resp = httpx.get(f"{base_url}/health", timeout=1)
            if resp.status_code == 200:
                break
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server failed to start")

    yield {"base_url": base_url, "graphql_url": f"{base_url}/graphql"}

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.skipif(not STRAWBERRY_AVAILABLE, reason="Strawberry not installed")
class TestGraphQLQueries:
    """Test GraphQL query operations."""

    def test_health_check(self, graphql_server):
        """Verify server health before testing GraphQL."""
        resp = httpx.get(f"{graphql_server['base_url']}/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_list_tasks_empty(self, graphql_server):
        """Test listing tasks when empty."""
        query = """
        query {
            tasks {
                id
                title
                status
            }
        }
        """
        resp = httpx.post(
            graphql_server["graphql_url"],
            json={"query": query},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "tasks" in data["data"]
        assert isinstance(data["data"]["tasks"], list)

    def test_introspection(self, graphql_server):
        """Test GraphQL introspection query."""
        query = """
        query {
            __schema {
                types {
                    name
                }
            }
        }
        """
        resp = httpx.post(
            graphql_server["graphql_url"],
            json={"query": query},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "__schema" in data["data"]
        type_names = [t["name"] for t in data["data"]["__schema"]["types"]]
        assert "Task" in type_names
        assert "Query" in type_names
        assert "Mutation" in type_names

    def test_query_type_fields(self, graphql_server):
        """Test that Query type has expected fields."""
        query = """
        query {
            __type(name: "Query") {
                fields {
                    name
                }
            }
        }
        """
        resp = httpx.post(
            graphql_server["graphql_url"],
            json={"query": query},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        field_names = [f["name"] for f in data["data"]["__type"]["fields"]]
        assert "task" in field_names  # Get by ID
        assert "tasks" in field_names  # List

    def test_mutation_type_fields(self, graphql_server):
        """Test that Mutation type has expected fields."""
        query = """
        query {
            __type(name: "Mutation") {
                fields {
                    name
                }
            }
        }
        """
        resp = httpx.post(
            graphql_server["graphql_url"],
            json={"query": query},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        field_names = [f["name"] for f in data["data"]["__type"]["fields"]]
        assert "createTask" in field_names
        assert "updateTask" in field_names
        assert "deleteTask" in field_names


@pytest.mark.skipif(not STRAWBERRY_AVAILABLE, reason="Strawberry not installed")
class TestGraphQLErrors:
    """Test GraphQL error handling."""

    def test_invalid_query_syntax(self, graphql_server):
        """Test error response for invalid query syntax."""
        resp = httpx.post(
            graphql_server["graphql_url"],
            json={"query": "invalid query syntax"},
            headers={"Content-Type": "application/json"},
        )
        # GraphQL returns 200 even for errors
        assert resp.status_code == 200
        data = resp.json()
        assert "errors" in data

    def test_unknown_field(self, graphql_server):
        """Test error response for unknown field."""
        query = """
        query {
            tasks {
                unknownField
            }
        }
        """
        resp = httpx.post(
            graphql_server["graphql_url"],
            json={"query": query},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "errors" in data
