"""Модули импортируются без побочных эффектов (в т.ч. без файла gold/gold.yaml)."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "callscope.__main__",
        "callscope.dates",
        "callscope.evaluate",
        "callscope.ingest",
        "callscope.models",
        "callscope.pipeline",
        "callscope.prompt",
        "callscope.providers",
        "callscope.render",
        "callscope.validate",
    ],
)
def test_module_imports(module: str) -> None:
    assert importlib.import_module(module).__name__ == module
