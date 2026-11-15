"""Эталон demo/gold.yaml и его подключение к команде eval."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from callscope.__main__ import main
from callscope.models import CallAnalysis

ROOT = Path(__file__).parent.parent
GOLD = ROOT / "demo" / "gold.yaml"


def test_gold_covers_exactly_the_demo_transcripts() -> None:
    gold = yaml.safe_load(GOLD.read_text(encoding="utf-8"))
    assert sorted(gold) == sorted(
        p.name for p in (ROOT / "demo" / "transcripts").glob("*.md")
    )


@pytest.mark.parametrize(
    ("name", "outcome", "next_date"),
    [
        ("01_vektor_stroy_pervyy.md", "продвижение", "2026-11-10"),
        ("02_vektor_stroy_demo.md", "продвижение", "2026-11-18"),
        ("03_zelenyy_dvor_prodlenie.md", "продвижение", "2026-11-06"),
        ("04_medplus_podderzhka.md", "продвижение", "2026-11-06"),
        ("05_logistik_yug_novaya.md", "требует_уточнения", None),
        ("06_kolos_netselevoy.md", "отказ", None),
        ("07_altair_apsell.md", "продвижение", "2026-12-01"),
        ("08_severnyy_port_otkaz.md", "отказ", None),
        ("09_vektor_stroy_kp.md", "продвижение", "2026-11-19"),
        ("10_zelenyy_dvor_vozvrat.md", "продвижение", "2026-11-12"),
    ],
)
def test_gold_outcome_and_next_date(
    name: str, outcome: str, next_date: str | None
) -> None:
    entry = yaml.safe_load(GOLD.read_text(encoding="utf-8"))[name]
    assert (entry["outcome"], entry["next_action_date"]) == (outcome, next_date)


def test_eval_uses_demo_gold_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    analysis = CallAnalysis(
        source_file="08_severnyy_port_otkaz.md",
        call_date=date(2026, 11, 9),
        call_weekday="понедельник",
        summary="отказ",
        outcome="отказ",
    )
    src = tmp_path / "analysis.json"
    src.write_text(json.dumps([analysis.model_dump(mode="json")]), encoding="utf-8")
    monkeypatch.chdir(ROOT)

    main(["eval", "--source", str(src)])

    out = capsys.readouterr().out
    assert "Эталон: demo/gold.yaml" in out
    assert "эталона нет" not in out
