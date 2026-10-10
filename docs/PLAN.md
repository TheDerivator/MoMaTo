# MoMaTo: delivery plan

This file tracks the build. What to build is in [`REQUIREMENTS.md`](REQUIREMENTS.md), why in
[`DECISIONS.md`](DECISIONS.md). Each milestone lists its deliverables (checkboxes), the
requirements it delivers, and an **acceptance gate**: the automated checks that must pass before
it counts as done. Keep the status table and the checkboxes current as work lands.

Design reference: [`design_handoff_kite_pm_tool/`](../design_handoff_kite_pm_tool/README.md)
(README + the prototype `Kite v3.dc.html`). Conventions follow TaskBoard (`U:\Projects\TaskBoard`,
D-002): when in doubt, do what TaskBoard does.

## Status

| #   | Milestone                                              | Status        |
|-----|--------------------------------------------------------|---------------|
| M0  | Foundations and guardrails                             | ☐ not started |
| M1  | Domain rules, persistence, profile, sample data        | ☐ not started |
| M2  | Identity and access control                            | ☐ not started |
| M3  | Projects API                                           | ☐ not started |
| M4  | Frontend shell, design system, Projects list           | ☐ not started |
| M5  | Project page: Overview, Remarks, Logbook, All details  | ☐ not started |
| M6  | Project page: Planning, People & days                  | ☐ not started |
| M7  | My timesheet                                           | ☐ not started |
| M8  | People planning                                        | ☐ not started |
| M9  | Action plans                                           | ☐ not started |
| M10 | Administration and profile                             | ☐ not started |
| M11 | Export (proof of concept) and API tokens               | ☐ not started |
| M12 | Single sign-on                                         | ☐ not started |
| M13 | Hardening and release                                  | ☐ not started |

Legend: ☐ not started · ◐ in progress · ☑ done

---

## Test strategy

"Everything that can be tested is tested" (D-011). The levels:

| Level | Tool | What it proves | Folder | Runs |
|---|---|---|---|---|
| Domain unit | pytest + hypothesis | every rule of REQUIREMENTS §4, with properties where a rule has an invariant | `tests/unit` | always |
| JS unit | `node --test` | pure modules in `static/js/lib/`: formatting, filters, geometry, timesheet rules, planning cells | `tests/js` | always |
| Integration | pytest on a real database | constraints, migrations, seeding, sample data, MS SQL DDL (compiled offline), the 2,100-parameter guard | `tests/integration` | always |
| API | pytest + TestClient (httpx2) | every endpoint: success **and** 401 / 403 / 404 / 409 / 422; permission and privacy matrices; paging; logbook side effects | `tests/api` | always |
| Architecture | pytest + import-linter | layer contracts, thin `app.py`, self-describing files, fresh code map, dependency groups | `tests/architecture` | always |
| End-to-end | Playwright (Chromium) against a live server with the sample data | user flows, persistence after reload, layout spot checks, no request to another origin, no console error | `tests/e2e` (`-m e2e`) | `check.py --e2e`; before closing a milestone |
| Accessibility | axe-playwright-python | every screen, dialog and popover in the four appearance combinations | `tests/e2e` | with e2e |
| Scale | pytest (`-m scale`) | the budgets of REQUIREMENTS §8.5 on the scale data set | `tests/api`, `tests/e2e` | M13, before releases |
| MS SQL | API + integration suites with `MOMATO_TEST_DATABASE_URL` | portability on a real SQL Server | | when a database is available |
| Visual | Playwright screenshots (`-m visual`) | unintended rendering changes | `tests/e2e/visual` | opt-in (M13) |

Principles:

1. **Rules are pure functions** (`momato/domain/`, `static/js/lib/`), so they are tested without a
   database or a browser; services and views stay thin.
2. **One fixture table, two languages**: a rule needed by both server and browser is tested in
   Python and in JS against the same JSON table in `tests/fixtures/` (week states, booking, load
   and compare classes, task status, buckets, formatting). TaskBoard's `change_states.json` pattern.
