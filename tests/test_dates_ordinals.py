"""Дни месяца, названные порядковыми числительными: «восемнадцатого ноября»."""

from __future__ import annotations

from datetime import date

import pytest

from callscope.dates import resolve


@pytest.mark.parametrize(
    ("expression", "anchor", "want_date"),
    [
        (
            "до восемнадцатого ноября включительно",
            date(2026, 11, 10),
            date(2026, 11, 18),
        ),
        ("Двадцатого ноября", date(2026, 11, 10), date(2026, 11, 20)),
        ("до первого декабря", date(2026, 11, 6), date(2026, 12, 1)),
        ("пятнадцатого декабря", date(2026, 11, 6), date(2026, 12, 15)),
        ("тридцатого ноября", date(2026, 11, 3), date(2026, 11, 30)),
        ("двадцать пятого декабря", date(2026, 11, 3), date(2026, 12, 25)),
        ("тридцать первого декабря", date(2026, 11, 3), date(2026, 12, 31)),
    ],
)
def test_ordinal_day_with_month_is_exact(
    expression: str, anchor: date, want_date: date
) -> None:
    result = resolve(expression, anchor)

    assert (result.resolved, result.precision) == (want_date, "exact")


@pytest.mark.parametrize(
    ("expression", "anchor", "want_date"),
    [
        ("не позже восемнадцатого", date(2026, 11, 10), date(2026, 11, 18)),
        ("не позже пятого", date(2026, 11, 10), date(2026, 12, 5)),
        ("до тридцать первого", date(2026, 11, 10), date(2026, 12, 31)),
    ],
)
def test_ordinal_day_without_month_takes_nearest_future_day(
    expression: str, anchor: date, want_date: date
) -> None:
    result = resolve(expression, anchor)

    assert (result.resolved, result.precision) == (want_date, "exact")
    assert result.flags == ["месяц не назван — взят ближайший подходящий"]


def test_ordinal_after_still_gives_approximate_lower_bound() -> None:
    result = resolve("после двадцатого ноября", date(2026, 11, 10))

    assert (result.resolved, result.precision) == (date(2026, 11, 21), "approximate")
