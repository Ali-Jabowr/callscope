# callscope

Разбор клиентских звонков отдела продаж: LLM извлекает смысл, детерминированный код проверяет факты.
Python 3.12, uv, pydantic 2, pyyaml. Web UI — только стандартная библиотека (http.server + HTML-строки), без шаблонизаторов.

## Commands
- Verify everything (the gate): `./.claude/verify.sh` (must pass before you say you are done)
- One test: `uv run pytest tests/test_x.py::test_name -q`
- Offline demo, no LLM, no keys: `uv run python -m callscope report --source demo/analysis.json`

## How to prove a change works
- New behaviour: the test that asserts it must fail if the change is reverted.
- Expected values are literals, never computed with the code under test. No if/loops inside a test.
- Tests never call a real LLM: use a fake provider that returns canned JSON.

## Gotchas
- All data in the repo is synthetic (fictional company «ТехноПоток» and its clients). Never add real names, phones, companies or recordings.
- The LLM provider is chosen by config/CLI flag, never hard-coded in the pipeline: providers live in `callscope/providers.py` behind `LLMProvider`.
- Every claim the model makes carries a verbatim quote; `validate.py` marks it verified/unverified against the transcript. Unverified claims never reach management lists.

## Code style
- Errors: raise with context or return; never `except Exception: pass`.
- User-facing text (UI, reports, CLI messages) is Russian; code identifiers are English.

## Boundaries
- Ask first: new dependencies, changes to `.claude/verify.sh` or CI.
- Never: commit secrets; touch `.env`.
