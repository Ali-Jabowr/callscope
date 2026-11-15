"""CLI: run | report | eval"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .models import CallAnalysis


def cmd_run(args: argparse.Namespace) -> int:
    from .pipeline import analyze_dir
    from .providers import get_provider

    provider = get_provider(args.provider)
    print(f"Провайдер: {provider.name}  |  транскрипты: {args.transcripts}")
    results = analyze_dir(Path(args.transcripts), provider, workers=args.workers)
    if not results:
        print("Ни один транскрипт не обработан.")
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = [r.model_dump(mode="json") for r in results]
    (out / "analysis.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJSON: {out / 'analysis.json'}")
    _render(results, out)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .validate import revalidate

    src = Path(args.source)
    data = json.loads(src.read_text(encoding="utf-8"))
    results = [CallAnalysis.model_validate(d) for d in data]

    # Негативный тест из README: правленая цитата обязана отловиться заново,
    # а не отрендериться со старой пометкой verified из JSON.
    tdir = Path(args.transcripts)
    rechecked = 0
    if tdir.is_dir():
        for a in results:
            tp = tdir / a.source_file
            if tp.exists():
                revalidate(a, tp)
                rechecked += 1
    if rechecked:
        print(f"Валидаторы перечитаны по транскриптам из {tdir}/ ({rechecked} шт.)")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _render(results, out)
    return 0


def _render(results: list[CallAnalysis], out: Path) -> None:
    from .render import render_csv, render_html, render_markdown

    (out / "report.html").write_text(render_html(results), encoding="utf-8")
    (out / "report.csv").write_text(render_csv(results), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(results), encoding="utf-8")
    print(f"HTML: {out / 'report.html'}")
    print(f"CSV:  {out / 'report.csv'}")
    print(f"MD:   {out / 'report.md'}")


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluate import run_eval

    return run_eval(Path(args.source), Path(args.gold))


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"ожидается дата ГГГГ-ММ-ДД, получено {value!r}"
        ) from exc


def _load_for_ui(source: str) -> list[CallAnalysis] | None:
    from .web import load_results

    try:
        return load_results(Path(source))
    except (OSError, ValueError) as exc:  # нет файла, битый JSON, не та схема
        print(f"Не удалось прочитать {source}: {exc}", file=sys.stderr)
        return None


def cmd_site(args: argparse.Namespace) -> int:
    from .web import build_site

    results = _load_for_ui(args.source)
    if results is None:
        return 1
    out = Path(args.out)
    build_site(results, args.as_of or date.today(), out)
    print(f"Сайт: {out / 'index.html'}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import HOST, make_server

    results = _load_for_ui(args.source)
    if results is None:
        return 1
    try:
        server = make_server(results, args.as_of or date.today(), args.port)
    except OSError as exc:
        print(f"Не удалось занять порт {args.port}: {exc}", file=sys.stderr)
        return 1
    print(f"Откройте http://{HOST}:{args.port}/  (Ctrl+C — остановить)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="callscope",
        description=(
            "Структурированный разбор клиентских звонков с контролем галлюцинаций"
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="прогнать транскрипты через LLM и собрать отчёт")
    r.add_argument("transcripts", nargs="?", default="transcripts")
    r.add_argument("-o", "--out", default="out")
    r.add_argument(
        "--provider",
        default="claude",
        help="claude | claude:model | openai | openai:model",
    )
    r.add_argument("--workers", type=int, default=4)
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser(
        "report", help="пересобрать отчёт из сохранённого JSON, без LLM"
    )
    rp.add_argument("--source", default="out/analysis.json")
    rp.add_argument(
        "--transcripts",
        default="transcripts",
        help="каталог транскриптов для повторной сверки цитат и дат",
    )
    rp.add_argument("-o", "--out", default="out")
    rp.set_defaults(func=cmd_report)

    ev = sub.add_parser("eval", help="сверить результат с ручным эталоном")
    ev.add_argument("--source", default="out/analysis.json")
    ev.add_argument("--gold", default="demo/gold.yaml")
    ev.set_defaults(func=cmd_eval)

    sv = sub.add_parser("serve", help="локальный веб-интерфейс (127.0.0.1)")
    sv.add_argument("--source", default="out/analysis.json")
    sv.add_argument(
        "--as-of", type=_iso_date, default=None, help="дата отсчёта, ГГГГ-ММ-ДД"
    )
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=cmd_serve)

    st = sub.add_parser(
        "site", help="записать страницы интерфейса как статический HTML"
    )
    st.add_argument("--source", default="out/analysis.json")
    st.add_argument(
        "--as-of", type=_iso_date, default=None, help="дата отсчёта, ГГГГ-ММ-ДД"
    )
    st.add_argument("-o", "--out", default="out/site")
    st.set_defaults(func=cmd_site)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
