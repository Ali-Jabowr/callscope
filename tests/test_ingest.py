"""Разбор шапки, client_id и загрузка демо-набора."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from callscope.ingest import client_slug, load
from callscope.pipeline import analyze_one

DEMO = Path(__file__).parent.parent / "demo" / "transcripts"


def _write(tmp_path: Path, participants: str) -> Path:
    p = tmp_path / "call.md"
    p.write_text(
        "Дата разговора: 2 ноября 2026 года, понедельник\n"
        f"Участники: {participants}\n\n---\n\nИрина: Алло.\nДмитрий: Да.\n",
        encoding="utf-8",
    )
    return p


@pytest.mark.parametrize(
    ("participants", "manager", "contact", "company"),
    [
        (
            (
                "Ирина — менеджер отдела продаж; "
                "Дмитрий — коммерческий директор клиента «Вектор-Строй»"
            ),
            "Ирина",
            "Дмитрий",
            "Вектор-Строй",
        ),
        (
            (
                "Анна — менеджер интегратора; "
                "Сергей — финансовый директор клиента «Альфа-Металл»"
            ),
            "Анна",
            "Сергей",
            "Альфа-Металл",
        ),
    ],
)
def test_manager_role_starting_with_manager_is_recognised(
    tmp_path: Path, participants: str, manager: str, contact: str, company: str
) -> None:
    t = load(_write(tmp_path, participants))
    assert (t.manager, t.client_contact, t.company) == (manager, contact, company)


@pytest.mark.parametrize(
    ("company", "slug"),
    [
        ("Вектор-Строй", "vektor-stroy"),
        ("Зелёный Двор", "zelenyy-dvor"),
        ("Медицина Плюс", "meditsina-plyus"),
        ("Логистик Юг", "logistik-yug"),
        ("Пекарня Колос", "pekarnya-kolos"),
        ("Альтаир-Ритейл", "altair-riteyl"),
        ("Северный Порт", "severnyy-port"),
        ("  ООО «Рога & Копыта» ", "ooo-roga-kopyta"),
        ("Acme 2", "acme-2"),
        (None, None),
        ("", None),
    ],
)
def test_client_slug(company: str | None, slug: str | None) -> None:
    assert client_slug(company) == slug


def test_transcript_exposes_client_id(tmp_path: Path) -> None:
    t = load(
        _write(
            tmp_path,
            "Ирина — менеджер отдела продаж; Дмитрий — директор клиента «Вектор-Строй»",
        )
    )
    assert t.client_id == "vektor-stroy"


def test_transcript_without_company_has_no_client_id(tmp_path: Path) -> None:
    t = load(_write(tmp_path, "Ирина — менеджер отдела продаж"))
    assert t.client_id is None


# файл: (client_id, менеджер, дата разговора)
DEMO_EXPECTED = [
    ("01_vektor_stroy_pervyy.md", "vektor-stroy", "Ирина", date(2026, 11, 2)),
    ("02_vektor_stroy_demo.md", "vektor-stroy", "Ирина", date(2026, 11, 10)),
    ("03_zelenyy_dvor_prodlenie.md", "zelenyy-dvor", "Павел", date(2026, 11, 3)),
    ("04_medplus_podderzhka.md", "meditsina-plyus", "Ольга", date(2026, 11, 4)),
    ("05_logistik_yug_novaya.md", "logistik-yug", "Павел", date(2026, 11, 5)),
    ("06_kolos_netselevoy.md", "pekarnya-kolos", "Ольга", date(2026, 11, 5)),
    ("07_altair_apsell.md", "altair-riteyl", "Ольга", date(2026, 11, 6)),
    ("08_severnyy_port_otkaz.md", "severnyy-port", "Ирина", date(2026, 11, 9)),
    ("09_vektor_stroy_kp.md", "vektor-stroy", "Ирина", date(2026, 11, 19)),
    ("10_zelenyy_dvor_vozvrat.md", "zelenyy-dvor", "Павел", date(2026, 11, 10)),
]


@pytest.mark.parametrize(("name", "client_id", "manager", "call_date"), DEMO_EXPECTED)
def test_demo_transcript_header(
    name: str, client_id: str, manager: str, call_date: date
) -> None:
    t = load(DEMO / name)
    assert (t.client_id, t.manager, t.call_date) == (client_id, manager, call_date)
    assert t.header_conflicts == []


def test_demo_dir_has_exactly_the_expected_files() -> None:
    assert sorted(p.name for p in DEMO.glob("*.md")) == sorted(
        name for name, *_ in DEMO_EXPECTED
    )


class _FakeProvider:
    name = "fake"

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def complete(self, system: str, user: str) -> str:
        return json.dumps(self._payload, ensure_ascii=False)


def test_pipeline_sets_client_id_and_transcript_not_the_model() -> None:
    t = load(DEMO / "01_vektor_stroy_pervyy.md")
    # модель пытается подсунуть чужие значения — они должны быть перезаписаны
    provider = _FakeProvider(
        {"summary": "итог", "client_id": "evil", "transcript": "подделка"}
    )
    a = analyze_one(t, provider)
    assert a.client_id == "vektor-stroy"
    assert a.transcript.startswith("Ирина: Дмитрий, добрый день.")
    assert a.transcript.endswith("Дмитрий: Договорились.")
