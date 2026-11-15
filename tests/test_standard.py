"""Стандарт продаж: критерии, проверка цитат, пропуск LLM на коротких звонках."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from callscope.ingest import Transcript
from callscope.models import CallAnalysis
from callscope.pipeline import analyze_one
from callscope.standard import load_criteria
from callscope.validate import validate

TUE = date(2026, 9, 8)

LONG_BODY = " ".join(["слово"] * 80) + "\nСергей: Пришлите точный расчёт до четверга."
SHORT_BODY = "Анна: Алло, это ТехноПоток.\nСергей: Мы не заказывали, до свидания."

UNVERIFIED_FLAG = "цитата не найдена в расшифровке"


def _transcript(body: str) -> Transcript:
    return Transcript(
        path=Path("test.md"),
        raw=body,
        body=body,
        call_date=TUE,
        weekday="вторник",
        weekday_stated="вторник",
        company="Тест",
        manager="Анна",
        client_contact="Сергей",
        header_conflicts=[],
    )


class FakeProvider:
    name = "fake"

    def __init__(self, reply: dict[str, object]) -> None:
        self.reply = reply
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return json.dumps(self.reply, ensure_ascii=False)


def _analysis(call_type: str, quote: str, status: str) -> CallAnalysis:
    return CallAnalysis.model_validate(
        {
            "source_file": "test.md",
            "call_date": TUE,
            "call_weekday": "вторник",
            "summary": "—",
            "call_type": call_type,
            "standard": [
                {
                    "criterion_id": "next_step_dated",
                    "title": "Шаг с датой",
                    "status": status,
                    "comment": "ок",
                    "evidence": [{"quote": quote, "speaker": "Сергей"}],
                }
            ],
        }
    )


def test_criteria_loaded_from_yaml() -> None:
    ids = [c.id for c in load_criteria()]
    assert ids == [
        "needs_discovered",
        "decision_maker_identified",
        "presentation_tied_to_needs",
        "next_step_dated",
        "exact_price",
        "objection_handled",
    ]


@pytest.mark.parametrize(
    ("quote", "status_in", "status_out", "flags"),
    [
        # цитата настоящая: статус модели сохраняется
        ("точный расчёт до четверга", "выполнено", "выполнено", []),
        # выдумка: статус принудительно «неясно» и флаг
        ("дам скидку тридцать процентов", "выполнено", "неясно", [UNVERIFIED_FLAG]),
        ("дам скидку тридцать процентов", "не_выполнено", "неясно", [UNVERIFIED_FLAG]),
    ],
)
def test_unverified_quote_downgrades_status(
    quote: str, status_in: str, status_out: str, flags: list[str]
) -> None:
    result = validate(
        _analysis("новая_продажа", quote, status_in), _transcript(LONG_BODY)
    )

    assert result.standard[0].status == status_out
    assert result.standard[0].flags == flags


@pytest.mark.parametrize(
    ("call_type", "want_titles"),
    [
        ("новая_продажа", ["Шаг с датой"]),
        ("поддержка", []),
        ("продление", []),
        ("допродажа", []),
        ("нецелевой", []),
        ("прочее", []),
    ],
)
def test_standard_kept_only_for_new_sale(
    call_type: str, want_titles: list[str]
) -> None:
    result = validate(
        _analysis(call_type, "точный расчёт до четверга", "выполнено"),
        _transcript(LONG_BODY),
    )

    assert [c.title for c in result.standard] == want_titles


def test_short_call_skips_llm() -> None:
    provider = FakeProvider({"summary": "не должно использоваться"})

    result = analyze_one(_transcript(SHORT_BODY), provider)

    assert provider.calls == 0
    assert result.call_type == "нецелевой"
    assert result.summary == "Короткий звонок, без содержательного разговора"
    assert result.outcome == "требует_уточнения"
    assert result.standard == []


def test_long_call_goes_to_llm_and_keeps_model_call_type() -> None:
    provider = FakeProvider(
        {"summary": "Итог", "call_type": "поддержка", "outcome": "перенос"}
    )

    result = analyze_one(_transcript(LONG_BODY), provider)

    assert provider.calls == 1
    assert result.call_type == "поддержка"
    assert result.summary == "Итог"


@pytest.mark.parametrize(
    ("status_in", "status_out", "flags"),
    [
        # заявленное выполнение без цитаты не принимается
        ("выполнено", "неясно", ["нет цитаты-доказательства"]),
        # отсутствие действия цитатой не подтвердить: статус остаётся
        ("не_выполнено", "не_выполнено", []),
        ("неясно", "неясно", []),
    ],
)
def test_compliance_without_quote_downgrades_status(
    status_in: str, status_out: str, flags: list[str]
) -> None:
    analysis = CallAnalysis.model_validate(
        {
            "source_file": "test.md",
            "call_date": TUE,
            "call_weekday": "вторник",
            "summary": "—",
            "call_type": "новая_продажа",
            "standard": [
                {
                    "criterion_id": "next_step_dated",
                    "title": "Шаг с датой",
                    "status": status_in,
                    "evidence": [],
                }
            ],
        }
    )

    result = validate(analysis, _transcript(LONG_BODY))

    assert result.standard[0].status == status_out
    assert result.standard[0].flags == flags
