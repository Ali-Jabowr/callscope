"""Защита от галлюцинаций: цитаты сверяются с транскриптом, а не с JSON."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from callscope.ingest import Transcript, load
from callscope.models import CallAnalysis, Evidence, Item
from callscope.validate import check_grounding, revalidate

TUE = date(2026, 9, 8)

SNIPPET = (
    "Сергей: Нет, коммерческое сейчас рано. Мне сначала нужна техническая схема "
    "и понимание, что будет с нашей доработанной 1С."
)

NOT_CONFIRMED = "НЕ ПОДТВЕРЖДЕНО: ни одна цитата не найдена в транскрипте"


def _transcript() -> Transcript:
    return Transcript(
        path=Path("test.md"),
        raw=SNIPPET,
        body=SNIPPET,
        call_date=TUE,
        weekday="вторник",
        weekday_stated="вторник",
        company="Тест",
        manager="Анна",
        client_contact="Сергей",
        header_conflicts=[],
    )


def _analysis_with_mistake(quote: str) -> CallAnalysis:
    return CallAnalysis(
        source_file="test.md",
        call_date=TUE,
        call_weekday="вторник",
        summary="—",
        manager_mistakes=[
            Item(text="Пункт", evidence=[Evidence(quote=quote, speaker="Сергей")])
        ],
    )


@pytest.mark.parametrize(
    ("quote", "want_verified", "want_flags"),
    [
        # настоящая цитата подтверждается, флагов нет
        ("коммерческое сейчас рано", True, []),
        # другая типографика (регистр, пунктуация) всё ещё засчитывается
        ("Нет, коммерческое сейчас рано", True, []),
        # выдумка отбивается и помечается
        ("дам скидку тридцать процентов", False, [NOT_CONFIRMED]),
    ],
)
def test_quote_is_checked_against_transcript(
    quote: str, want_verified: bool, want_flags: list[str]
) -> None:
    analysis = _analysis_with_mistake(quote)

    check_grounding(analysis, _transcript())

    item = analysis.manager_mistakes[0]
    assert (item.evidence[0].verified, item.flags) == (want_verified, want_flags)


def test_revalidate_catches_tampered_quote(tmp_path: Path) -> None:
    """report обязан перечитывать цитаты по транскрипту, а не верить JSON."""
    transcript_file = tmp_path / "test.md"
    transcript_file.write_text(
        "Дата разговора: 8 сентября 2026 года, вторник\n\n---\n\n" + SNIPPET,
        encoding="utf-8",
    )
    loaded = load(transcript_file)
    analysis = CallAnalysis(
        source_file="test.md",
        call_date=loaded.call_date,
        call_weekday=loaded.weekday,
        summary="—",
        risks=[
            Item(
                text="Выдуманный риск",
                # verified=True — как после реального прогона, до правки цитаты
                evidence=[
                    Evidence(
                        quote="цитата, которой нет в тексте",
                        speaker="Сергей",
                        verified=True,
                    )
                ],
            )
        ],
    )

    revalidate(analysis, transcript_file)

    item = analysis.risks[0]
    assert (item.evidence[0].verified, NOT_CONFIRMED in item.flags) == (False, True)