3. **Fixed clock, deterministic data**: tests pin `MOMATO_TODAY=2026-10-08` (Thursday, week 41);
   the sample data is curated JSON plus a seeded generator. Expected numbers are computed in the
   test from the sample's rows, never copied from the app's output.
4. Each test gets a copy of a migrated template database (fast); the API and integration suites
   run against any database URL (`MOMATO_TEST_DATABASE_URL`).
5. Browser tests wait on states, never on time, and run with reduced motion except the tests about
   motion itself.
6. **Coverage gates** in `scripts/check.py`: `momato/domain` 100 % of branches, `momato/` at least
   90 %, `static/js/lib/` at least 95 % of lines (node's built-in coverage).
7. **Traceability**: a test names the requirements and rules it proves in its docstring or name
   (`[TS-7]`, `[R4.8]` for REQUIREMENTS §4.8). `scripts/trace.py` lists IDs without a test. A
   milestone's gate includes "every requirement listed for it is tagged in a test"; M13 runs it in
   strict mode. Non-functional requirements (§8) are covered by the M13 gate.
8. **Scale is designed in, not bolted on** (D-028): from M3 on, list endpoints are paged and a
   statement counter asserts that the number of SQL statements per request does not grow with the
   data; M13 measures the budgets on the scale data set.
9. **Not automatable**, kept as a manual checklist in `docs/OPERATIONS.md`: Kerberos in a real
   domain, a real Entra ID tenant, IIS, visual fidelity to the design (each UI milestone ends with
   screenshots compared by eye against the prototype in the four appearances).

**Definition of done** for every milestone: deliverables checked; `uv run python scripts/check.py
--fix --e2e` green; the gate's tests exist and are tagged; this file's status updated; new
decisions in DECISIONS.md; ARCHITECTURE.md updated when the structure changes; CODEMAP regenerated.

---

## Milestones

### M0 · Foundations and guardrails

- [ ] Dependencies (D-003), runtime: `uv add fastapi uvicorn sqlalchemy alembic pydantic-settings
      python-multipart`; development: `uv add --dev pytest pytest-cov hypothesis httpx2 ruff pyright
      import-linter pytest-playwright axe-playwright-python`; MS SQL: `uv add --optional mssql
      pyodbc`. Later milestones add theirs the same way (argon2-cffi in M2, markdown-it-py and nh3
      in M5, xlsxwriter and openpyxl (dev) in M11, pyjwt[crypto] and pyspnego in M12, pillow (dev)
      in M13).
- [ ] Replace uv init's `main.py` with `app.py` (three lines) and the `momato/` package with its
      layers (`cli, web, api, services, schemas, identity, db, domain`); `python -m momato serve`;
      pyproject description.
- [ ] `momato/config.py` (`MOMATO_` settings, the app folder's `.env`), `.env.example`, `var/` ignored.
- [ ] `GET /api/health`; the web layer serves `static/index.html` (placeholder) for app routes.
- [ ] Tooling configuration in pyproject (TaskBoard's): ruff rules, pyright strict on `momato/`,
      import-linter contracts (layers; pure domain; routers never touch the database), pytest
      (markers `e2e`, `scale`, `visual`, `requires_sqlite`; warnings are errors; e2e off by default),
      coverage.
- [ ] `scripts/check.py` (fix, lint, format, types, contracts, code map, trace, pytest with coverage
      gates, `node --test`), `scripts/gen_codemap.py`, `scripts/trace.py`.
- [ ] Test skeleton: `tests/{unit,integration,api,architecture,e2e,js,fixtures}`, conftest with
      settings and database fixtures, the statement counter, e2e live-server fixture and helpers
      (no request to another origin, no console error, axe).
- [ ] `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/CODEMAP.md`.

**Acceptance gate**: `check.py` is green; an API test gets 200 from `/api/health`; architecture
tests: contracts hold, `app.py` is a thin entrypoint, every file describes itself, the code map is
fresh; a dependency test reads pyproject and `uv.lock` and fails if any test or tooling package is a
runtime dependency; `trace.py` lists every requirement ID (report mode); an e2e smoke test loads the
placeholder page without contacting another origin.

### M1 · Domain rules, persistence, profile, sample data

Delivers REQUIREMENTS §4 (R4.1 – R4.12), §5 (without identity), §7; DT-2.

- [ ] Pure domain modules: `calendar` (ISO weeks, working days, quarters, spent buckets, timeline
      windows), `capacity` (work patterns, available time, availability, load and compare classes),
      `planning` (planned in a period, weekly planned hours, project days, expected by today),
      `tasks` (status, slipped, effective end, timeline text), `timesheet` (booking rules in
      minutes, week states and their texts), `numbering`, `logbook` (old/new core values →
      entries), `fields` (profile model, value validation per field type).
- [ ] Deployment profile: TOML format, `momato/profiles/default.toml` (the design's cards and
      fields, the other-work and time-off categories, the task template, `hidden_statuses`, the
      numbers), loader and validation at startup, `MOMATO_PROFILE`.
- [ ] Database: metadata naming convention, `UTCDateTime`, Unicode and Numeric types with MS SQL
      variants; the models of §5 (the `users` table with its person columns; sign-in columns and
      identity tables come in M2); the hot-path indexes; SQLite foreign keys, WAL, busy timeout,
      `BEGIN IMMEDIATE` for write sessions; `app_locks`; `db/ids.py` (long id lists as integers in
      the SQL); Alembic environment and initial migration; `db/migrate.py`, `python -m momato db
      upgrade`, migration at startup.
- [ ] **Sample data that looks well used** (D-037): curated JSON (org tree, people, project names,
      plans, remarks) plus a seeded generator (dates, members, tasks and progress, planned days,
      time entries, logbook history):
  - TaskBoard's departments and people (STL › Quality, Process, Maintenance; R&D › Coatings; Anna
    Claes, Bram Peeters, Chloé Martens, Dries Wouters, Eva Janssens, Filip Maes) plus about eight
    more departments of a steel plant (for example hot rolling, cold rolling, coating lines, energy
    and utilities, safety and environment, logistics, IT and automation, central maintenance),
    some with sub-departments, about 30 sections in all, the top-level ones flagged as departments;
  - about 70 people with job titles, a few part-timers (Eva Janssens works four days) and a few
    availability overrides;
  - about 200 projects in every status (some Stopped, hidden by default), spread over 2024–2028,
    with 2 to 6 members, tasks from the template, planned days, Markdown remarks with replies and
    a few images, and a logbook history;
  - about 12 action plans owned by different departments, each mixing projects from several;
  - two years of time entries for everyone (project work, other work, vacation weeks), and Anna
    Claes's week 41 as in the design: four project lines planned at 14, 10, 8 and 4 h plus Other
    work at 4 h, Monday and Tuesday full (16 h).
  - `python -m momato seed [--sample [--demo-password …]]`, idempotent, dates shifted to today
    (D-027).
- [ ] Shared fixture tables: `week_states.json`, `booking.json`, `load_classes.json`,
      `compare_classes.json`, `task_status.json`, `buckets.json`, `formatting.json`.

**Acceptance gate**:
- Every fixture row passes in Python; `momato/domain` has 100 % branch coverage.
- Hypothesis properties: spent buckets partition a period's working days; the weekly planned hours
  of all weeks of a quarter add up to the planned days × 8; a year's quarter availabilities add up
  to the year's; after any sequence of + and −, no value is negative and no day exceeds the cap,
  and an accepted + followed by − restores the previous state; exactly one week state applies to
  any week; load classes are monotonic in the value; ISO week labels round-trip (including week 53).
- The database refuses: a second planned-days cell for the same project, person and quarter; a
  time entry whose task belongs to another project; a time entry with both or neither of project
  and category; a duplicate *General* entry (filtered unique index); a duplicate project number.
- `alembic check` finds models and migrations in sync; upgrading an empty database works; the MS SQL
  DDL of every table compiles offline with NVARCHAR text, `DATETIME2`, integer minutes, Numeric
  days, filtered indexes and no forbidden cascades; the 2,100-parameter guard is active for all tests.
- Seeding twice changes nothing; the sample loads completely and matches its own source: the counts
  per department, status and person computed in the test from the JSON and the generator's output
  equal the database's; it has at least 10 departments, 60 people, 180 projects (some Stopped) and
  10 action plans; Anna Claes's week 41 has the design's lines and hours.
- A broken profile (unknown type, duplicate key, choice field without choices, category without a
  kind) stops the loader with a message naming the problem.

### M2 · Identity and access control

Delivers AUTH-1, AUTH-2, AUTH-4, AUTH-5 (server), REQUIREMENTS §6.

- [ ] Port TaskBoard's identity layer (D-004) with its tests, merged into the `users` table
      (person = user, D-012): system accounts `admin` and `anonymous`, sign-in columns, server-side
      sessions, CSRF, argon2 (`uv add argon2-cffi`), login throttling, forced password change,
      initial admin password, audit log, provisioning, the `IdentityProvider` protocol (providers
      in M12), the lockout guard. Models and migration.
- [ ] MoMaTo's permission catalog and built-in roles (Viewer, Project administrator, Hours viewer,
      Administrator); scopes global, org node and own department; default grants for signed-in
      people and anonymous (D-013); implicit coordinator and member rights (D-014); `AccessPolicy`
      with `can`, the visible-projects filter and the visible-time people filter. Seeded at start.
- [ ] Endpoints: login, logout, me, change password. `docs/AUTH.md`.

**Acceptance gate**: a policy matrix test (Viewer / Project administrator on a department /
Project administrator globally / Hours viewer / Administrator / coordinator / member / anonymous /
suspended × every permission × a node in scope, its ancestor, sibling and child); an
own-department matrix (flag on the person's node, on an ancestor, none; the person moves; the flag
moves); with default grants a fresh person sees every project and the time of their department
only; anonymous gets 401 on every data endpoint; after removing the default Viewer grant projects
disappear; system accounts never appear as people; a state-changing request without the CSRF
header gets 403; the sixth failed login gets 429; a suspended person's session is refused at the
next request; removing the last administrator is refused.

### M3 · Projects API

Delivers the server side of SH-6, SH-12, PL-1 – PL-8, PP-1 – PP-3, PP-6, OV-4, PG-4 – PG-6,
PD-3 – PD-5, LB-1, DT-1 – DT-3, AP-1, AP-7, AP-8, ADM-7, SH-11.

- [ ] `GET /api/bootstrap`: me (person, permissions), today, org tree, people, statuses,
      priorities, plans, the profile (cards, fields, choices, categories, hidden statuses); never
      projects.
- [ ] Projects list: filters (`node`, `status`, `q`, `name`, `coordinator`), hidden statuses left
      out unless asked for, order by number descending, **keyset pages of 50** (`after=<number>`),
      the total; a counts endpoint (per status, and per org node rolled up the tree, for the same
      filters); the neighbours and position of a project within a filtered list.
- [ ] Search endpoints for pickers: projects (number, name; optionally bookable only) and people.
- [ ] Projects: get by number, create (number assigned, optional task template), update core and
      detail fields (version, 409), members add/remove, plan link/unlink, delete.
- [ ] Logbook entries written by the services for the core fields; `GET /api/projects/{n}/log?filter=`.
- [ ] Tasks: list, create, update, move, delete. Planned days: the person × quarter grid of a
      project (planned and logged), set one cell.
- [ ] Action plans: list, create, update, delete; plan overview (groups and aggregates) and feed.
- [ ] Domain errors mapped to 404 / 409 / 422 in one place; OpenAPI at `/api/docs`.

**Acceptance gate**: API tests for every endpoint with its 401 / 403 / 404 (an invisible project is
404) / 409 / 422 cases. Paging: following `after` from the first page visits every matching project
exactly once, in order, also when projects are created between page loads; the total and every
count equal those computed in the test from the sample; without a status filter no Stopped project
appears, with `status=stopped` only those; neighbours and position match the test's own ordering;
the bootstrap holds no project; the number of SQL statements of a list page, a counts call and a
search does not depend on the number of projects (statement counter, 200 vs 2,000 projects). A
parametrized test changes each core field once and finds exactly one logbook entry with the right
old and new value, and changing a detail field writes none. For a sample project the planned,
logged and expected totals equal values computed in the test; a coordinator without any role can
edit their project and no other; a Project administrator on one department edits its projects and
not another department's; deleting a task moves its hours to *General*; deleting a project with
booked time is refused; a plan overview groups by top-level department with the owner first and
leaves out projects the caller can't see.

### M4 · Frontend shell, design system, Projects list

Delivers SH-1 – SH-12, PL-1 – PL-8, APP-1 – APP-5 (the celebration switch comes in M7), the login
dialog of AUTH-1.

- [ ] Vendored Preact, hooks and htm; fonts Bricolage Grotesque, Figtree, IBM Plex Sans with
      their licences; `static/vendor/README.md` (versions, sources).
- [ ] `css/tokens.css`: the design's lightness maps (light / dark), chroma multiplier, hues, radius
      scale and fonts as custom properties for `[data-mode] × [data-look]` (`playful`, `boring`);
      components never hard-code colours. `theme-boot.js` applies the stored appearance before the
      first paint.
- [ ] Shell: tree pane (full and rail) with server counts, main menu (full and rail), top bar
      (server search, Ctrl K, date), breadcrumb title with child menu, Appearance popover, login
      dialog, toasts, router with base path, API client with CSRF header, narrow-screen rails.
- [ ] Projects list with paging while scrolling and "Load more"; the New project dialog with
      server-side pickers.
- [ ] Pure modules with tests: `lib/format.js`, `lib/tree.js` (branches, breadcrumb),
      `lib/timeline.js` (positions in a window), `lib/routes.js`, `lib/appearance.js`,
      `lib/status.js`, `lib/paging.js` (merging pages, resetting on filter changes).

**Acceptance gate**: JS unit tests pass the shared formatting and window fixtures, and paging merges
pages without duplicates and resets on a filter change; e2e: the app loads without contacting
another origin and without console errors; the first 50 rows show, scrolling to the end loads the
next 50, and "Load more" works from the keyboard; the header count and the tree counts equal the
API's; Stopped projects are hidden until their chip is selected; selecting a department filters the
rows and the counts; the Project and Coordinator header filters and the top search narrow the list
(and the search switches to Projects); Ctrl K focuses the search; mode, style and collapse states
survive a reload, and an OS dark preference is followed until a mode is chosen; computed-style spot
checks (tree 236 / 48 px, menu 228 / 64 px, card radius 20 px Playful and 6 px Boring, display font
per style); creating a project opens it with the next number; a viewer sees no "+ New project"; at
390 px the page has no horizontal scroll outside the table card; axe finds nothing on Projects and
its popovers in all four appearances.

### M5 · Project page: Overview, Remarks, Logbook, All details

Delivers PP-1 – PP-7, OV-1, OV-3, OV-4, RM-1 – RM-5, LB-2 – LB-4, DT-1 – DT-3 (UI).

- [ ] Frame: top line with ‹ › through the list, badges, status menu, plan checklist, inline title,
      tabs in the URL, read-only mode, the 409 message.
- [ ] Overview (goal, latest remark, coordinator / people / dates / department / priority card),
      Logbook, All details with an editor per field type.
- [ ] Remarks: port TaskBoard's conversation (`uv add markdown-it-py nh3`): server-side Markdown and
      sanitizing, posts and revisions, image uploads as drafts with cleanup, attachment access by
      project visibility, composer with Write / Preview and toolbar, paste and drop, lightbox; plus
      replies, the template chip, `#number` links and `@name` highlighting.
- [ ] Pure modules with tests: `lib/logbook.js` (filter groups, hues), `lib/fields.js` (display
      and parsing per field type).

**Acceptance gate**: TaskBoard's conversation tests, ported: sanitizer tests with XSS vectors,
images only from this app, upload types and size limits checked by bytes (SVG refused), drafts
cleaned up after a day, attachments refused (404) to users who can't view the project, revisions
kept on edit, authors only edit their own posts; JS tests (every field type formats and parses
back); e2e: changing the status updates the pill and adds "You changed status" to the logbook (count
+ 1); renaming commits on Enter and blur, Esc cancels, an empty title is ignored; toggling an action
plan adds its pill and a logbook entry; ‹ › show "3 of N", follow the filtered list and keep the
tab; posting a remark with the template chip and a pasted image shows the rendered list and the
image, which opens in the lightbox; replying with Enter, Esc cancelling; editing shows "edited" and
the earlier version; `#4102` links to that project; every detail field type is edited and still
there after a reload; a viewer sees no editing affordances; two browsers editing the same project:
the second gets "Someone else changed this project"; axe on every tab in all four appearances.

### M6 · Project page: Planning, People & days

Delivers PG-1 – PG-6, PD-1 – PD-5, OV-2, OV-5.

- [ ] Gantt: quarter axis, today pill and line, planned bars with progress, revised-end extension,
      milestones, colours; the task dialog (add, edit, move, delete).
- [ ] People & days grid (cells, bars, upcoming, totals, "Also booked"), cell editing, adding and
      removing people.
- [ ] Overview "Where we are" and the Days card on real data.
- [ ] Pure modules with tests: `lib/gantt.js` (axis, positions, bar geometry), `lib/days.js`.

**Acceptance gate**: JS geometry tests against hand-computed cases (a project across a year
boundary, a task beyond the project end, today outside the range, a slipped milestone);
`task_status.json` passes in JS; e2e: a new task at 100 % turns Done (green) and "Where we are" says
Done; a revised end draws the dashed extension and "slipped"; tasks reorder; deleting a task with
hours asks first; 12.5 days in a cell update the row total and the Days card and survive a reload;
"+ Add person" adds a row and a chip; removing them asks first and their planned days are gone; axe.

### M7 · My timesheet

Delivers TS-1 – TS-15, the week card of SH-2, the celebration switch of APP-1.

- [ ] API: `GET /api/timesheet/{week}` (lines, tasks, planned hours, minutes per task and day, day
      targets, state), `PUT /api/timesheet/{week}/cells` (absolute minutes), `POST …/submit`; the
      current week's summary in the bootstrap; the rules of R4.8 enforced.
- [ ] Desktop: header, week navigation, summary card, fill-up cards with their animation, task
      picker, − and +1 h, the Other work and Time off cards, "+ Add project".
- [ ] Phone width: one column, wrapping summary (TS-12); the week card in the menu and its rail
      version; the celebration and its switch.
- [ ] Pure modules with tests: `lib/timesheet.js` (booking rules and week states, mirroring the
      domain, independent of the layout) and the save queue (coalescing, rollback).

**Acceptance gate**: Python and JS pass the same `week_states.json` and `booking.json`; the API
refuses (422 / 403) over 10 h a day, negative values or values off the step, weekends, future weeks
and someone else's time; the same PUT twice gives one state; a change to a submitted week clears the
submission. E2E as Anna Claes on the pinned Thursday: the week card reads "Two days done!" and "16
of 40 h logged. Next up: Wednesday."; + on a card fills it and updates the ring, the stacked bar,
the day button and the week card; + at 10 h does nothing; − falls back to another task with time;
emptying Monday turns the card amber with "Monday still open", and 8 h of Vacation on Monday makes
it full again; a full week shows "Full week done!"; Submit shows the celebration with 70 confetti
pieces, "Back to work" closes it and the button reads "Submitted ✓"; with reduced motion there is
no confetti, with the switch off no modal; at 390 × 844 the cards stack in one column and + and
Submit work; ten quick + clicks end in the right total after a reload; a refused save rolls back
with a toast; axe in all four appearances.

### M8 · People planning

Delivers PPL-1 – PPL-7, the people counts of SH-3.

- [ ] API `GET /api/people-planning?node=&mode=&period=`: rows, buckets, cells (value, capacity or
      planned, class), the hidden-people count; `GET …/people-planning/{person}` for the drill-down
      lines (member projects, non-member bookings, other work, time off, other projects).
      Aggregation in SQL (`GROUP BY`), bucket boundaries computed in Python.
- [ ] UI: header with mode and period switches, range and legend; table with the person filter,
      rows expanding with lines loaded on demand, colours, totals; drill-down links to People & days.
- [ ] Pure module with tests: `lib/planning.js` (cell presentation from the classes).

**Acceptance gate**: API tests: the time-privacy matrix (own time always visible; a colleague
through the default department grant; a department head with a global Hours viewer role; a viewer
outside the branch sees Planned but not Spent or Compare, and the hidden count is right); Spent
totals equal the sum of the time entries computed in the test, without time off; available time
subtracts time off; Compare counts member projects only; for the pinned date the buckets are
exactly "Week 40 · 28 Sep – 2 Oct 2026", weeks 37–40, and Oct ’25 – Sep ’26; Eva Janssens's
capacity follows her four-day pattern and an availability override changes the Planned free days;
the number of SQL statements does not depend on the number of people. E2E: modes and periods switch
(in the URL, kept after a reload); expanding Anna Claes and opening a project from her lines lands
on People & days; the person filter and the tree branch filter the rows; axe.

### M9 · Action plans

Delivers AP-1 – AP-8 (UI), the plan counts of SH-3.

- [ ] UI: plan tabs, meta line, description, plan dialog (new, edit, delete), totals card,
      timeline table grouped by top-level department with collapsible groups, selection in the URL,
      summary card and feed, "+ Add project" (server-side search).
- [ ] Pure module with tests: `lib/plans.js` (grouping with the owner first, aggregate spans).

**Acceptance gate**: JS tests of grouping and aggregates on sample rows; e2e: selecting a
department shows only the plans it owns; a branch without plans shows "No action plans owned by
{branch}"; selecting a project shows its summary and "Latest on this project"; a feed item opens its
project on Remarks or Logbook; a group collapses; a new plan gets a project from another department,
which appears under that department and in that project's logbook; without `plan.manage` there is
no "+ New plan"; projects the viewer can't see are absent from rows, totals and feed; axe.

### M10 · Administration and profile

Delivers ADM-1 – ADM-8, AUTH-4, AUTH-5 (UI).

- [ ] Org tree editor (add, rename, move, reorder, department flag, delete when unused).
- [ ] People: one page for a person's data (`org.manage`: name, job title, org node, work pattern,
      hue, availability per year, deactivate) and sign-in (`users.manage`: password, SSO
      preparation, suspend); roles and assignments (including the own-department scope and the
      default grants); audit log viewer.
