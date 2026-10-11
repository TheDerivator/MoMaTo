# MoMaTo

Internal project management for an organisation structured as a tree: browse projects through the
organisation, plan them (gantt, planned days per person), keep remarks and a logbook, book hours
on a playful timesheet, and see planned versus spent time per person.

- What it must do and the rules behind every number: [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md)
- Why it is built this way: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- The delivery plan and its status: [`docs/PLAN.md`](docs/PLAN.md)
- How the code is organised: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
  [`docs/CODEMAP.md`](docs/CODEMAP.md)

## Develop

Needs [uv](https://docs.astral.sh/uv/) (Python 3.14 is installed by it) and, for the JS unit tests,
Node 22 or newer.

```sh
uv sync                                   # runtime + dev dependencies
uv run python -m momato serve --reload    # http://127.0.0.1:8000, API docs at /api/docs
uv run python scripts/check.py --fix      # the quality gate: format, lint, types, contracts, tests
uv run playwright install chromium        # once, for the browser tests
uv run python scripts/check.py --e2e      # the gate including browser tests
```

Settings come from `MOMATO_*` environment variables or a `.env` file; see `.env.example`.

## Install on a server

```sh
uv sync --no-dev                          # no test or tooling packages
uv sync --no-dev --extra mssql            # with the MS SQL driver (pyodbc)
```
