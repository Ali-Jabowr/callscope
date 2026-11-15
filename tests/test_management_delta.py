"""Вид руководителя, уточнения: agreed, нормализованные стемы ухода, отказ."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from callscope.management import attention_list, manager_promises
from callscope.models import CallAnalysis, DateRef, Evidence, Item, NextStep

AS_OF = date(2026, 9, 10)


def ev(quote: str, verified: bool | None = True) -> list[Evidence]:
    return [Evidence(quote=quote, verified=verified)]


def call(**kw: Any) -> CallAnalysis:
    fields: dict[str, Any] = {
        "source_file": "c.md",
        "call_date": date(2026, 9, 1),
        "call_weekday": "вторник",
        "company": "Альфа",
        "client_id": "alfa",
        "summary": "Клиент закрыл вопрос",
    }
    fields.update(kw)
    return CallAnalysis(**fields)


def test_promise_not_agreed_is_excluded() -> None:
    step = NextStep(
        action="Выслать КП",
        owner="менеджер",
        agreed=False,
        date=DateRef(raw_expression="к дате", resolved=date(2026, 9, 9)),
        evidence=ev("могу выслать"),
    )
    assert manager_promises([call(next_steps=[step])], AS_OF) == []


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("Клиент уйдёт к конкурентам", "q"),
        ("Сигнал", "Мы уйдем, если не сделаете скидку"),
        ("Сигнал", "Это УХОД клиента"),
        ("Сигнал", "ушли в другие системы"),
        ("Сигнал", "смотрят другую систему"),
        ("Сигнал", "ищут другие решения"),
        ("Сигнал", "у конкурента дешевле"),
        ("Сигнал", "мы не продлим договор"),
    ],
)
def test_churn_stems_raise_severity_to_high(text: str, quote: str) -> None:
    item = Item(text=text, evidence=ev(quote))
    entries = attention_list([call(needs_supervisor_attention=[item])], AS_OF)
    assert [e.severity for e in entries] == ["высокая"]


def test_no_churn_stem_stays_medium() -> None:
    item = Item(text="Нужен созвон", evidence=ev("просили перезвонить"))
    entries = attention_list([call(needs_supervisor_attention=[item])], AS_OF)
    assert [e.severity for e in entries] == ["средняя"]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param(
            {"risks": [Item(text="Риск", evidence=ev("не интересно"))]},
            [("Клиент закрыл вопрос", "средняя", "не интересно")],
            id="verified-risk-quote",
        ),
        pytest.param(
            {
                "risks": [Item(text="Риск", evidence=ev("мимо", False))],
                "needs_supervisor_attention": [
                    Item(text="Позвонить", evidence=ev("жду звонка"))
                ],
            },
            [
                ("Позвонить", "средняя", "жду звонка"),
                ("Клиент закрыл вопрос", "средняя", "жду звонка"),
            ],
            id="skips-unverified-risk-uses-supervisor-quote",
        ),
        pytest.param(
            {"risks": [Item(text="Риск", evidence=ev("мимо", None))]},
            [("Клиент закрыл вопрос", "средняя", "")],
            id="no-verified-quote",
        ),
    ],
)
def test_refusal_uses_summary_and_first_verified_quote(
    kwargs: dict[str, Any], expected: list[tuple[str, str, str]]
) -> None:
    entries = attention_list([call(outcome="отказ", **kwargs)], AS_OF)
    assert [(e.reason, e.severity, e.quote) for e in entries] == expected
