# MoMaTo: architecture

How the code is organised and the rules that keep it that way. What the product does is in
[`REQUIREMENTS.md`](REQUIREMENTS.md); [`CODEMAP.md`](CODEMAP.md) lists every file.

## Layers

```text
cli → web → api → services → schemas → identity → db → domain
```

Imports only go rightwards (import-linter, contract "Layers"; `tests/architecture/`).

| Layer | Holds | Must not |
|---|---|---|
| `domain` | Rules as pure functions and small value types: calendar, capacity, planning, tasks, timesheet, numbering, logbook, profile fields. | import a framework, SQLAlchemy, Pydantic or `momato.config`. |
| `db` | SQLAlchemy models, sessions, migrations, id-list helpers. | contain business rules. |
| `identity` | Accounts, sessions, passwords, providers, the access policy (`can(...)`, query filters). | |
| `schemas` | Pydantic request and response shapes. | |
| `services` | Use cases: load, apply domain rules, check the policy, write (with logbook entries in the same transaction), commit. | know about HTTP. |
| `api` | Thin routers, dependencies, the one place domain errors become 404 / 409 / 422. | touch the database; routers call services. |
| `web` | `create_app()`, middleware (security headers, compression), the static frontend. | |
| `cli` | `python -m momato ...`. | |

`momato/config.py` (settings) and `momato/profiles/` (the deployment profile: TOML files, one per
deployment variant) sit beside the layers. The profile's model and the validation of its values
are pure domain code (`domain/fields.py`); `services/profile.py` only reads the file.

## Rules of the domain, in short

- Days and ratios are exact `Fraction`s, time is integer minutes (D-040); display rounds half up.
- `calendar` (weeks, quarters, buckets), `capacity` (work patterns, availability, load and compare
  classes), `planning` (planned days into periods and weeks, project days), `tasks` (status,
  timeline text, the standard phases), `timesheet` (booking and week states), `logbook` (which
  entries a change produces), `fields` (profile model and detail values), `formatting`, `numbering`,
  `projects` (statuses and priorities).
- A rule that the browser needs too has a JSON table in `tests/fixtures/` that both languages pass:
  `week_states`, `booking`, `load_classes`, `compare_classes`, `task_status`, `buckets`,
  `formatting`.

## Persistence notes

- One org root: the org editor (M10) keeps exactly one node without a parent; no constraint can
  express it portably (a filtered unique index on NULL parents is not enforced by SQLite).
- Planned days reference the project's members with a composite foreign key (D-041); time entries
  reference a task together with its project, and the three filtered unique indexes keep one row
  per person, day and target, including *General* (a task of NULL).
- The sample data (`services/sample_data.py` with `services/data/sample-data.json`) is built as
  plain specs by `build_sample` and inserted by `load_sample_data`; tests derive expectations from
  the specs, not from the database.

## Remarks and images

- Remarks and replies are `posts` (one level; a reply has a `parent_id` of the same project).
  `services/remarks.py` lists, posts, edits (keeping the earlier text as `post_revisions`) and
  deletes; `services/markdown.py` renders on the server: CommonMark, no raw HTML, sanitized with an
  allow-list (nh3), images only from `api/attachments/`, `@name` and `#4102` decorated.
- Images are uploaded first (`POST /api/projects/{n}/attachments`) as drafts of the uploader and
  claimed by the remark whose Markdown refers to them; drafts older than a day are removed on the
  next upload. A file is `<data_dir>/uploads/<public_id>` (32 hex digits, no extension; the type
  is sniffed from its bytes), served only to people who may see the project.
- The browser shows what the server rendered (`dangerouslySetInnerHTML` of sanitized HTML), so the
  composer's Preview calls the same renderer (`POST /api/markdown/preview`).

## Administration and profile

- Three services behind `/api/admin`: `OrgAdminService` (org tree, `org.manage`),
  `PeopleAdminService` (a person's data and availability with `org.manage`; sign-in, password,
  suspension and assignments with `users.manage`, the latter by way of `AccessService`) and
  `AccessService` (roles, default grants, audit log, the lockout guard). Each constructor or method
  asks the principal for the permission it needs; routers only shape input and output.
