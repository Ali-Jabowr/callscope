"""Локальный веб-интерфейс: только стандартная библиотека, работает офлайн.

Страницы строятся чистыми функциями «данные -> HTML-строка», поэтому их можно
проверять без сокетов и записывать на диск как статический сайт (`site`).
Весь текст из данных проходит через html.escape (`render.e`).
Производные данные (цепочки, обещания, внимание) берём из management.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from .management import (
    _client_key,
    attention_list,
    build_chains,
    manager_promises,
    standard_summary,
)
from .models import (
    CallAnalysis,
    Constraint,
    Evidence,
    Item,
    NextStep,
    StandardCheck,
)
from .render import CONF_LABEL, OUTCOME_LABEL, e, fmt_date
from .validate import normalize

TYPE_LABEL = {
    "новая_продажа": "Новая продажа",
    "продление": "Продление",
    "допродажа": "Допродажа",
    "поддержка": "Поддержка",
    "нецелевой": "Нецелевой",
    "прочее": "Прочее",
}
SEVERITY_CLS = {"высокая": "bad", "средняя": "warn"}
PROMISE_CLS = {"просрочено": "bad", "сегодня": "warn", "впереди": "ok"}
PROMISE_ORDER = {"просрочено": 0, "сегодня": 1, "впереди": 2}
CHECK_MARK = {
    "выполнено": ("✓", "ok"),
    "не_выполнено": ("✗", "bad"),
    "неясно": ("?", "warn"),
}
HOST = "127.0.0.1"


@dataclass(frozen=True)
class Links:
    """Как строить ссылки: от корня сервера или относительно файла на диске."""

    root: str = "/"
    static: bool = False

    def _page(self, name: str) -> str:
        return f"{self.root}{name}" + (".html" if self.static else "")

    def home(self) -> str:
        return f"{self.root}index.html" if self.static else self.root

    def calls(self) -> str:
        return self._page("calls")

    def clients(self) -> str:
        return self._page("clients")

    def call(self, source_file: str) -> str:
        return self._page(f"call/{quote(source_file)}")


SERVER_LINKS = Links()


def load_results(path: Path) -> list[CallAnalysis]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CallAnalysis.model_validate(d) for d in data]


# ------------------------------------------------------------------- вёрстка

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1b1f27;--muted:#667085;--border:#e4e7ec;
--accent:#4f46e5;--accent-soft:#eef2ff;--ok:#067647;--ok-bg:#ecfdf3;
--warn:#b54708;--warn-bg:#fffaeb;--bad:#b42318;--bad-bg:#fef3f2;
--mark:#fde68a;--shadow:0 1px 2px rgba(16,24,40,.05)}
@media (prefers-color-scheme:dark){:root{--bg:#0e1116;--card:#161b22;
--text:#e6e8ec;--muted:#9aa4b2;--border:#262d38;--accent:#8b93ff;
--accent-soft:#1d2140;--ok:#4ade80;--ok-bg:#0f2a1c;--warn:#fbbf24;
--warn-bg:#2d2208;--bad:#f87171;--bad-bg:#2d1212;--mark:#5c4a00;--shadow:none}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);line-height:1.55;
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,
"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
nav.top{position:sticky;top:0;z-index:5;background:var(--card);
border-bottom:1px solid var(--border)}
nav.top .in{max-width:1080px;margin:0 auto;padding:0 24px;height:56px;
display:flex;align-items:center;gap:28px}
.brand{font-weight:700;font-size:17px;color:var(--text);letter-spacing:-.01em}
.brand i{display:inline-block;width:10px;height:10px;border-radius:50%;
background:var(--accent);margin-right:8px}
nav.top a.nav{color:var(--muted);font-weight:500;padding:18px 0;
border-bottom:2px solid transparent}
nav.top a.nav:hover{text-decoration:none;color:var(--text)}
nav.top a.nav.active{color:var(--text);border-bottom-color:var(--accent)}
main{max-width:1080px;margin:0 auto;padding:32px 24px 56px}
h1{font-size:28px;letter-spacing:-.02em;margin:0 0 4px}
h2{font-size:17px;margin:0 0 16px;letter-spacing:-.01em}
p.sub{color:var(--muted);margin:0 0 28px}
.card{background:var(--card);border:1px solid var(--border);border-radius:14px;
padding:22px 24px;margin-bottom:20px;box-shadow:var(--shadow)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;
margin-bottom:20px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:14px;
padding:16px 18px;box-shadow:var(--shadow)}
.stat .count{display:block;font-size:30px;font-weight:700;letter-spacing:-.02em}
.stat .label{display:block;color:var(--muted);font-size:13px}
.stat.zero .count{color:var(--muted);opacity:.5}
.badge{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;
border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap;
background:var(--accent-soft);color:var(--accent)}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.badge.ok{background:var(--ok-bg);color:var(--ok)}
.badge.warn{background:var(--warn-bg);color:var(--warn)}
.badge.bad{background:var(--bad-bg);color:var(--bad)}
.badge.plain{background:var(--bg);color:var(--muted)}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.04em;
color:var(--muted);font-weight:600;padding:0 12px 10px}
td{padding:12px;border-top:1px solid var(--border);vertical-align:top}
tr[hidden]{display:none}
tbody tr:hover{background:var(--bg)}
.muted{color:var(--muted)}.small{font-size:13px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.chips{margin-bottom:16px}
.chip{border:1px solid var(--border);background:var(--card);color:var(--text);
border-radius:999px;padding:6px 14px;font:inherit;font-size:13px;cursor:pointer}
.chip.active{background:var(--accent);border-color:var(--accent);color:#fff}
.list{list-style:none;margin:0;padding:0}
.list>li{padding:14px 0;border-top:1px solid var(--border)}
.list>li:first-child{border-top:0;padding-top:0}
.list>li:last-child{padding-bottom:0}
blockquote{margin:8px 0 0;padding:8px 12px;border-left:3px solid var(--border);
color:var(--muted);font-size:14px;background:var(--bg);border-radius:0 8px 8px 0}
blockquote .badge{margin-left:8px;vertical-align:1px}
.flag{color:var(--warn);font-size:13px;margin-top:6px}
.bar{display:grid;grid-template-columns:minmax(160px,1fr) 2fr 32px;gap:12px;
align-items:center;padding:7px 0}
.bar .track{height:8px;border-radius:999px;background:var(--bg);overflow:hidden}
.bar .fill{height:100%;background:var(--accent);border-radius:999px}
.bar .num{font-weight:700;text-align:right}
.chk{display:inline-flex;width:24px;height:24px;border-radius:50%;
align-items:center;justify-content:center;font-weight:700;flex:none}
.chk.ok{background:var(--ok-bg);color:var(--ok)}
.chk.bad{background:var(--bad-bg);color:var(--bad)}
.chk.warn{background:var(--warn-bg);color:var(--warn)}
.checklist>li{display:flex;gap:12px}
.chk-title{font-weight:600}
.transcript p{margin:0 0 8px}
mark{background:var(--mark);color:inherit;border-radius:3px;padding:0 2px}
.timeline{list-style:none;margin:14px 0 0;padding:0 0 0 18px;
border-left:2px solid var(--border)}
.timeline li{position:relative;padding:0 0 14px 14px}
.timeline li::before{content:"";position:absolute;left:-24px;top:6px;width:10px;
height:10px;border-radius:50%;background:var(--accent)}
.chain-head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.chain-head b{font-size:16px}
footer{max-width:1080px;margin:0 auto;padding:0 24px 40px;color:var(--muted);
font-size:13px}
.empty{color:var(--muted);margin:0}
"""