- [ ] Profile page: own data and availability (read only), change password.

**Acceptance gate**: API tests for every administration endpoint (403 without the right permission,
no cycles in the tree, deleting a node in use refused, the lockout guard); e2e: flagging a node as a
department lets its people see each other's Spent time through the default grant; suspending a
person ends their open session; changing a work pattern changes timesheet targets and planning
capacity; an availability override shows on People planning; a deactivated person leaves the
pickers but keeps their history; axe on every administration page.

### M11 · Export (proof of concept) and API tokens

Delivers EXP-1 – EXP-4, TOK-1 – TOK-4.

- [ ] `uv add xlsxwriter`, `uv add --dev openpyxl` (to read exports in tests); streamed CSV and XLSX
      of the project list (Projects) and of time entries (People planning).
- [ ] API tokens, ported from TaskBoard (its D-097): model and migration, Profile UI, Bearer
      principal, scope narrowing, "via" marks, `GET /api/agent-guide`.

**Acceptance gate**: each export holds the same rows and numbers as its screen for the sample; CSV
starts with a BOM and round-trips through Python's `csv`; XLSX cells are typed (numbers, dates) with
a frozen header; a person without `hours.view` exports nobody else's time; a read-only token gets
403 on writes; a write token cannot reach administration; expired and revoked tokens get 401; a bad
token with a valid cookie gets 401; Bearer requests need no CSRF header; the logbook, remarks and
time entries show "via"; the agent guide lists every endpoint of the OpenAPI document; e2e: a token
is shown once, works, and stops working after revoking.

