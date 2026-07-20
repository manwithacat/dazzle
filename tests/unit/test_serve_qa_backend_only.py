"""backend-only serve arms QA magic-link for agent trial-coverage."""

from __future__ import annotations

import os

from dazzle.cli.runtime_impl.serve import _arm_qa_mode_env


class _Ctx:
    def __init__(self, enable_dev_mode: bool) -> None:
        self.enable_dev_mode = enable_dev_mode


def test_arm_qa_mode_env_sets_when_dev() -> None:
    os.environ.pop("DAZZLE_QA_MODE", None)
    _arm_qa_mode_env(_Ctx(True))
    assert os.environ.get("DAZZLE_QA_MODE") == "1"


def test_arm_qa_mode_env_noop_when_not_dev() -> None:
    os.environ["DAZZLE_QA_MODE"] = "0"
    _arm_qa_mode_env(_Ctx(False))
    assert os.environ.get("DAZZLE_QA_MODE") == "0"
