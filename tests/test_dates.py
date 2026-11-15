"""Резолвер дат: выражения из реальных транскриптов, без LLM."""

from __future__ import annotations

from datetime import date

import pytest

from callscope.dates import resolve

TUE = date(2026, 9, 8)  # транскрипты 1 и 2
MON = date(2026, 9, 7)  # транскрипт 3
SUN = date(2026, 9, 6)  # транскрипт 4


@pytest.mark.parametrize(
    ("expression", "anchor", "want_date", "want_precision"),
    [
        ("до среды", TUE, date(2026, 9, 9), "exact"),
        ("в этот четверг", TUE, date(2026, 9, 10), "exact"),
        ("10 сентября в 15:00", TUE, date(2026, 9, 10), "exact"),
        ("завтра до конца дня", TUE, date(2026, 9, 9), "exact"),
        ("к понедельнику", TUE, date(2026, 9, 14), "exact"),
        ("в пятницу после четырёх", TUE, date(2026, 9, 11), "exact"),
        ("в пятницу после 11:00", MON, date(2026, 9, 11), "exact"),
        ("два-три рабочих дня", MON, date(2026, 9, 10), "approximate"),
        ("после двадцатого числа января", SUN, date(2027, 1, 21), "approximate"),
        ("в декабре", SUN, None, "month_only"),
        ("во второй половине января", SUN, None, "month_only"),
        ("1 ноября", TUE, date(2026, 11, 1), "exact"),
    ],
)
def test_resolves_expression_from_transcripts(
    expression: str,
    anchor: date,
    want_date: date | None,
    want_precision: str,
) -> None:
    result = resolve(expression, anchor)

    assert (result.resolved, result.precision) == (want_date, want_precision)


@pytest.mark.parametrize(
    ("expression", "anchor", "want_date", "want_precision"),
    [
        # слово, начинающееся с «ма», — не май
        ("5 машин", TUE, None, "relative_unresolved"),
        ("максимум до конца недели", TUE, None, "relative_unresolved"),
        # «средства» — не среда, но «пятницу» в той же фразе находим
        ("в пятницу, средств не жду", TUE, date(2026, 9, 11), "exact"),
    ],
)
def test_lookalike_words_are_not_dates(
    expression: str,
    anchor: date,
    want_date: date | None,
    want_precision: str,
) -> None:
    result = resolve(expression, anchor)

    assert (result.resolved, result.precision) == (want_date, want_precision)