### M12 · Single sign-on

Delivers AUTH-3.

- [ ] `uv add "pyjwt[crypto]" pyspnego`; port TaskBoard's OIDC provider (Entra ID), Windows sign-in
      (Negotiate), trusted header, forwarded-header handling, matching prepared people, group
      mappings with their administration page, `serve` TLS options; AUTH.md sections.

**Acceptance gate**: TaskBoard's SSO tests, ported, pass against the in-process fake IdP and fake
Negotiate: PKCE, signed tokens, key rotation, replay, open redirects, unknown people per
configuration, suspended people refused, group mappings add rights; without configuration no SSO
route exists; an e2e sign-in round trip through the fake IdP.

### M13 · Hardening and release

Delivers REQUIREMENTS §8 and closes the traceability.

- [ ] Strict CSP (the import map allowed by its hash), security headers, compression.
- [ ] Accessibility pass: a keyboard path for every interaction; one consolidated axe suite over
      every screen, dialog and popover in the four appearances.
- [ ] Scale data generator (5,000 projects, 500 people, two years of time); scale tests for the
      budgets of §8.5 (API and browser).
- [ ] MS SQL: the API and integration suites against `MOMATO_TEST_DATABASE_URL` (needs a SQL Server
      database, like TaskBoard's M10).
- [ ] Visual regression baselines (`-m visual`, `uv add --dev pillow`): one screenshot per screen and
      appearance, compared with a tolerance, updated deliberately.
- [ ] `docs/OPERATIONS.md`: Windows server (service, IIS or Windows sign-in, MS SQL), Linux demo
      (systemd, Caddy or nginx), upgrades, the manual checklist.

**Acceptance gate**: the full suite passes on SQLite, and on MS SQL once a database is available;
`trace.py --strict` finds a test for every requirement and rule; axe reports no violations; no
console errors under the CSP; the scale budgets are met; the coverage gates hold.

---

## Plan evaluation

**Ordering.** Rules and persistence come first (M1) because every screen shows numbers derived
from them. Access control (M2) comes before the API (M3), as in TaskBoard: retrofitting
authorization into existing endpoints is where permission bugs come from, and time privacy is a
requirement, not a filter added later. From M4 on, each milestone is a screen delivered end to end
and browser-tested. The cost is that nothing is visible in a browser before M4; `/api/docs` gives an
interactive surface from M3. SSO comes late (M12): nothing depends on it, local accounts carry
development and the demo, and M2 already has the provider protocol.

**Risks and mitigations**

1. *Porting TaskBoard's identity code* to person = user, org-tree scopes, the own-department scope,
   default grants and implicit project rights. Its tests are ported with it, and the policy matrix
   test is written before the services that rely on it. Merging person and user removes TaskBoard's
   linking code rather than adding any.
2. *Scale* (D-028): thousands of projects and hundreds of thousands of time entries. Paged lists
   with keyset paging, counts and sums in SQL, hot-path indexes, a statement-count test from M3 on,
   and the measured budgets of M13 on a data set ten times the sample.
3. *MS SQL portability*: a *General* entry has no task, so uniqueness uses filtered unique indexes;
   time is integer minutes and days `Numeric`; date arithmetic stays in Python (bucket bounds are
   parameters); the 2,100-parameter guard runs in every test. There is no SQL Server here: the DDL
   is compiled offline and the suites are ready for a database.
4. *Design fidelity* across four appearance combinations: the tokens are generated from the design's
   own maps; computed-style spot checks and per-milestone screenshot reviews catch drift; contrast
   fixes are recorded as decisions.
5. *Optimistic timesheet writes under quick clicks*: absolute-value cells, coalescing and ordering
   tests make repeated or reordered requests harmless.
6. *Time leaking through aggregates or exports*: one policy filter feeds people planning, exports
   and the API, each with its own privacy matrix test.
7. *Animation in browser tests* (fill-ups, confetti): reduced motion in tests, separate tests for
   the motion paths, waiting on states rather than time.
8. *Calendar edges* (ISO week 53, quarters and weeks across years): property-based tests.
9. *A hand-curated sample of 200 projects* is work: names and texts are curated once, everything
   numeric comes from the seeded generator, and tests derive their expectations from the same files.

**Assumptions** are listed in [`DECISIONS.md`](DECISIONS.md) as *Assumed*; say if any is wrong.