FILTER_JS = """
document.querySelectorAll('.chip').forEach(function (chip) {
  chip.addEventListener('click', function () {
    var f = chip.dataset.filter;
    document.querySelectorAll('.chip').forEach(function (c) {
      c.classList.toggle('active', c === chip);
    });
    document.querySelectorAll('tbody tr').forEach(function (r) {
      r.hidden = f !== '' && r.dataset.type !== f;
    });
  });
});
"""


def _badge(text: str, cls: str = "") -> str:
    return f'<span class="badge {cls}">{e(text)}</span>'


def _page(
    title: str, active: str, body: str, as_of: date, links: Links, script: str = ""
) -> str:
    nav = "".join(
        f'<a class="nav{" active" if key == active else ""}" href="{href}">{label}</a>'
        for key, label, href in (
            ("home", "Обзор", links.home()),
            ("calls", "Звонки", links.calls()),
            ("clients", "Клиенты", links.clients()),
        )
    )
    js = f"<script>{script}</script>" if script else ""
    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{e(title)} · CallScope</title><style>{CSS}</style></head><body>"
        f'<nav class="top"><div class="in"><span class="brand"><i></i>CallScope</span>'
        f"{nav}</div></nav><main>{body}</main>"
        "<footer>Каждое утверждение несёт дословную цитату; сверку с расшифровкой "
        "делает код, а не модель. Несверенное не попадает в списки руководителю. "
        f"Сроки считаются на {e(fmt_date(as_of))}.</footer>{js}</body></html>"
    )


