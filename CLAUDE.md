# MoMaTo: guide for AI agents

Internal project management tool (FastAPI + SQLAlchemy backend, static Preact/htm frontend).
Read in this order:

1. [`docs/PLAN.md`](docs/PLAN.md): the delivery plan (M0–M13), what is done, what is next.
   **Keep its status table and checkboxes current** when you finish work.
2. [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md): what to build and the exact rules behind every
   number (IDs like `TS-7`, rule sections like `R4.8`).
3. [`docs/DECISIONS.md`](docs/DECISIONS.md): why things are the way they are. Don't silently
   reverse a *Confirmed* decision; ask.
4. [`docs/CODEMAP.md`](docs/CODEMAP.md): generated tree of every file with a one-line summary.
   Use it to jump to the right file instead of searching.
5. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): layers, portability rules, recipes.

Design reference (not code): `design_handoff_kite_pm_tool/` (README + the prototype
`Kite v3.dc.html`). Conventions follow TaskBoard (`U:\Projects\TaskBoard`, D-002): when in doubt,
do what TaskBoard does.

## Commands

```sh
uv run python scripts/check.py --fix   # format, lint, types, contracts, codemap, trace, tests: run before finishing
uv run python scripts/check.py --e2e   # also browser tests (needs: uv run playwright install chromium)
uv run pytest tests/unit -q            # fast subset
uv run pytest -m e2e                   # only the browser tests
node --test tests/js/*.test.mjs        # only the JS unit tests
uv run python scripts/trace.py         # which requirement IDs have a test
uv run python -m momato serve --reload # dev server on http://127.0.0.1:8000
```

`python` is not on the shell PATH: always go through `uv run`.

## Rules

- Layers: `cli → web → api → services → schemas → identity → db → domain`, imports only go rightwards
  (import-linter enforces it). Routers never touch the database; services enforce permissions.
- `app.py` stays a 3-line entrypoint.
- Every file starts with a one-line docstring/comment; it feeds the code map.
- Schema changes need an Alembic migration (a test compares models and migrations).
- Keep code portable to MS SQL (rules in REQUIREMENTS §8.2) and OS-neutral (Windows and Linux).
- What can be tested is tested (D-011): rules as unit tests, endpoints with their 401/403/404/409/422
  cases, pure JS in `tests/js/`, flows in `tests/e2e/`. A test names the requirement IDs it proves
  in its docstring or name (`[TS-7]`, `[R4.8]`); `scripts/trace.py` lists IDs without a test.
- No external network resources at runtime: vendor JS libraries and fonts under `momato/static/`.
- No inline styles or scripts (the CSP forbids them): classes and custom properties in CSS; dynamic
  values go through the CSSOM (`el.style.width = ...`, which the CSP allows).
- Test and tooling packages go in the `dev` group (`uv add --dev`), never in runtime dependencies.

## Backslash-heavy content: avoid Bash heredocs

Heredocs in the Bash tool can mangle backslashes silently. Write such files with the Write tool, or
edit them with Edit; then run scripts separately (`uv run python script.py`).