- Every change writes an `audit_log` row in the same transaction (`services/audit.py`); the log
  never holds a password. `ensure_administrator_remains` runs after anything that could remove the
  last active administrator (status, assignments, a role's permissions).
- `GET /api/account` is the Profile page's document; changing the password is `/api/auth/password`.
- In the browser `views/admin*.js` are the sections and `lib/admin.js` the pure parts (which
  sections a person may open, scope choices, work-pattern parsing, audit wording).

## API tokens and exports

- A Bearer token is resolved in `AuthService.principal_for_request` (`identity/api_tokens.py`):
  the owner's principal with its grants filtered to the scope, plus `token_id`/`token_name`/
  `token_scope`. `AccessPolicy` and `Principal.token_allows` apply the scope to implicit rights;
  `get_principal` (api/deps.py) refuses non-safe methods for read tokens and notes "last used".
- "via": `LogEntry.api_token_id`, `Post.api_token_id`/`edited_api_token_id`,
  `PostRevision.api_token_id` and `TimeEntry.api_token_id`; services pass `principal.token_id`
  when they write, outputs resolve names with `common.token_names`.
- `services/exports.py` builds a table (header + rows from batches) and `services/export_files.py`
  writes it as CSV or XLSX into a spooled file; the router streams the file. The project list is
  read through `ProjectService.export_batches`, so it shares its filters and visibility with the
  screen; time entries use `AccessPolicy.people_hours_filter`.
- `GET /api/agent-guide` renders `services/data/agent-guide.md` and lists every endpoint of the
  OpenAPI document except the `auth`, `tokens` and `administration` tags.

## Rules that are easy to break

- **Rules are pure functions.** A number the user sees comes from a function in `momato/domain/`
  (Python) and, where the browser needs it, a mirror in `momato/static/js/lib/` (JS). Both are
  tested against the same JSON tables in `tests/fixtures/`.
- **Routers never decide access.** One policy object answers `can(...)` and builds query filters;
  services call it. Lists, counts and exports only contain what the caller may see.
- **Scale is designed in** (D-028). No endpoint returns all projects; lists are paged on the
  server, counts and sums are computed in SQL, and a statement-counter test asserts that the
  number of SQL statements of a request does not grow with the data.
- **Time is integer minutes**, days are `Numeric`, never floats (D-038, §8.2).
- **Date arithmetic is Python's**, not SQL's: bucket bounds are passed as parameters.
- **No external network resources at runtime**; the CSP forbids inline scripts (but the import map,
  by hash) and inline styles. Dynamic styling uses CSS custom properties or the CSSOM.

## MS SQL portability (REQUIREMENTS §8.2)

Unicode text types; explicit lengths on indexed strings; no cascades on self-references or on
multiple paths; case-insensitive uniqueness normalised in code; a constraint naming convention;
filtered unique indexes for nullable unique columns; no CHECK constraints on enums;
`NVARCHAR(max)` and `DATETIME2` variants; at most 2,100 parameters per statement (long id lists are
written into the SQL as integers; every test runs with a guard that fails above 2,100).

## Tests

See the table in [`PLAN.md`](PLAN.md#test-strategy). Shared fixtures are in `tests/conftest.py`
(settings with the date pinned to Thursday 8 October 2026, an HTTP client), helpers such as the
SQL statement counter in `tests/helpers.py`, and the browser guard rails (console errors, requests
to other origins, axe) in `tests/e2e/conftest.py`.

## Recipes

**Add an endpoint**: a schema in `schemas/`, a service function in `services/` (policy check,
domain rules, logbook entries when core project fields change), a router function in
`api/routers/` that only validates and calls it, registered in `api/__init__.py`. Add API tests
with the 401 / 403 / 404 / 409 / 422 cases and tag them with the requirement IDs.

**Change the schema**: edit the model in `db/models/`, then
`uv run alembic revision --autogenerate -m "..."` and review the migration; a test fails when models
and migrations differ. Check the MS SQL portability rules above.

**Add a rule**: a pure function in `domain/` with a unit test (and a hypothesis property when the
rule has an invariant); if the browser needs it too, add rows to the shared fixture table and a
JS mirror with its `node --test`.

**Add a screen**: a view in `static/js/views/`, pure logic in `static/js/lib/` with tests in
`tests/js/`, an e2e test, and an axe check in the four appearances.