def _card(title: str, inner: str) -> str:
    return f'<section class="card"><h2>{e(title)}</h2>{inner}</section>'


def _score_badge(score: float | None) -> str:
    if score is None:
        return _badge("сверка: —", "plain")
    cls = "ok" if score >= 0.9 else ("warn" if score >= 0.7 else "bad")
    return _badge(f"{score:.0%}", cls)


def _outcome_badge(outcome: str) -> str:
    label, cls = OUTCOME_LABEL.get(outcome, (outcome, "warn"))
    return _badge(label, cls)


def _client_name(a: CallAnalysis) -> str:
    return a.company or a.client_id or a.source_file


# ------------------------------------------------------------------ обзор


def render_overview(
    results: list[CallAnalysis], as_of: date, links: Links = SERVER_LINKS
) -> str:
    counts = {t: 0 for t in TYPE_LABEL}
    for a in results:
        counts[a.call_type] += 1
    stats = "".join(
        f'<div class="stat{"" if n else " zero"}"><span class="count">{n}</span>'
        f'<span class="label">{e(TYPE_LABEL[t])}</span></div>'
        for t, n in counts.items()
    )
    by_file = {a.source_file: a for a in results}

    attention = "".join(
        f"<li><div class='row'>{_badge(x.severity, SEVERITY_CLS[x.severity])}"
        f'<a href="{e(links.call(x.call))}"><b>{e(x.client)}</b></a>'
        f'<span class="muted small">{e(fmt_date(by_file[x.call].call_date))}</span>'
        f"</div><div>{e(x.reason)}</div>"
        + (f"<blockquote>«{e(x.quote)}»</blockquote>" if x.quote else "")
        + "</li>"
        for x in attention_list(results, as_of)
    )
    attention_html = (
        f'<ul class="list">{attention}</ul>'
        if attention
        else '<p class="empty">Нет сигналов, требующих внимания.</p>'
    )

    summary = standard_summary(results)
    titles = {c.criterion_id: c.title for a in results for c in a.standard}
    top = max((n for _, n in summary), default=0) or 1
    bars = "".join(
        f'<div class="bar"><span>{e(titles.get(cid, cid))}</span>'
        f'<span class="track"><span class="fill" style="width:{n * 100 // top}%">'
        f'</span></span><span class="num">{n}</span></div>'
        for cid, n in summary
    )
    standard_html = bars or '<p class="empty">Нет данных по продажному стандарту.</p>'

    promises = sorted(
        manager_promises(results, as_of),
        key=lambda p: (PROMISE_ORDER[p.status], p.due),
    )
    rows = "".join(
        f'<tr><td><a href="{e(links.call(p.call))}">{e(p.client)}</a></td>'
        f"<td>{e(p.action)}</td><td>{e(fmt_date(p.due))}</td>"
        f"<td>{_badge(p.status, PROMISE_CLS[p.status])}</td></tr>"
        for p in promises
    )
    promises_html = (
        "<table><thead><tr><th>Клиент</th><th>Обещание</th><th>Срок</th>"
        f"<th>Статус</th></tr></thead><tbody>{rows}</tbody></table>"
        if rows
        else '<p class="empty">Проверенных обещаний менеджеров нет.</p>'
    )

    clients = len(build_chains(results))
    body = (
        "<h1>Обзор</h1>"
        f'<p class="sub">Звонков: {len(results)} · клиентов: {clients}</p>'
        f'<div class="grid">{stats}</div>'
        + _card("Требует внимания", attention_html)
        + _card("Частые отступления от продажного стандарта", standard_html)
        + _card("Обещания менеджеров", promises_html)
    )
    return _page("Обзор", "home", body, as_of, links)


