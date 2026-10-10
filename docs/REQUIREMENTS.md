# MoMaTo: requirements

What MoMaTo must do, and the exact rules behind every number it shows. The design handoff
([`design_handoff_kite_pm_tool/`](../design_handoff_kite_pm_tool/README.md), high fidelity) is the
reference for look and behaviour; this file adds what a real, multi-user application needs and
pins down what the prototype fakes. Decisions and assumptions are in [`DECISIONS.md`](DECISIONS.md)
(`D-xxx`), the delivery plan is in [`PLAN.md`](PLAN.md).

Every requirement has an ID (`PL-3`), and every rule section of §4 too (`R4.8` is §4.8). Tests
name the IDs they prove (`[PL-3]` in a test's docstring or name), and `scripts/trace.py` lists
requirements without a test (PLAN.md, test strategy).

The design calls the product *Kite*; it is **MoMaTo** everywhere: UI wordmark, package `momato`,
settings `MOMATO_*` (D-001).

---

## 1. Purpose

MoMaTo is an internal project management tool for an organisation structured as a tree of any
depth (organisation → departments → sub-departments → sections). Projects hang under tree nodes.
It covers:

- browsing projects through the organisation tree, with filters;
- a project page: overview, gantt planning, planned days per person, remarks (conversations with
  images), a logbook of changes, and all secondary details;
- **My timesheet**: logging hours per project and task (and time off), compared live against
  planned hours, with a celebration on submit;
- **People planning**: planned days per person per quarter, and spent versus planned time;
- **Action plans**: plans owned by one department that group projects from any department;
- two appearance axes: Light / Dark × Playful / Boring;
- accounts, rights, single sign-on and administration (from TaskBoard), CSV/Excel export (a proof
  of concept) and API tokens for AI agents.

It must stay fast with **thousands of projects and hundreds of people** (D-028).

## 2. Users and terms

| Who | Uses MoMaTo to |
|---|---|
| Team member | book their hours and time off, follow their projects, post remarks |
| Project coordinator | keep a project's fields, planning and planned days current |
| Project administrator | maintain all projects of a department (or of all departments) |
| Department head | see planned load and spent time for their branch (or wider) |
| Action plan owner | follow the projects of a plan across departments |
| Administrator | manage the org tree, people, sign-in and rights |
| Agent or script | read and write through the API with a personal token |

| Term | Meaning |
|---|---|
| Org node, branch | A node of the organisation tree; a branch is a node and everything below it. |
| Department | An org node flagged *department* by an administrator. A person's department is the nearest flagged node on the path from their node up to the root (D-006). |
| Person | Someone in the organisation, and at the same time their account (D-012): a person may or may not be able to sign in. The built-in `admin` and `anonymous` are system accounts, not people. |
| Member | A person involved in a project ("people involved"). The coordinator is always a member. |
| Task | A row of a project's gantt planning (also called phase); hours are booked on tasks. |
| Planned days | Days planned for one person on one project in one calendar quarter. |
| Time entry | Minutes one person booked on one day on a project task (or *General*), or on a category. |
| Category | Time not spent on projects: *Other work* (default Meetings, Training, Admin) or *Time off* (default Vacation, Out of office). |
| Work pattern | A person's hours per weekday, Monday to Friday (default 8 each). |
| Availability | Days a person can be planned in a year (default 220 × capacity factor, adjustable; D-020). |
| Profile | The deployment profile: detail fields, categories and a few numbers fixed per deployment in the codebase (§7). |
| Today | The server's date (D-027). |

---

## 3. Functional requirements

### 3.1 Application shell (SH)

- **SH-1** Full-viewport layout per the design: organisation tree pane, main menu, main area with a
  top bar and a scrolling content area. Both panes collapse to rails; the tree pane is
  **collapsed by default**. Collapse states are remembered per browser.
- **SH-2** Main menu: logo (rotated square + "momato" wordmark), navigation in the order
  **Projects, Action plans, People planning, My timesheet** with the design's four stroke icons
  and per-item hues (285, 60, 235, 155), the week card (TS-15), a spacer and the user row. The
  collapsed rail shows icon buttons with tooltips, a mini week ring, five day bars, the avatar.
- **SH-3** Tree pane: "ORGANISATION" eyebrow, collapse button, a hint per view ("Filters the project
  list" / "Shows plans owned in this branch" / "Filters the people shown"), tree rows with chevron,
  name and a count per view: visible projects in the branch (without hidden statuses, PL-2) /
  action plans owned in the branch / active people in the branch. Project counts come from the
  server. Collapsed rail: expand button and the selected node's name written vertically. On views
  the tree doesn't apply to (project page, timesheet, administration) only the rail is shown;
  clicking it opens Projects with the tree expanded.
- **SH-4** The selected node is shared by Projects, People planning and Action plans and is part of
  the URL (`?node=`). Default: the root.
- **SH-5** Breadcrumb title (Projects, People planning, Action plans): eyebrow, ancestors as ghost
  buttons, current node as H1, and a ▾ button opening a menu of child nodes with the view's
  counts and a › for nodes with children.
- **SH-6** Top bar: a search field that searches projects on the server (name, number,
  coordinator, org node name) as the user types and switches to Projects; Ctrl K (⌘K on a Mac,
  shown accordingly in the chip) focuses it; today's date on the right ("Thursday 8 October 2026").
- **SH-7** User row: avatar, name, job title; opens the Appearance popover (APP-1), which also
  links to the Profile page and offers Log out (not for visitors signed in by a trusted proxy,
  as in TaskBoard).
- **SH-8** Routes (History API, working under a URL prefix `MOMATO_BASE_PATH`); the server answers
  every app route with the page, so links can be pasted and survive a login:

  | Route | Screen |
  |---|---|
  | `/` | redirects to `/projects` |
  | `/projects?node=&status=&q=&name=&coordinator=` | project list |
  | `/projects/{number}[/planning\|/people\|/remarks\|/logbook\|/details]` | project page and tab |
  | `/timesheet[/{yyyy}-W{ww}]` | my timesheet, current or given ISO week |
  | `/people?node=&mode=planned\|spent\|compare&period=week\|month\|year&person=` | people planning |
  | `/plans[/{id}]?node=&project={number}` | action plans |
  | `/profile`, `/admin/...` | profile, administration |
- **SH-9** Narrow screens (D-024): below 720 px both panes show as rails and wide tables scroll
  inside their card; nothing else is optimised for phones yet. The timesheet works at phone width
  (TS-12).
- **SH-10** Local interactions are optimistic: no loaders between views, changes show at once and
  roll back with an error toast when the server refuses them.
- **SH-11** Unknown or invisible objects show a friendly "not found or no access" page.
- **SH-12** No screen loads all projects (D-028): lists are paged on the server; pickers that choose
  a project or a person search on the server as the user types; the bootstrap carries the org tree,
  people and plans, never projects.

### 3.2 Projects list (PL)

- **PL-1** Header on one line: breadcrumb title (eyebrow "PROJECTS"), ▾ child menu, the number of
  projects matching the filters ("214 projects"), spacer, "+ New project" (shown with
  `project.edit` somewhere in the branch).
- **PL-2** Status chips in the fixed order Idea, Rejected idea, In preparation, In progress, On hold,
  Stopped, Finished, each with its dot and count; chips with count 0 are hidden; clicking selects
  one status, clicking it again clears it. **Without a selected status, the profile's hidden
  statuses (default: Stopped) are left out of the list and its counts**; their chips stay visible
  with their counts, and selecting one shows those projects (D-018). Counts follow the branch,
  search and column filters and come from the server.
- **PL-3** Table card with the design's columns: No. | Project | Coordinator | People | Status |
  Timeline. The Project and Coordinator headers are inline filter inputs (case-insensitive substring
  match, Unicode-aware, applied on the server).
- **PL-4** Row: `#4102`; name with org node name below; coordinator avatar and name; up to three
  other members' avatars; status pill; a timeline track over the window of D-029 with the project
  bar in its status colour, a today tick and dates "Nov ’25 – Mar ’27".
- **PL-5** Rows are links: a click opens the project page, Ctrl/middle click a new tab.
- **PL-6** Empty state: "No projects match. Try another branch or clear the search."
- **PL-7** Order: project number, highest first. The list loads 50 rows at a time (keyset paging on
  the number, so rows added meanwhile never repeat or vanish); the next page loads when the end of
  the list scrolls into view, or with a "Load more" button that also serves keyboard users. All
  filters are in the URL.
- **PL-8** "+ New project" dialog: name, org node (only branches where the user has
  `project.edit`; default the selected node), coordinator (default: me), start, end, status (default
  Idea), goal, and "Start with the standard phases" (the profile's task template, PG-6). The number
  is assigned by the server (D-017); the logbook records the creation; the new project opens.

### 3.3 Project page (PP)

- **PP-1** Top line: "← Projects" (back to the list as it was), the clickable org breadcrumb, and
  ‹ › buttons with "3 of 214" stepping through the list the user came from (the server gives the
  position and the neighbours for the same filters), else through all visible projects. The current
  tab is kept when stepping.
- **PP-2** Badges: dark number pill; status pill with ▾ opening the seven statuses (any transition
  allowed, D-018); one pill per linked action plan (rotated-square swatch); a dashed
  "+ Action plan" pill opening a checklist of the plans the user can see.
- **PP-3** Title H1, click to rename: Enter or blur commits, Esc cancels; an empty or unchanged
  title changes nothing.
- **PP-4** Tabs Overview, Planning, People & days, Remarks (count), Logbook (count), All details,
  with a 2.5 px accent underline; the tab is part of the URL.
- **PP-5** Without `project.edit` the page is read-only: no menus, no inline-edit affordances.
- **PP-6** Edits carry the project's version; a stale edit is refused (HTTP 409) and the page says
  "Someone else changed this project", then reloads it.
- **PP-7** Important metadata is always prominent: members, number, goal, status, coordinator.

#### Overview (OV)

- **OV-1** Auto-fit grid (`minmax(320px, 1fr)`). Goal card: the goal at 17 px / 1.55, editable in
  place (plain text, line breaks kept).
- **OV-2** "Where we are": one bar per task in task order with its status text
  ("45% · running", "Done", "Planned"), and "x% of the timeline behind us" / "Starts 3 Nov 2025" /
  "Ended 19 Dec 2025" (R4.6).
- **OV-3** Latest remark card (the rendered remark), clamped to 5 lines; clicking opens Remarks.
- **OV-4** Card with coordinator (42 px avatar, name, job title), people involved (chips), start,
  end, department (org node), priority (High / Medium / Low); each editable in place by editors.
  Adding or removing people is the same action as PD-4.
- **OV-5** Days card: "x of y planned days logged", a 12 px green bar and a dark "expected by today"
  tick (R4.4); "Per person →" opens People & days. "All details →" opens All details.

#### Planning (PG)

- **PG-1** Legend: Planned (light), Progress (solid), Revised end (red dashed stripes), Milestone
  (dark rotated square). Grid `270px | 1fr`; the time axis is in quarters covering the project
  and all its tasks; a "Today" pill and a vertical accent line mark today when it is in range.
- **PG-2** Task rows (min-height 58): name; "5 Jan – 20 Mar · Running · slipped"; the planned bar
  (16 px, light tint) with the progress fill; the revised-end dashed extension when slipped; a
  milestone diamond (3 px white ring) at the effective end of milestone tasks.
- **PG-3** Bar colours by derived status (R4.6): Done hue 155, Running 285, Planned 235.
- **PG-4** Editors add a task ("+ Add task") or click a row to edit it in a dialog: name, planned
  start and end, revised end (optional), milestone, progress 0–100 % (D-008); move up / down;
  delete. Deleting a task with booked hours moves those hours to *General* after confirmation (D-032).
- **PG-5** A task's end is not before its start; a revised end is after the planned end.
- **PG-6** The profile's task template (default: the design's six phases, spread over the project
  span by fixed fractions, two of them milestones) can create a new project's tasks.

#### People & days (PD)

- **PD-1** One row per member (coordinator first, tagged "Coordinator", others with their job
  title), one column per quarter of the project span, and a Total column.
- **PD-2** Cell: planned days ("12 d" or "–"), a 5 px bar of days logged against planned (red when
  over), and "x logged", or "upcoming" for a quarter that starts after today. Total: planned days
  and "x logged".
- **PD-3** Editors click a cell to set planned days (steps of 0.5 d, 0 to the quarter's workdays);
  Enter or blur saves, Esc cancels.
- **PD-4** "+ Add person" adds a member (a person picker searching on the server). Removing a member
  (here or from the Overview chips) also removes their planned days on the project, after
  confirmation; their booked hours stay and count as non-member bookings. The coordinator cannot be
  removed (change the coordinator first).
- **PD-5** People who booked hours on the project without being members are listed under
  "Also booked" with their logged days only.

#### Remarks (RM): TaskBoard's conversation (D-015)

- **RM-1** Composer (with `project.comment`): avatar and a Markdown editor on a tinted background
  with Write / Preview, a toolbar (bold, italic, list, code, link, image), the "Done / Next steps
  template" chip that inserts `Done:\n- \n\nNext steps:\n- `, and "Post remark" (also Ctrl+Enter).
  A draft survives background reloads.
- **RM-2** Images are attached by the toolbar button, by pasting or by dropping: PNG, JPEG, GIF or
  WebP up to 10 MB, recognised by their bytes (SVG and anything else refused). They are uploaded as
  drafts and belong to the remark that refers to them once posted; drafts nobody posted are removed
  after a day. Images are served only to users who may view the project, are deleted with their
  remark or project, and open full size in a lightbox (any click or Esc closes it).
- **RM-3** Remarks are rendered on the server: CommonMark with tables and strikethrough, single
  newlines as line breaks, raw HTML not interpreted, output sanitized; only this app's images;
  `@name` highlighted (no notifications); `#4102` links to that project. Remark cards, newest first:
  avatar, name, relative date (R4.10), the rendered text. Max width 820 px.
- **RM-4** Replies, one level, oldest first, in tinted bubbles. "Reply" opens an inline input
  (Markdown text, no images): Enter posts, Shift+Enter starts a new line, Esc cancels.
- **RM-5** Authors edit and delete their own remarks and replies; an edited one shows "edited" and
  keeps its earlier versions, which can be viewed; a deleted remark with replies stays as "Remark
  deleted". Users with `users.manage` may delete (not edit) any remark. At most 20,000 characters.

#### Logbook (LB)

- **LB-1** The server writes an entry in the same transaction as every change of a core project
  field: created, title, status, start date, end date, coordinator, people (one entry per person
  added or removed), action plans (added to / removed from), goal, priority, org node (D-016). An
  entry holds when, who, the field, the old and new value as shown to users, and the API token if
  one was used ("via …"). Detail fields are not logged for now.
- **LB-2** Filter chips: Everything, Title, Status, Dates (start, end), People (people,
  coordinator), Action plans. The other fields appear under Everything.
- **LB-3** Timeline list, newest first: date column, coloured ring dot, "**Name** changed
  **field**" ("You" for the viewer), and the old value (struck through, muted) → new value chips,
  tinted per field: Title 285, Status 155, dates 60, Coordinator 235, People 330, Action plans 20,
  Created 90, others 285. Long values are truncated in the chip and shown in full on expand.
- **LB-4** The logbook is read-only.

#### All details (DT)

- **DT-1** An auto-fit grid of cards, each a list of label/value rows (150 px labels, hover tint).
  Cards and fields come from the profile (§7); the default profile is the design's:
  - *Identification*: project number, ERP order, original project, activity type;
  - *Organisation*: department, sponsor, budget owner, steering committee;
  - *Classification*: priority, strategic axis, process, programme, tags, ease of execution;
  - *Involvement*: operations & maintenance, procurement, engineering (yes/no), planning phase.
- **DT-2** A profile field is either a core project field (number, department, priority) or a
  detail field of one of these types: text, long text, number, date, choice, tags, person,
  project (a reference by number, chosen with a server-side picker), yes/no.
- **DT-3** Editors edit each value in place with an input fitting its type; the server validates
  values against the profile (422 otherwise). Detail changes are not logged for now (D-016).

### 3.4 My timesheet (TS)

- **TS-1** `/timesheet` shows the current ISO week; ‹ › go to other weeks, up to the current one.
  Time can be booked on any working day of the current and past weeks (D-022).
- **TS-2** Header "Week 41 · 5 – 9 October 2026" and a headline that follows the week's state
  (R4.9): "Two days done, 3 to go", "Let's catch up on Monday", "Your week is full. Ready to
  submit?", "Week submitted".
- **TS-3** Summary card: a 96 px ring of hours / weekly target (accent, green at the target); a
  12 px stacked bar of hours per line in the line's colour; five day buttons (auto-fit, min 104 px)
  with day name and number, a tag (✓ / Today / Next / Open), a 6 px fill bar and "x / 8 h" (the
  day's target); the selected day has an accent border and tinted background (default: today in
  the current week, Monday in a past week); "Submit week" (accent; green "Submitted ✓" after).
- **TS-4** Lines: one per project with planned hours for this person this week, one per project
  with time booked this week, then "Other work" and "Time off"; projects by planned hours, highest
  first, then unplanned ones; colours cycle through hues 285, 155, 235, 60, 330.
- **TS-5** Fill-up cards (grid `repeat(auto-fill, minmax(172px, 196px))`, gap 14, min-height 340,
  radius 24) whose background fills from the bottom with the line's tint as logged hours approach
  planned hours (height animated 0.45 s, `cubic-bezier(.3,1.5,.5,1)`), with a ✓ badge at the planned
  hours. Top to bottom: number · status; the project title as a link to its page (underline in the
  project colour at 45 %, darker on hover); the note ("7 h to go", "Right on plan", "2 h over plan",
  "14 h planned" before any booking, "Not planned" for unplanned lines); the task picker; the
  selected day's hours (44 px); "x of y h this week"; a 44 px round − and a "+1 h" pill (pressed:
  scale 0.94); "goes to {task}". The Time off card has no plan: no fill-up, its note is "x h this
  week".
- **TS-6** Task picker: the project's Running tasks, then its next Planned task, then *General*,
  each with its hours this week; tasks with hours this week are always listed. For Other work and
  Time off the choices are the profile's categories of that kind. The selected task gets a white
  background and a ring in the line colour, and is remembered per line per browser.
- **TS-7** + and − follow the booking rules of R4.8. Time off fills the day like work (R4.9).
- **TS-8** "+ Add project" offers, through a server-side search, the projects the user can see that
  are In preparation or In progress; such a line counts as unplanned and stays as long as it has
  time booked that week.
- **TS-9** Every change is saved at once, optimistically, as the new absolute number of minutes in
  that cell (person, day, line, task), so repeated or reordered requests cannot double-count; quick
  clicks are coalesced; a refused save rolls back.
- **TS-10** "Submit week" marks the week submitted (D-007). Changing any time of a submitted week
  reopens it; the week card, headline and button follow.
- **TS-11** Celebration on submit: a blurred dark backdrop with 70 confetti pieces falling 1.8–3.4 s
  with random drift and rotation and a modal popping in (0.5 s overshoot) with the big ring and
  hours, "Week 41 is in", "40 hours logged. 3 of 5 lines reached their planned hours." (lines with
  planned hours), one chip per line "x/y", and "Back to work". Off when the user disabled it
  (APP-1); with reduced motion the modal shows without confetti or animation.
- **TS-12** At phone width (below 600 px) the timesheet stays usable: the summary card wraps, the
  cards stack in one column, the day buttons, + and − and Submit work. The design's dedicated phone
  variant is for later (D-024); the timesheet's state and rules live in layout-free modules
  (`lib/timesheet.js`) so that variant can be added as another view.
- **TS-13** People book only their own time. System accounts have no timesheet and no week card.
- **TS-14** All timesheet numbers use tabular numerals.
- **TS-15** Week card (sidebar, current week; R4.9): eyebrow "WEEK 41" with "x/40 h"; a title by
  state ("Two days done!", "Fresh week, let's go", "Monday and Tuesday still open" on a warm amber
  card with "Catch up →", "Full week done!" with "Submit week →", "Week 41 submitted ✓"); five day
  boxes M T W T F (full: solid green with white text; open: amber; partly filled: a green fill to
  the day's percentage; today: 2 px accent border; future: dashed border); a sub line ("16 of 40 h
  logged. Next up: Wednesday."). Clicking it opens the timesheet.

### 3.5 People planning (PPL)

- **PPL-1** Header: breadcrumb title (eyebrow "PEOPLE PLANNING"), mode switch Planned · Spent ·
  Compare, a period switch Past week · Past month · Past year when the mode isn't Planned, the range
  label ("Quarters 2026 – 2027 · days", "Week 40 · 28 Sep – 2 Oct 2026 · hours") and a legend.
  Mode and period are in the URL.
- **PPL-2** Table: Person (an inline filter input) | Total | buckets. Rows are the active people
  in the selected branch. Clicking a row expands that person's per-project lines, loaded from the
  server at that moment; a project line opens the project on People & days.
- **PPL-3** Planned: eight quarters (current and next year), the current quarter's header in
  accent; cells hold planned days coloured by load against the quarter's availability (R4.3, R4.5);
  Total is this year's days plus "x d free" or "x d over" against the year's availability.
- **PPL-4** Spent: buckets per period (R4.11); cells hold the time spent (hours for a week, days
  otherwise), coloured by load against available time (time off subtracted); the drill-down adds
  "Other work" and "Time off" lines.
- **PPL-5** Compare: each cell shows spent large and "of {planned}" small, coloured on track
  (within ±15 %, green), under (blue, hue 235), over or unplanned (red) (R4.5). Only time on the
  person's member projects counts; non-member bookings, other work and time off are their own
  drill-down lines. Total: "x% of plan".
- **PPL-6** Hours privacy (D-005): Spent and Compare show a person's numbers only to that person and
  to viewers holding `hours.view` on the person's org node. Others are left out, with a note
  "n people in this branch whose hours you can't see". Planned is shown to anyone who may view
  projects somewhere.
- **PPL-7** In drill-downs, projects the viewer can't see are summed into one "Other projects" line;
  totals always include them.

### 3.6 Action plans (AP)

- **AP-1** An action plan has a name, a description, an owning org node, a coordinator (a person),
  a colour (a hue from a fixed palette) and any number of projects from any department.
- **AP-2** The visible plans are those owned inside the selected branch; if there are none:
  "No action plans owned by {branch}".
- **AP-3** Header: breadcrumb title (eyebrow "ACTION PLANS"), "4 plans", "+ New plan" (with
  `plan.manage` in the branch); plan tabs (segmented, swatch, name, project count); the meta line
  "Owned by STL › Quality · coordinated by … · includes projects from 3 departments"; the plan name
  (H2, 26 px) and description. Plan managers edit or delete a plan from a menu.
- **AP-4** Totals card: "x of y planned days logged across n projects", a 12 px bar with an
  expected-by-today tick, and "Tick = expected by today".
- **AP-5** Timeline table (columns `250px | 1fr | 130px`), grouped by top-level department (the
  root's children), the owner's group first with an "Owner" badge; groups collapse. A group row has
  name, count, status dots, an aggregate span bar and an aggregate days meter; a project row has
  name, status pill, a bar on a monthly grid over the window of D-029 with the today line, and
  "lg / pl d" with a meter. Clicking a project row selects it (tint and a 3 px accent inset bar);
  clicking again clears it. The selection is in the URL.
- **AP-6** Right column: when a project is selected, a summary card (status, number, × close, name,
  coordinator and dates, goal, days meter, "Open project →"); and a feed card, "Recent across this
  plan" or "Latest on this project": remarks (a 3-line plain-text excerpt) and logbook changes (not
  creations), newest first, at most 8; an item opens its project on Remarks or Logbook.
- **AP-7** "+ Add project" on a plan (a server-side project search) and "+ Action plan" on a project
  both link a project to a plan (logged in the project's logbook); allowed with `project.edit` on
  the project or `plan.manage` on the plan's owner (D-031).
- **AP-8** Projects the viewer can't see are left out of the plan's rows, totals and feed.

### 3.7 Appearance (APP)

- **APP-1** The Appearance popover: Mode (Light / Dark), Style (Playful / Boring) with the
  explanation "Playful: soft colours, rounded shapes. Boring: muted palette, tighter corners, one
  plain typeface.", and "Celebrate submitted weeks" (on by default).
- **APP-2** The mode follows the operating system until chosen; the choices are remembered per
  browser and applied before the first paint (no flash).
- **APP-3** Tokens as in the design, with *Boring* taking the design's *Managerial* values (D-026):
  OKLCH colours built from lightness steps remapped in dark mode, a chroma multiplier (1 / 0.55),
  the brand hue (285 / 255) and warm hue (75 / 255), the radius scale (× 1 / × 0.3, pills 999 px /
  6 px), and fonts (Bricolage Grotesque + Figtree / IBM Plex Sans); Boring uses font weights about
  100 lighter. Status, load, person and line hues as in the design. Tabular numerals for every
  number.
- **APP-4** Every text/background pair meets WCAG 2.1 AA in all four combinations; where a design
  colour misses it, the token is adjusted and the change recorded in DECISIONS.md.
- **APP-5** Motion as in the design (hover .12–.15 s, bars .3–.4 s, fill .45 s, press scale .9–.96);
  everything non-essential is off under `prefers-reduced-motion`.

### 3.8 Accounts and rights (AUTH)

- **AUTH-1** Ported from TaskBoard (D-004), with person = user (D-012): built-in system accounts
  `admin` (break-glass) and `anonymous` (every visitor not signed in); people sign in with a local
  password (argon2) or SSO; server-side sessions; CSRF protection (SameSite cookies and a
  double-submit header); login throttling; a forced password change for passwords set by an
  administrator; the generated initial admin password printed once.
- **AUTH-2** Rights per §6: roles bundle permissions; people hold roles at a scope.
- **AUTH-3** Single sign-on, opt-in by configuration: Microsoft Entra ID (OpenID Connect with
  PKCE), Windows sign-in by the app itself (Negotiate: Kerberos or NTLM), a trusted reverse-proxy
  header; people prepared in advance (email or Windows login name) are matched at their first
  sign-in; unknown people rejected (or created without rights, by configuration); IdP group → role
  mappings. Without configuration no SSO route exists.
- **AUTH-4** Suspending a person's sign-in ends their sessions at their next request. At least one
  active administrator always remains.
- **AUTH-5** An audit log records sign-ins, account and rights changes.

### 3.9 Administration and profile (ADM)

The mockups don't cover these screens; they reuse the design's visual language with plain forms
and tables.

- **ADM-1** Org tree (`org.manage`): add, rename, move (no cycles), reorder, flag or unflag as
  department, delete when nothing refers to the node.
- **ADM-2** People (`org.manage`): create; edit name, job title, org node, work pattern (hours per
  weekday), colour hue; deactivate (never delete): a deactivated person cannot sign in, leaves
  pickers and planning rows, and keeps their history.
- **ADM-3** Sign-in (`users.manage`): set or reset a local password, prepare an SSO sign-in (email,
  Windows login name), suspend and reactivate.
- **ADM-4** Availability (`org.manage`): per person and year, the days available for planning,
  shown with the default it overrides (D-020).
- **ADM-5** Roles and assignments (`users.manage`): built-in roles (read-only) and custom roles;
  assignments per person at scope global, an org node, or "own department"; the default grants of
  signed-in users and of anonymous visitors (D-013).
- **ADM-6** Audit log viewer (`users.manage`).
- **ADM-7** Deleting a project (`project.delete`): only when no time is booked on it (D-018); its
  tasks, planned days, remarks and images, logbook and plan links go with it.
- **ADM-8** Profile page: name, job title, org node and availability (read only), change own
  password (local sign-in), API tokens (TOK-1).

### 3.10 Export, a proof of concept (EXP)

- **EXP-1** The project list as shown (branch, status, search and column filters): core fields and
  all profile detail fields.
- **EXP-2** Time entries for a date range and branch: date, ISO week, person, org node, project
  number and name, task, category, hours, week submitted.
- **EXP-3** Each export comes as CSV (UTF-8 with BOM, comma separator, ISO dates, decimal point) and
  as XLSX (one sheet, typed cells, frozen header row) (D-033), is streamed, and is reachable from
  the screen it mirrors (Projects; People planning for time entries) and from the API.
- **EXP-4** Exports contain exactly what the user may see on screen, `hours.view` included.

### 3.11 API tokens for agents (TOK)

- **TOK-1** Personal tokens created on the Profile page (`Authorization: Bearer mm_…`, only a hash
  stored), acting as their owner with the owner's current rights narrowed to the token's scope:
  *read only* (view permissions) or *read and write* (everything but `org.manage` and
  `users.manage`). Expiry chosen by the owner (7 / 30 / 90 / 365 days or never); tokens can be
  revoked. Ported from TaskBoard (its D-097).
- **TOK-2** A Bearer request is judged by its token alone (a bad token is 401, never a fallback to
  cookies or anonymous), so it needs no CSRF header. Tokens never manage tokens.
- **TOK-3** What a token writes is marked "via <token name>" (logbook, remarks, time entries).
- **TOK-4** `GET /api/agent-guide` returns a Markdown guide for agents, its endpoint list generated
  from the OpenAPI document.

---

## 4. Rules and calculations

These rules are pure functions in `momato/domain/` (Python) and, where the browser needs them,
mirrored in `momato/static/js/lib/`; both are tested against the same fixture tables in
`tests/fixtures/`.

### 4.1 Calendar

- Today is the server's date (`MOMATO_TODAY` pins it; tests use Thursday 8 October 2026, ISO
  week 41, the design's date).
- Weeks are ISO weeks (Monday to Sunday, numbered per ISO 8601). Working days are Monday to Friday;
  there is no holiday calendar: time off is booked (D-019).
- Quarters are calendar quarters, written `Q4/26`.

### 4.2 People's time

- Time is stored in whole minutes (D-038) and shown in hours (or days at 8 h per day, profile
  `hours_per_day`).
- A work pattern gives hours per weekday Monday to Friday (default 8, 8, 8, 8, 8). The **weekly
  target** is their sum, a **day target** is that weekday's hours, a **working day** is a weekday
  with hours > 0, and the **capacity factor** is weekly target / 40.
- **Available time** over a period = the sum of day targets over its working days, minus the time
  off booked in it.

### 4.3 Availability and planned days

- **Availability** of a year = the person's override for that year, else the profile's
  `available_days_per_year` (220) × capacity factor. A quarter's availability = the year's ×
  workdays(quarter) / workdays(year).
- Planned days are set per (project, person, quarter) in steps of 0.5 d, for members only.
- **Planned in a period** = Σ over quarters q overlapping it of planned(q) × wd(period ∩ q) / wd(q),
  where wd counts the person's working days.
- **Weekly planned hours** of a project line = planned in that week × 8, kept exact and shown in
  whole hours (D-021). Other work is planned at the profile's share of the weekly target (default
  10 %: 4 h of 40). Time off is not planned.

### 4.4 Project days

- Planned total = Σ planned days of the project (all members, all quarters).
- Logged = Σ time booked on the project (anyone) in days.
- Expected by today = Σ over quarters of planned(q) × (workdays of q up to today / workdays(q)),
  where a quarter after today counts 0 and a past one counts in full.
- Percentages (logged, expected) are of the planned total, clamped to 0–100; 0 when nothing is
  planned. The same applies to a person's row (PD), an action plan and its groups (AP).

### 4.5 Load and compare classes

| Load (value v against capacity c, r = v / c) | Class |
|---|---|
| v = 0 | empty |
| r < 0.40 | light (very light green) |
| 0.40 ≤ r < 0.85 | Comfortable (green) |
| 0.85 ≤ r ≤ 1.02 | Nearly full (amber) |
| r > 1.02 | Over capacity (red) |

| Compare (spent s against planned p) | Class |
|---|---|
| s = 0 and p = 0 | empty |
| p = 0, s > 0 | unplanned (red) |
| s / p > 1.15 | over (red) |
| s / p < 0.85 | under (blue) |
| otherwise | on track (green) |

### 4.6 Tasks and timelines

- A task's **status**: Done when progress is 100 %; Running when progress > 0 or its planned start
  is on or before today; Planned otherwise. **Slipped** when it has a revised end after its planned
  end. Its **effective end** is the revised end, else the planned end.
- Project timeline text: before the start "Starts {date}", after the end "Ended {date}", otherwise
  "x% of the timeline behind us" with x = (today − start) / (end − start), rounded.
- "Where we are" status text: Running tasks "{progress}% · running", others their status.

### 4.7 Project numbers

New projects get the highest existing number + 1, or the profile's first number when there are
none. Numbers are unique, never change, and are the project's permalink (D-017).

### 4.8 Timesheet booking

- A time entry is (person, day, project and task-or-General | category, minutes ≥ 0).
- + adds the profile step (`timesheet_step_minutes`, default 60) to the selected task of that line
  on the selected day, unless the day's total over all lines (time off included) would exceed the
  day cap (`day_cap_minutes`, default 600): then nothing happens.
- − removes one step from the selected task; if that task has no time that day, from the first
  task of the same line (picker order) that has; never below 0; if the line has no time that day,
  nothing happens.
- The server enforces non-negative values, multiples of the step, the day cap, working days only,
  own time only, and the week limit (no future weeks) (422 otherwise).

### 4.9 Week states

For a week, let t be today's weekday index (Monday 0) in the current week, and 7 for a past week.
For each working day d, counting all booked time (time off included):

- **full**: time(d) ≥ target(d);
- **open**: d < t − 1 (before yesterday) and not full;
- day tag: ✓ if full; else "Today" if d = t; "Next" if d > t; "Open" if open; else none.

| State (first that applies) | Week card title | Card CTA | Timesheet headline |
|---|---|---|---|
| submitted | "Week 41 submitted ✓" | "View week →" | "Week submitted" |
| some day open | "{open days} still open" (amber card) | "Catch up →" | "Let's catch up on {open days}" |
| all working days full | "Full week done!" | "Submit week →" | "Your week is full. Ready to submit?" |
| n ≥ 1 full days | "{N} days done!" ("One day", "Two days", …) | "Keep going →" | "{N} days done, {rest} to go" |
| none full | "Fresh week, let's go" | "Keep going →" | "Let's fill in your week" |

"{open days}" is one name ("Monday"), two joined by "and", or "3 days". Sub lines: "Catching up
takes a minute. 16 of 40 h logged so far." (open), "All five days are in. One tap to submit." (full),
"16 of 40 h logged. Next up: Wednesday." (otherwise; the first working day not full), "40 hours
logged. Enjoy the weekend." (submitted).

### 4.10 Formatting

- Dates en-GB: "8 Oct 2026"; short "8 Oct"; months "Nov ’25"; top bar "Thursday 8 October 2026".
- Relative dates: "Today", "Yesterday", "n days ago" below 7 days, else the date.
- Days with at most one decimal ("12.5 d"); hours whole, or with up to two decimals when minutes
  make them uneven (sub-hour booking later).

### 4.11 Spent buckets

| Period | Buckets | Unit |
|---|---|---|
| Past week | Mon–Fri of the last full week (ended before today) | hours |
| Past month | the last 4 full weeks, one bucket per week ("Wk 37", Monday's date) | days |
| Past year | the last 12 full months ("Oct ’25" … "Sep ’26") | days |

Spent = time booked in the bucket on projects and other work (Spent mode) or on member projects
only (Compare); time off is never spent time. Planned in a bucket follows R4.3; available time
follows R4.2.

### 4.12 Timeline windows

The Projects list and Action plans draw timelines from 1 January of last year to 31 December of
next year (2025–2027 in the design) (D-029).

---

## 5. Data model

Names and splits are refined in M1 and M2; this is the intended shape. Every table follows the
portability rules of §8.

- `org_nodes(id, parent_id?, name, position, is_department)`: one root.
- `users(id, kind (person | system), name, job_title?, org_node_id?, hue, work_minutes_mon …
  work_minutes_fri, status (active | suspended | deactivated), username?, email?, password_hash?,
  must_change_password, created_at)`: people and system accounts in one table (D-012); username
  and email unique when present (filtered unique indexes).
- `availability(user_id, year, days)`: overrides of the default (D-020).
- `projects(id, number, name, org_node_id, status, coordinator_id, start_date, end_date, goal,
  priority, created_at, updated_at, version)`: unique `number`.
- `project_members(project_id, user_id)`.
- `project_details(project_id, field_key, value)`: unique per project and key; `value` is the
  JSON-encoded value, validated against the profile (D-034).
- `tasks(id, project_id, position, name, planned_start, planned_end, revised_end?, is_milestone,
  progress, version)`.
- `planned_days(project_id, user_id, quarter_start, days)`: unique per project, person and quarter.
- `time_entries(id, user_id, work_date, project_id?, task_id?, category_key?, minutes, updated_at,
  api_token_id?)`: exactly one of project or category; a task belongs to the same project
  (composite foreign key); one row per person, day, project, task (or General) and category
  (filtered unique indexes).
- `week_submissions(user_id, iso_year, iso_week, submitted_at)`.
- `posts(id, project_id, parent_id?, author_id, body_md, created_at, edited_at?, edited_by_id?,
  deleted_at?, api_token_id?)`, `post_revisions(post_id, rev, body_md, written_by_id, written_at)`,
  `attachments(id, project_id, post_id?, uploader_id, filename, content_type, size, storage_key,
  created_at)`: remarks, replies (one level) and their images (files under the data folder).
- `log_entries(id, project_id, at, actor_id, api_token_id?, field_key, from_value?, to_value?)`.
- `action_plans(id, name, description, owner_org_node_id, coordinator_id, hue, position, version)`
  and `action_plan_projects(plan_id, project_id)`.
- Identity (from TaskBoard): `external_identities`, `roles`, `role_permissions`,
  `role_assignments(user_id, role_id, scope_kind, org_node_id?)` with scope kinds global, node and
  own department, `default_grants` (for signed-in users and anonymous visitors), `sessions`,
  `login_attempts`, `audit_log`, `api_tokens`, `sso_requests`, `group_mappings`.
- System: `app_locks`.

Indexes support the hot paths: projects by (org node, status, number) and by number; time entries
by (user, work_date) and (project, work_date); planned days by (user, quarter).

## 6. Access control

Permissions are scoped to org-tree branches: a grant on a node covers its whole subtree.

| Permission | Scope | Viewer | Project administrator | Hours viewer | Administrator | Allows |
|---|---|:-:|:-:|:-:|:-:|---|
| `project.view` | branch of the project's node | ✔ | ✔ | | ✔ | see projects: all tabs, planned days, logged totals; their place in plans |
| `project.edit` | same | | ✔ | | ✔ | create projects there; edit fields, details, tasks, planned days, members, plan links |
| `project.comment` | same | | ✔ | | ✔ | post remarks, replies and images |
| `project.delete` | same | | | | ✔ | delete a project without booked time |
| `plan.manage` | branch of the plan's owner | | ✔ | | ✔ | create, edit and delete action plans |
| `hours.view` | branch of the person's node | | | ✔ | ✔ | see time booked by those people (Spent, Compare, drill-downs, exports) |
| `org.manage` | global | | | | ✔ | org tree, departments, people, work patterns, availability |
| `users.manage` | global | | | | ✔ | sign-in, roles, assignments, audit log, delete any remark |

Rules:

1. A scoped permission applies when it is held globally or on any node on the path from the
   object's node up to the root. A global permission counts only when assigned globally.
2. Scopes are global, an org node, or **own department**: resolved at each request to the
   department of the person (none when they have no department).
3. **Default grants** hold for every signed-in person, and the anonymous visitor's grants are a
   floor for everyone (TaskBoard D-025). Defaults: signed-in people get *Viewer* globally and
   *Hours viewer* on their own department; anonymous gets nothing, so MoMaTo requires a login
   (D-013). Administrators change both like any other assignment.
4. **Project administrator** is assigned on a department (all its projects and plans) or globally
   (all departments) (D-014).
5. Everyone sees their own time. A project's coordinator may view, edit and comment on it; its
   members may view and comment on it (D-014).
6. Lists only contain what the caller may see; counts only count it; an invisible project answers
   404, like a missing one.
7. Routers never decide access: one policy object answers `can(...)` and builds the query filters
   (visible projects, people whose time is visible); services call it.

## 7. Configuration and the deployment profile

Environment variables (or a `.env` file in the app folder), as in TaskBoard: `MOMATO_DATA_DIR`
(database file and uploaded images), `MOMATO_DATABASE_URL` (any SQLAlchemy URL; MS SQL via
`mssql+pyodbc://`), `MOMATO_ENVIRONMENT`, `MOMATO_HOST`, `MOMATO_PORT`, `MOMATO_BASE_PATH`,
`MOMATO_TRUSTED_PROXIES`, `MOMATO_COOKIE_SECURE`, `MOMATO_INITIAL_ADMIN_PASSWORD`,
`MOMATO_AUTO_MIGRATE`, `MOMATO_TODAY`, the SSO settings of TaskBoard renamed, and
**`MOMATO_PROFILE`** (default `default`).

The **deployment profile** (D-009) is a TOML file in `momato/profiles/`, chosen by name. It
cannot be changed from inside the app; developers add a profile to build a variant of the tool with
other detail fields. It is validated at startup (a broken profile stops the server with a clear
message) and holds:

- the detail cards, and per field: key, label, type (DT-2), choices for choice fields, and the card;
- the categories, each with a kind: *other work* (default Meetings, Training, Admin) or *time off*
  (default Vacation, Out of office);
- the task template (default: the design's six phases with their fractions and milestones);
- `hidden_statuses` (default `["stopped"]`, PL-2);
- numbers: `hours_per_day` 8, `day_cap_minutes` 600, `timesheet_step_minutes` 60,
  `available_days_per_year` 220, `other_work_share` 0.1, `first_project_number` 1000.

A field removed from a profile keeps its stored values (hidden, never deleted); choice values no
longer listed are shown as stored, marked as unknown.

## 8. Non-functional requirements

### 8.1 Stack and code organisation (as TaskBoard, D-002)

| Concern | Choice |
|---|---|
| Runtime | Python 3.14, managed with uv |
| Web | FastAPI on Uvicorn; OpenAPI UI at `/api/docs` |
| Persistence | SQLAlchemy 2 (sync, typed) + Alembic; SQLite by default, MS SQL ready (optional extra `mssql`: pyodbc) |
| Settings | pydantic-settings, `MOMATO_` prefix |
| Remarks | Markdown rendered on the server (markdown-it-py) and sanitized (nh3) |
| Frontend | static ES modules, no build step: Preact + hooks + htm, vendored, wired by an import map |
| Fonts | Bricolage Grotesque, Figtree, IBM Plex Sans as vendored woff2 (SIL OFL, D-035) |
| Export | XlsxWriter (XLSX), the standard library (CSV) |
| Tests | pytest (+ httpx2 TestClient, hypothesis, pytest-cov), Playwright for Python + axe, `node --test` |
| Quality | ruff (lint + format), pyright (strict on `momato/`), import-linter |

- **Dependencies** (D-003): runtime libraries in `[project.dependencies]` (`uv add`), every test and
  tooling package in the `dev` dependency group (`uv add --dev`), the MS SQL driver in the optional
  extra `mssql`. `uv sync --no-dev` installs a server without test tools.
- Flat layout: `app.py` (three lines) next to the `momato/` package. Layers
  `cli → web → api → services → schemas → identity → db → domain`, imports only rightwards; the domain
  is plain Python; routers never touch the database. Enforced by import-linter.
- Every source file starts with a one-line description; `docs/CODEMAP.md` is generated from them.

### 8.2 Portability and operations

- Code runs on Windows and Linux (`pathlib`, locations from settings).
- The schema and queries follow TaskBoard's MS SQL portability rules: Unicode text types,
  explicit lengths on indexed strings, no cascades on self-references or multiple cascade paths,
  case-insensitive uniqueness normalised in code, a constraint naming convention, filtered unique
  indexes for nullable unique columns, no CHECK constraints on enums, `NVARCHAR(max)` and
  `DATETIME2` variants, at most 2,100 parameters per statement (long id lists written into the SQL
  as integers), time as integer minutes and days as `Numeric` (never floats), date arithmetic in
  Python rather than in SQL.
- `python -m momato serve | db upgrade | seed [--sample] | create-admin`; migrations run at startup
  unless turned off.
- Deployments as TaskBoard: a corporate Windows server (service, IIS or Windows sign-in, SQLite or
  MS SQL) and a Linux demo server (systemd, Caddy/nginx, SQLite).

### 8.3 Security

- No external network resources at runtime: libraries and fonts are vendored.
- Strict Content Security Policy (no inline scripts except the import map, by hash; no inline
  styles), nosniff, no framing, same-origin policies; HSTS is the proxy's job.
- Names, details and other plain user text are rendered as text, never as HTML. Remark Markdown is
  rendered and sanitized on the server; images are checked by their bytes and served only to users
  who may view their project.
- Input validated by Pydantic schemas; lists, counts and exports filtered by the access policy.

### 8.4 Accessibility

- WCAG 2.1 AA. Everything works with the keyboard (tree, menus, popovers, tabs, inline editing,
  paged lists, timesheet + and −, task picker, gantt task dialog, composer); focus is visible.
- Colour is never the only cue: statuses and load classes have labels or numbers and legends.
- axe-core finds no violations on any screen, dialog and popover, in all four appearance
  combinations.

### 8.5 Scale and performance

Target size: thousands of projects and hundreds of people, not all at once (D-028). With the scale
data set (5,000 projects, 500 people, 2 years of time entries: about 750,000 rows) on SQLite on a
developer laptop:

- a project list page (50 rows), its status and tree counts each answer within 300 ms, and the list
  renders within 500 ms; the next page within 300 ms;
- project search and pickers answer within 200 ms;
- a project page's API calls answer within 300 ms each;
- people planning (any mode, root branch) answers within 1.5 s; a person's drill-down within 300 ms;
- a timesheet save answers within 150 ms;
- the bootstrap stays under 300 kB compressed.

Responses over 1 kB are compressed.

### 8.6 Browsers and language

Current Edge, Chrome, Firefox and Safari (ES modules, import maps, OKLCH). Automated browser tests
run in Chromium. English UI, en-GB formats, ISO weeks (D-036).

---

## 9. Out of scope (for now)

- Importing data from spreadsheets (the API with a token can load data), backups (SQLite file and
  MS SQL tools), more exports than the two of EXP (D-010, D-033).
- The timesheet's dedicated phone variant and phone layouts of the other screens (D-024).
- Logging changes of detail fields (D-016); adjustable timeline windows (D-029).
- Holiday calendars and leave planning (time off is booked afterwards); approval of timesheets;
  budgets and costs.
- Notifications and e-mail; live updates when others change data (a reload shows them).
- Changing detail fields, statuses or categories from inside the app.
- Dragging gantt bars; editing planned days by dragging.
- Languages other than English.
