"""Веб-интерфейс: страницы, экранирование, подсветка цитат, статический сайт."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from callscope.__main__ import main
from callscope.models import (
    CallAnalysis,
    DateRef,
    Evidence,
    Item,
    NextStep,
    StandardCheck,
)
from callscope.web import (
    Links,
    build_site,
    render_call,
    render_calls,
    render_clients,
    render_not_found,
    render_overview,
    route,
)

AS_OF = date(2026, 9, 10)
TRANSCRIPT = (
    "Ирина: Добрый день.\n"
    "Дмитрий: Нам нужен учёт склада, это важно.\n"
    "Ирина: Скину КП до пятницы.\n"
)


def q(quote: str, verified: bool | None = True) -> list[Evidence]:
    return [Evidence(quote=quote, speaker="Ирина", verified=verified)]


def check(status: str, title: str = "Цена названа") -> StandardCheck:
    return StandardCheck(
        criterion_id="exact_price",
        title=title,
        status=status,  # type: ignore[arg-type]
        evidence=q("Скину КП до пятницы"),
    )


def make_call(source: str = "a1.md", **kw: Any) -> CallAnalysis:
    fields: dict[str, Any] = {
        "source_file": source,
        "call_date": date(2026, 9, 1),
        "call_weekday": "вторник",
        "company": "Альфа",
        "client_id": "alfa",
        "manager": "Ирина",
        "call_type": "новая_продажа",
        "summary": "Обсудили склад",
        "outcome": "продвижение",
        "transcript": TRANSCRIPT,
        "grounding_score": 1.0,
        "client_needs": [
            Item(text="Учёт склада", evidence=q("нам нужен учет склада")),
        ],
        "next_steps": [
            NextStep(
                action="Выслать КП",
                owner="менеджер",
                date=DateRef(
                    raw_expression="до пятницы",
                    resolved=date(2026, 9, 4),
                    precision="exact",
                ),
                evidence=q("Скину КП до пятницы"),
            )
        ],
        "standard": [check("выполнено")],
    }
    fields.update(kw)
    return CallAnalysis(**fields)


def fixture() -> list[CallAnalysis]:
    return [
        make_call("a1.md"),
        make_call(
            "a2.md",
            call_date=date(2026, 9, 5),
            call_type="продление",
            outcome="перенос",
            summary="Продление",
            next_steps=[],
            standard=[],
        ),
        make_call(
            "b1.md",
            company="Бета <i>",
            client_id="beta",
            call_type="поддержка",
            outcome="отказ",
            summary="<script>alert(1)</script>",
            next_steps=[],
            standard=[],
        ),
    ]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", "<h1>Обзор</h1>"),
        ("/", "<h2>Требует внимания</h2>"),
        ("/", "<h2>Частые отступления от продажного стандарта</h2>"),
        ("/", "<h2>Обещания менеджеров</h2>"),
        ("/calls", "<h1>Звонки</h1>"),
        ("/clients", "<h1>Клиенты</h1>"),
        ("/call/a1.md", "<h1>Карточка звонка</h1>"),
        ("/call/a1.md", "<h2>Итог разговора</h2>"),
        ("/call/a1.md", "<h2>Следующие шаги</h2>"),
        ("/call/a1.md", "<h2>Потребности клиента</h2>"),
        ("/call/a1.md", "<h2>Риски</h2>"),
        ("/call/a1.md", "<h2>Ошибки менеджера</h2>"),
        ("/call/a1.md", "<h2>Чек-лист стандарта</h2>"),
        ("/call/a1.md", "<h2>Транскрипт</h2>"),
    ],
)
def test_page_returns_200_with_heading(path: str, expected: str) -> None:
    status, body = route(path, fixture(), AS_OF)

    assert status == 200
    assert expected in body


@pytest.mark.parametrize("path", ["/call/nope.md", "/nope", "/call/"])
def test_unknown_path_is_404_in_russian(path: str) -> None:
    status, body = route(path, fixture(), AS_OF)

    assert status == 404
    assert "<h1>Страница не найдена</h1>" in body


def test_call_path_is_url_decoded() -> None:
    status, _ = route("/call/%D0%B0.md", [make_call("а.md")], AS_OF)

    assert status == 200


def test_query_string_is_ignored() -> None:
    status, _ = route("/calls?type=x", fixture(), AS_OF)

    assert status == 200


@pytest.mark.parametrize("path", ["/", "/calls", "/clients", "/call/b1.md"])
def test_company_name_is_escaped_everywhere(path: str) -> None:
    _, body = route(path, fixture(), AS_OF)

    assert "Бета &lt;i&gt;" in body
    assert "Бета <i>" not in body


@pytest.mark.parametrize("path", ["/", "/call/b1.md"])
def test_summary_with_script_is_escaped(path: str) -> None:
    _, body = route(path, fixture(), AS_OF)

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)" not in body


def test_transcript_is_escaped() -> None:
    a = make_call(transcript="Ирина: <b>привет</b>\n", client_needs=[])

    body = render_call(a, AS_OF)

    assert "Ирина: &lt;b&gt;привет&lt;/b&gt;" in body


def test_verified_quote_is_highlighted_ignoring_case_and_yo() -> None:
    body = render_call(make_call(), AS_OF)

    assert "<mark>Нам нужен учёт склада</mark>" in body


@pytest.mark.parametrize("verified", [False, None])
def test_unverified_quote_is_not_highlighted(verified: bool | None) -> None:
    a = make_call(
        client_needs=[Item(text="x", evidence=q("нам нужен учет склада", verified))],
        next_steps=[],
        standard=[],
    )

    body = render_call(a, AS_OF)

    assert "<mark>" not in body


def test_quote_not_found_in_transcript_does_not_break_the_page() -> None:
    a = make_call(
        client_needs=[Item(text="x", evidence=q("этого нет в тексте", True))],
        next_steps=[],
        standard=[],
    )

    body = render_call(a, AS_OF)

    assert "<mark>" not in body
    assert "«этого нет в тексте»" in body


@pytest.mark.parametrize(
    ("verified", "expected", "absent"),
    [
        (True, ">сверено<", ">не сверено<"),
        (False, ">не сверено<", ">сверено<"),
        (None, ">не сверено<", ">сверено<"),
    ],
)
def test_each_claim_shows_verified_badge(
    verified: bool | None, expected: str, absent: str
) -> None:
    a = make_call(
        client_needs=[Item(text="x", evidence=q("нам нужен учет склада", verified))],
        next_steps=[],
        standard=[],
    )

    body = render_call(a, AS_OF)

    assert expected in body
    assert absent not in body


@pytest.mark.parametrize(
    ("status", "symbol"),
    [("выполнено", "✓"), ("не_выполнено", "✗"), ("неясно", "?")],
)
def test_standard_checklist_marks(status: str, symbol: str) -> None:
    a = make_call(standard=[check(status)], client_needs=[], next_steps=[])

    body = render_call(a, AS_OF)

    assert re.search(rf"{re.escape(symbol)}\W*(?:<[^>]+>\W*)*Цена названа", body)


def test_next_step_shows_resolved_date() -> None:
    body = render_call(make_call(), AS_OF)

    assert "4 сентября 2026" in body
    assert "Выслать КП" in body


def test_overview_counts_calls_per_type() -> None:
    body = render_overview(fixture(), AS_OF)

    assert (
        '<span class="count">1</span><span class="label">Новая продажа</span>' in body
    )
    assert '<span class="count">1</span><span class="label">Продление</span>' in body


@pytest.mark.parametrize("expected", ["высокая", "просрочено", "средняя"])
def test_overview_shows_status_badges_with_text(expected: str) -> None:
    body = render_overview(fixture(), AS_OF)

    assert f">{expected}<" in body


def test_overview_standard_summary_shows_failed_count() -> None:
    results = [make_call(standard=[check("не_выполнено")])]

    body = render_overview(results, AS_OF)

    assert '<span class="num">1</span>' in body
    assert "Цена названа" in body


def test_calls_table_rows_link_to_cards_and_carry_type() -> None:
    body = render_calls(fixture(), AS_OF)

    assert '<a href="/call/a1.md">' in body
    assert 'data-type="продление"' in body
    assert 'data-filter="поддержка"' in body
    assert "100%" in body


def test_clients_page_groups_calls_into_chain_timeline() -> None:
    body = render_clients(fixture(), AS_OF)

    assert body.count('class="card chain"') == 2
    assert body.index('href="/call/a2.md"') > body.index('href="/call/a1.md"')


def test_not_found_page_has_nav() -> None:
    body = render_not_found(AS_OF)

    assert 'href="/calls"' in body


def test_static_links_are_relative() -> None:
    top = render_calls(fixture(), AS_OF, Links(root="", static=True))
    card = render_call(make_call(), AS_OF, Links(root="../", static=True))

    assert 'href="call/a1.md.html"' in top
    assert 'href="index.html"' in top
    assert 'href="../index.html"' in card
    assert 'href="/' not in top + card


def test_build_site_writes_all_pages(tmp_path: Path) -> None:
    build_site(fixture(), AS_OF, tmp_path)

    names = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*.html"))
    assert names == [
        "404.html",
        "call/a1.md.html",
        "call/a2.md.html",
        "call/b1.md.html",
        "calls.html",
        "clients.html",
        "index.html",
    ]


@pytest.mark.parametrize("name", ["../evil.md", "sub/x.md"])
def test_build_site_rejects_source_file_with_path(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="source_file"):
        build_site([make_call(name)], AS_OF, tmp_path / "site")


def test_cli_site_command_writes_files(tmp_path: Path) -> None:
    src = tmp_path / "analysis.json"
    src.write_text(
        json.dumps([r.model_dump(mode="json") for r in fixture()], ensure_ascii=False),
        encoding="utf-8",
    )

    code = main(
        [
            "site",
            "--source",
            str(src),
            "--as-of",
            "2026-09-10",
            "-o",
            str(tmp_path / "s"),
        ]
    )

    assert code == 0
    assert "<h1>Обзор</h1>" in (tmp_path / "s" / "index.html").read_text("utf-8")


def test_cli_site_missing_source_reports_in_russian(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["site", "--source", str(tmp_path / "no.json"), "-o", str(tmp_path)])

    assert code == 1
    assert "Не удалось прочитать" in capsys.readouterr().err