# ------------------------------------------------------------------ звонки


def render_calls(
    results: list[CallAnalysis], as_of: date, links: Links = SERVER_LINKS
) -> str:
    present = [t for t in TYPE_LABEL if any(a.call_type == t for a in results)]
    chips = (
        '<button class="chip active" data-filter="">Все ' + f"{len(results)}</button>"
    )
    chips += "".join(
        f'<button class="chip" data-filter="{e(t)}">{e(TYPE_LABEL[t])} '
        f"{sum(a.call_type == t for a in results)}</button>"
        for t in present
    )
    rows = "".join(
        f'<tr data-type="{e(a.call_type)}"><td>{a.call_date:%d.%m.%Y}</td>'
        f'<td><a href="{e(links.call(a.source_file))}">{e(_client_name(a))}</a></td>'
        f"<td>{e(a.manager or '—')}</td>"
        f"<td>{e(TYPE_LABEL[a.call_type])}</td>"
        f"<td>{_outcome_badge(a.outcome)}</td>"
        f"<td>{_score_badge(a.grounding_score)}</td></tr>"
        for a in sorted(results, key=lambda a: a.call_date, reverse=True)
    )
    body = (
        "<h1>Звонки</h1>"
        f'<p class="sub">Всего разобрано: {len(results)}</p>'
        f'<div class="row chips">{chips}</div>'
        '<section class="card"><table><thead><tr><th>Дата</th><th>Клиент</th>'
        "<th>Менеджер</th><th>Тип</th><th>Итог</th><th>Сверка цитат</th></tr>"
        f"</thead><tbody>{rows}</tbody></table></section>"
    )
    return _page("Звонки", "calls", body, as_of, links, script=FILTER_JS)


# ------------------------------------------------------------ карточка звонка


def _quote_spans(text: str, quotes: Sequence[str]) -> list[tuple[int, int]]:
    """Где в исходном тексте стоят цитаты, найденные так же, как их сверял валидатор.

    Сверка идёт по normalize(); чтобы подсветить оригинал, нормализуем текст
    посимвольно (через тот же normalize) и запоминаем позицию каждого символа.
    """
    folded: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(text):
        piece = normalize(f"x{ch}x")[1:-1]  # «x» защищает пробелы от strip
        if piece == " " and folded and folded[-1] == " ":
            continue
        for c in piece:
            folded.append(c)
            origin.append(i)
    haystack = "".join(folded)

    spans: list[tuple[int, int]] = []
    for q in quotes:
        needle = normalize(q)
        pos = haystack.find(needle) if needle else -1
        while pos != -1:
            spans.append((origin[pos], origin[pos + len(needle) - 1] + 1))
            pos = haystack.find(needle, pos + len(needle))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _marked(text: str, spans: list[tuple[int, int]], lo: int, hi: int) -> str:
    out: list[str] = []
    pos = lo
    for start, end in spans:
        start, end = max(start, lo), min(end, hi)
        if start >= end:
            continue
        out.append(e(text[pos:start]))
        out.append(f"<mark>{e(text[start:end])}</mark>")
        pos = end
    out.append(e(text[pos:hi]))
    return "".join(out)


def _transcript_html(a: CallAnalysis, evidence: list[Evidence]) -> str:
    if not a.transcript:
        return '<p class="empty">Расшифровка недоступна.</p>'
    spans = _quote_spans(a.transcript, [ev.quote for ev in evidence if ev.verified])
    lines: list[str] = []
    offset = 0
    for line in a.transcript.split("\n"):
        if line.strip():
            lines.append(
                f"<p>{_marked(a.transcript, spans, offset, offset + len(line))}</p>"
            )
        offset += len(line) + 1
    return f'<div class="transcript">{"".join(lines)}</div>'


def _evidence_html(evidence: list[Evidence]) -> str:
    out = []
    for ev in evidence:
        badge = _badge("сверено", "ok") if ev.verified else _badge("не сверено", "bad")
        who = f"<b>{e(ev.speaker)}:</b> " if ev.speaker else ""
        out.append(f"<blockquote>{who}«{e(ev.quote)}»{badge}</blockquote>")
    return "".join(out)


