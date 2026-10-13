"""The advertised project resources (dazzle://modules|entities|surfaces) are served."""

import json
from pathlib import Path

import pytest

from dazzle.mcp.server import read_resource
from dazzle.mcp.server.state import get_state, reset_state

_SIMPLE_TASK = Path(__file__).resolve().parents[2] / "examples" / "simple_task"


@pytest.mark.parametrize(
    ("uri", "expected_key"),
    [
        ("dazzle://modules", "modules"),
        ("dazzle://entities", "Task"),
        ("dazzle://surfaces", "task_list"),
    ],
)
async def test_project_resource_is_served(uri: str, expected_key: str) -> None:
    reset_state()
    get_state().project_root = _SIMPLE_TASK
    try:
        payload = json.loads(await read_resource(uri))
    finally:
        reset_state()
    assert expected_key in payload
