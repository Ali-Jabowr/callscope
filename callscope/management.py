"""Вид руководителя: цепочки звонков по клиентам и список «требует внимания».

Всё детерминированно, без LLM.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from callscope.models import CallAnalysis, Evidence, Item
from callscope.validate import normalize

# Признаки риска ухода клиента: поднимают сигнал руководителю до «высокой».
CHURN_STEMS = tuple(
    normalize(s)
    for s in (
        "уйд",
        "уход",
        "другая систем",
        "другой систем",
        "другую систем",
        "другие решени",
        "другие систем",
        "дешевле",
        "не продл",
    )
)


@dataclass(frozen=True)
class Chain:
    client_id: str
    client: str
    calls_count: int
    last_call_date: date
    last_outcome: str
    last_call_type: str


@dataclass(frozen=True)
class Promise:
    client: str
    call: str
    action: str
    due: date
    status: str
    quote: str


@dataclass(frozen=True)
class Attention:
    client: str
    call: str
    reason: str
    severity: str
    quote: str


def _client_key(a: CallAnalysis) -> str:
    # Звонок без client_id не склеиваем с другими: он образует свою цепочку.
    return a.client_id or a.source_file


def _verified(evidence: list[Evidence]) -> bool:
    return bool(evidence) and all(ev.verified is True for ev in evidence)


def _quote(evidence: list[Evidence]) -> str:
    return evidence[0].quote if evidence else ""


def _client_name(a: CallAnalysis) -> str:
    return a.company or a.client_id or a.source_file


def build_chains(analyses: list[CallAnalysis]) -> list[Chain]:
    groups: dict[str, list[CallAnalysis]] = {}
    for a in sorted(analyses, key=lambda a: a.call_date):
        groups.setdefault(_client_key(a), []).append(a)
    return [
        Chain(
            client_id=key,
            client=_client_name(calls[-1]),
            calls_count=len(calls),
            last_call_date=calls[-1].call_date,
            last_outcome=calls[-1].outcome,
            last_call_type=calls[-1].call_type,
        )
        for key, calls in sorted(groups.items())
    ]


def _status(due: date, as_of: date) -> str:
    if due < as_of:
        return "просрочено"
    if due == as_of:
        return "сегодня"
    return "впереди"


def manager_promises(analyses: list[CallAnalysis], as_of: date) -> list[Promise]:
    return [
        Promise(
            client=_client_name(a),
            call=a.source_file,
            action=step.action,
            due=step.date.resolved,
            status=_status(step.date.resolved, as_of),
            quote=_quote(step.evidence),
        )
        for a in analyses
        for step in a.next_steps
        if step.owner == "менеджер"
        and step.agreed
        and step.date is not None
        and step.date.resolved is not None
        and _verified(step.evidence)
    ]


def _is_churn(item: Item) -> bool:
    text = normalize(" ".join([item.text, *(ev.quote for ev in item.evidence)]))
    return any(stem in text for stem in CHURN_STEMS)


def _first_verified_quote(items: list[Item]) -> str:
    for item in items:
        for ev in item.evidence:
            if ev.verified is True:
                return ev.quote
    return ""


def _entries(a: CallAnalysis, as_of: date) -> list[Attention]:
    client, call = _client_name(a), a.source_file
    out = [
        Attention(
            client,
            call,
            item.text,
            "высокая" if _is_churn(item) else "средняя",
            _quote(item.evidence),
        )
        for item in a.needs_supervisor_attention
        if _verified(item.evidence)
    ]
    out += [
        Attention(
            client,
            call,
            f"просроченное обещание менеджера: {p.action}",
            "высокая",
            p.quote,
        )
        for p in manager_promises([a], as_of)
        if p.status == "просрочено"
    ]
    if a.outcome == "отказ":
        out.append(
            Attention(
                client,
                call,
                a.summary,
                "средняя",
                _first_verified_quote([*a.risks, *a.needs_supervisor_attention]),
            )
        )
    failed = [c for c in a.standard if c.status == "не_выполнено"]
    if a.call_type == "новая_продажа" and len(failed) >= 2:
        out.append(
            Attention(
                client,
                call,
                "отступления от продажного стандарта",
                "средняя",
                _quote(failed[0].evidence),
            )
        )
    return out


def attention_list(analyses: list[CallAnalysis], as_of: date) -> list[Attention]:
    dates = {a.source_file: a.call_date for a in analyses}
    entries = [e for a in analyses for e in _entries(a, as_of)]
    return sorted(entries, key=lambda e: (e.severity != "высокая", dates[e.call]))


def standard_summary(analyses: list[CallAnalysis]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for a in analyses:
        if a.call_type != "новая_продажа":
            continue
        for c in a.standard:
            counts[c.criterion_id] += c.status == "не_выполнено"
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