def _flags_html(flags: list[str]) -> str:
    return "".join(f'<div class="flag">⚑ {e(f)}</div>' for f in flags)


def _items_card(title: str, items: list[Item], empty: str = "Не выявлено.") -> str:
    if not items:
        return _card(title, f'<p class="empty">{e(empty)}</p>')
    lis = "".join(
        f"<li><div>{e(it.text)} "
        f'<span class="muted small">уверенность: '
        f"{e(CONF_LABEL[it.confidence.value])}</span></div>"
        f"{_evidence_html(it.evidence)}{_flags_html(it.flags)}</li>"
        for it in items
    )
    return _card(title, f'<ul class="list">{lis}</ul>')


def _steps_card(a: CallAnalysis) -> str:
    if not a.next_steps:
        return _card("Следующие шаги", '<p class="empty">Согласованных шагов нет.</p>')
    lis = []
    for s in a.next_steps:
        d = s.date
        when = "дата не определена"
        if d is not None and d.resolved is not None:
            when = fmt_date(d.resolved) + (f", {d.time}" if d.time else "")
        said = (
            f" <span class='muted small'>(«{e(d.raw_expression)}»)</span>" if d else ""
        )
        agreed = "" if s.agreed else _badge("не согласовано", "warn")
        lis.append(
            f"<li><div class='row'><b>{e(s.action)}</b>{_badge(s.owner, 'plain')}"
            f"{agreed}</div><div>{e(when)}{said}</div>"
            f"{_evidence_html(s.evidence)}{_flags_html(s.flags)}</li>"
        )
    return _card("Следующие шаги", f'<ul class="list">{"".join(lis)}</ul>')


def _standard_card(a: CallAnalysis) -> str:
    if not a.standard:
        return ""
    lis = []
    for c in a.standard:
        mark, cls = CHECK_MARK[c.status]
        comment = f'<div class="muted small">{e(c.comment)}</div>' if c.comment else ""
        lis.append(
            f'<li><span class="chk {cls}">{mark}</span><div>'
            f'<div class="chk-title">{e(c.title)}</div>{comment}'
            f"{_evidence_html(c.evidence)}{_flags_html(c.flags)}</div></li>"
        )
    return _card(
        "Чек-лист стандарта", f'<ul class="list checklist">{"".join(lis)}</ul>'
    )


def _all_evidence(a: CallAnalysis) -> list[Evidence]:
    claims: list[Item | NextStep | Constraint | StandardCheck] = [
        *a.client_needs,
        *a.risks,
        *a.manager_mistakes,
        *a.needs_supervisor_attention,
        *a.next_steps,
        *a.constraints,
        *a.standard,
    ]
    dates = [
        *a.all_dates,
        *(s.date for s in a.next_steps if s.date),
        a.next_action_date,
    ]
    return [ev for c in claims for ev in c.evidence] + [
        ev for d in dates if d is not None for ev in d.evidence
    ]


def render_call(a: CallAnalysis, as_of: date, links: Links = SERVER_LINKS) -> str:
    notes = ""
    if a.data_gaps or a.validation_flags:
        notes = _card(
            "Недостаточно данных и флаги проверки",
            "<ul class='list'>"
            + "".join(f"<li>{e(g)}</li>" for g in [*a.data_gaps, *a.validation_flags])
            + "</ul>",
        )
    constraints = (
        _card(
            "Ограничения клиента",
            "<ul class='list'>"
            + "".join(
                f"<li>{e(c.text)}{_evidence_html(c.evidence)}</li>"
                for c in a.constraints
            )
            + "</ul>",
        )
        if a.constraints
        else ""
    )
    body = (
        "<h1>Карточка звонка</h1>"
        f'<p class="sub">{e(_client_name(a))} · {e(fmt_date(a.call_date))}, '
        f"{e(a.call_weekday)} · менеджер: {e(a.manager or '—')}</p>"
        f'<div class="row" style="margin-bottom:20px">'
        f"{_badge(TYPE_LABEL[a.call_type])}{_outcome_badge(a.outcome)}"
        "<span class='muted small'>сверка цитат</span>"
        f"{_score_badge(a.grounding_score)}"
        f"</div>"
        + _card("Итог разговора", f"<p style='margin:0'>{e(a.summary)}</p>")
        + _steps_card(a)
        + _items_card("Потребности клиента", a.client_needs)
        + _items_card("Риски", a.risks)
        + _items_card("Ошибки менеджера", a.manager_mistakes)
        + _items_card(
            "Требует внимания руководителя",
            a.needs_supervisor_attention,
            "Сигналов нет.",
        )
        + constraints
        + _standard_card(a)
        + notes
        + _card("Транскрипт", _transcript_html(a, _all_evidence(a)))
    )
    return _page("Карточка звонка", "calls", body, as_of, links)


