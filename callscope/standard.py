"""Стандарт первого звонка по продаже: критерии грузятся из standard.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]  # types-PyYAML не в dev-зависимостях
from pydantic import BaseModel

STANDARD_PATH = Path(__file__).with_name("standard.yaml")


class Criterion(BaseModel):
    id: str
    title: str
    description: str


def load_criteria(path: Path = STANDARD_PATH) -> list[Criterion]:
    return [
        Criterion.model_validate(c) for c in yaml.safe_load(path.read_text("utf-8"))
    ]
