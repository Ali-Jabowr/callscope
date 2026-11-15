"""Вид руководителя: цепочки, обещания, список внимания, сводка по стандарту."""

from __future__ import annotations

from dataclasses import astuple
from datetime import date
from typing import Any

import pytest

from callscope.management import (
    attention_list,
    build_chains,
    manager_promises,
    standard_summary,
)
from callscope.models import (
    CallAnalysis,
    DateRef,
    Evidence,
    Item,
    NextStep,
    StandardCheck,
)

AS_OF = date(2026, 9, 10)
NEW_SALE: dict[str, Any] = {"call_type": "новая_продажа"}


def ev(quote: str = "цитата", verified: bool | None = True) -> list[Evidence]:
    return [Evidence(quote=quote, verified=verified)]


def call(source: str = "c.md", day: date = date(2026, 9, 1), **kw: Any) -> CallAnalysis:
    fields: dict[str, Any] = {
        "source_file": source,
        "call_date": day,
        "call_weekday": "вторник",
        "company": "Альфа",
        "client_id": "alfa",
        "summary": "итог",
    }
    fields.update(kw)
    return CallAnalysis(**fields)


def step(
    due: date | None, owner: str = "менеджер", verified: bool | None = True
) -> NextStep:
    ref = None if due is None else DateRef(raw_expression="к дате", resolved=due)
    return NextStep(
        action="Выслать КП",
        owner=owner,  # type: ignore[arg-type]
        date=ref,
        evidence=ev("вышлю КП", verified),
    )


def check(cid: str, status: str) -> StandardCheck:
    return StandardCheck(
        criterion_id=cid,
        title=cid,
        status=status,  # type: ignore[arg-type]
        evidence=ev("не спросил"),
    )


def test_chains_group_by_client_and_take_last_call() -> None:
    chains = build_chains(
        [
            call("b2.md", date(2026, 9, 5), outcome="отказ", call_type="продление"),
            call("b1.md", date(2026, 9, 1), outcome="продвижение"),
            call(
                "a1.md",
                date(2026, 9, 2),
                client_id="beta",
                company="Бета",
                outcome="перенос",
                call_type="новая_продажа",
            ),
        ]
    )
    assert [astuple(c) for c in chains] == [
        ("alfa", "Альфа", 2, date(2026, 9, 5), "отказ", "продление"),
        ("beta", "Бета", 1, date(2026, 9, 2), "перенос", "новая_продажа"),
    ]


@pytest.mark.parametrize(
    ("due", "status"),
    [
        (date(2026, 9, 9), "просрочено"),
        (date(2026, 9, 10), "сегодня"),
        (date(2026, 9, 11), "впереди"),
    ],
)
def test_promise_status_against_as_of(due: date, status: str) -> None:
    promises = manager_promises([call(next_steps=[step(due)])], AS_OF)
    assert [(p.status, p.due, p.quote) for p in promises] == [(status, due, "вышлю КП")]


@pytest.mark.parametrize(
    "bad_step",
    [
        step(date(2026, 9, 9), owner="клиент"),
        step(date(2026, 9, 9), verified=False),
        step(date(2026, 9, 9), verified=None),
        step(None),
    ],
)
def test_promise_excludes_non_manager_unverified_or_undated(bad_step: NextStep) -> None:
    assert manager_promises([call(next_steps=[bad_step])], AS_OF) == []


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param(
            {
                "needs_supervisor_attention": [
                    Item(text="Нужен созвон", evidence=ev("q1"))
                ]
            },
            [("Нужен созвон", "средняя", "q1")],
            id="supervisor-item",
        ),
        pytest.param(
            {
                "needs_supervisor_attention": [
                    Item(text="Клиент рассматривает другую систему", evidence=ev("q2"))
                ]
            },
            [("Клиент рассматривает другую систему", "высокая", "q2")],
            id="churn-in-text",
        ),
        pytest.param(
            {
                "needs_supervisor_attention": [
                    Item(text="Сигнал", evidence=ev("думаем про уход к конкурентам"))
                ]
            },
            [("Сигнал", "высокая", "думаем про уход к конкурентам")],
            id="churn-in-evidence",
        ),
        pytest.param(
            {
                "needs_supervisor_attention": [
                    Item(text="Сигнал", evidence=ev("q", False))
                ]
            },
            [],
            id="unverified-supervisor-item",
        ),
        pytest.param(
            {"next_steps": [step(date(2026, 9, 9))]},
            [("просроченное обещание менеджера: Выслать КП", "высокая", "вышлю КП")],
            id="overdue-promise",
        ),
        pytest.param({"next_steps": [step(date(2026, 9, 10))]}, [], id="due-today"),
        pytest.param(
            {"outcome": "отказ"},
            [("итог", "средняя", "")],
            id="refusal",
        ),
        pytest.param(
            {
                **NEW_SALE,
                "standard": [check("a", "не_выполнено"), check("b", "не_выполнено")],
            },
            [("отступления от продажного стандарта", "средняя", "не спросил")],
            id="two-standard-failures",
        ),
        pytest.param(
            {
                **NEW_SALE,
                "standard": [check("a", "не_выполнено"), check("b", "выполнено")],
            },
            [],
            id="one-standard-failure",
        ),
        pytest.param(
            {
                "call_type": "поддержка",
                "standard": [check("a", "не_выполнено"), check("b", "не_выполнено")],
            },
            [],
            id="standard-ignored-outside-new-sale",
        ),
    ],
)
def test_attention_rules(
    kwargs: dict[str, Any], expected: list[tuple[str, str, str]]
) -> None:
    entries = attention_list([call(**kwargs)], AS_OF)
    assert [(e.reason, e.severity, e.quote) for e in entries] == expected


def test_attention_entry_carries_client_and_source_file() -> None:
    entries = attention_list([call("x.md", outcome="отказ")], AS_OF)
    assert [(e.client, e.call) for e in entries] == [("Альфа", "x.md")]


def test_attention_sorted_high_first_then_by_date() -> None:
    early_medium = call("m1.md", date(2026, 9, 1), outcome="отказ")
    late_medium = call("m2.md", date(2026, 9, 8), outcome="отказ")
    late_high = call("h2.md", date(2026, 9, 7), next_steps=[step(date(2026, 9, 9))])
    early_high = call("h1.md", date(2026, 9, 3), next_steps=[step(date(2026, 9, 9))])
    entries = attention_list([late_medium, late_high, early_medium, early_high], AS_OF)
    assert [e.call for e in entries] == ["h1.md", "h2.md", "m1.md", "m2.md"]


def test_standard_summary_counts_failures_in_new_sales_sorted_desc() -> None:
    summary = standard_summary(
        [
            call(
                "1.md",
                standard=[check("price", "не_выполнено"), check("step", "выполнено")],
                **NEW_SALE,
            ),
            call(
                "2.md",
                standard=[
                    check("price", "не_выполнено"),
                    check("step", "не_выполнено"),
                ],
                **NEW_SALE,
            ),
            call(
                "3.md", standard=[check("price", "не_выполнено")], call_type="поддержка"
            ),
        ]
    )
    assert summary == [("price", 2), ("step", 1)]