# ------------------------------------------------------------------ клиенты


def render_clients(
    results: list[CallAnalysis], as_of: date, links: Links = SERVER_LINKS
) -> str:
    chains = sorted(build_chains(results), key=lambda c: c.last_call_date, reverse=True)
    cards = []
    for chain in chains:
        calls = sorted(
            (a for a in results if _client_key(a) == chain.client_id),
            key=lambda a: a.call_date,
        )
        steps = "".join(
            f"<li><div class='row'><b>{e(fmt_date(a.call_date))}</b>"
            f"{_badge(TYPE_LABEL[a.call_type])}{_outcome_badge(a.outcome)}</div>"
            f'<a href="{e(links.call(a.source_file))}">{e(a.summary)}</a></li>'
            for a in calls
        )
        cards.append(
            '<section class="card chain"><div class="chain-head">'
            f"<b>{e(chain.client)}</b>"
            f'<span class="muted small">звонков: {chain.calls_count} · '
            f"последний: {e(fmt_date(chain.last_call_date))}</span></div>"
            f'<ul class="timeline">{steps}</ul></section>'
        )
    body = (
        "<h1>Клиенты</h1>"
        f'<p class="sub">Цепочек звонков: {len(chains)}</p>' + "".join(cards)
    )
    return _page("Клиенты", "clients", body, as_of, links)


def render_not_found(as_of: date, links: Links = SERVER_LINKS) -> str:
    body = (
        "<h1>Страница не найдена</h1>"
        '<p class="sub">Такой страницы нет. Вернитесь к обзору или списку звонков.</p>'
    )
    return _page("Страница не найдена", "", body, as_of, links)


# ----------------------------------------------------------- маршруты и сервер


def route(path: str, results: list[CallAnalysis], as_of: date) -> tuple[int, str]:
    clean = unquote(urlsplit(path).path)
    clean = clean.rstrip("/") or "/"
    pages: dict[str, Callable[[], str]] = {
        "/": lambda: render_overview(results, as_of),
        "/calls": lambda: render_calls(results, as_of),
        "/clients": lambda: render_clients(results, as_of),
    }
    if clean in pages:
        return 200, pages[clean]()
    name = clean.removeprefix("/call/") if clean.startswith("/call/") else None
    for a in results:
        if a.source_file == name:
            return 200, render_call(a, as_of)
    return 404, render_not_found(as_of)


def make_server(
    results: list[CallAnalysis], as_of: date, port: int
) -> ThreadingHTTPServer:
    """HTTP-сервер на 127.0.0.1; результаты уже загружены и не перечитываются."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = route(self.path, results, as_of)
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

    return ThreadingHTTPServer((HOST, port), Handler)


def build_site(results: list[CallAnalysis], as_of: date, out: Path) -> None:
    """Те же страницы в виде файлов с относительными ссылками."""
    for a in results:
        if Path(a.source_file).name != a.source_file:
            raise ValueError(f"source_file содержит путь: {a.source_file!r}")
    top, nested = Links(root="", static=True), Links(root="../", static=True)
    (out / "call").mkdir(parents=True, exist_ok=True)
    files = {
        "index.html": render_overview(results, as_of, top),
        "calls.html": render_calls(results, as_of, top),
        "clients.html": render_clients(results, as_of, top),
        "404.html": render_not_found(as_of, top),
    }
    for a in results:
        files[f"call/{a.source_file}.html"] = render_call(a, as_of, nested)
    for name, html_text in files.items():
        (out / name).write_text(html_text, encoding="utf-8")
