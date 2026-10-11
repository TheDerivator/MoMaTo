// The Projects list: breadcrumb title, status chips, the paged table (PL-1..PL-8).
import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { Crumbs } from "../components/crumbs.js";
import { NewProjectDialog } from "../components/dialogs.js";
import { ProjectsExport } from "../components/exportmenu.js";
import { Avatar, StatusPill } from "../components/ui.js";
import { html } from "../html.js";
import { formatMonth, plural } from "../lib/format.js";
import { emptyList, filterKey, firstPage, nextPage, reset } from "../lib/paging.js";
import { buildUrl, filtersOf } from "../lib/routes.js";
import { chips, nextSelection, statusByKey } from "../lib/status.js";
import { barGeometry, position, timelineWindow } from "../lib/timeline.js";
import { Link, currentRoute, navigate } from "../router.js";

function listParams(route) {
  return {
    node: route.node,
    status: route.status,
    q: route.q,
    name: route.name,
    coordinator: route.coordinator,
  };
}

// ------------------------------------------------------------------ header

function StatusChips({ ctx, counts }) {
  const { boot, route } = ctx;
  const shown = chips(boot.statuses, counts.statuses ?? {}, route.status);
  return html`<div class="status-chips" role="group" aria-label="Filter by status">
    ${shown.map(
      (chip) => html`<button
        key=${chip.key}
        class=${`chip${chip.gray ? " chip--gray" : ""}`}
        style=${{ "--hue": chip.hue }}
        aria-pressed=${chip.selected ? "true" : "false"}
        onClick=${() => navigate(ctx.urlFor({ ...route, status: nextSelection(route.status, chip.key) }))}
      >
        <span class=${`dot${chip.gray ? " dot--gray" : ""}`} style=${{ "--hue": chip.hue }}></span>
        ${chip.label}<span class="chip__count">${chip.count}</span>
      </button>`,
    )}
  </div>`;
}

// ------------------------------------------------------------------ the table

function HeaderFilter({ value, placeholder, label, onCommit }) {
  const [text, setText] = useState(value);
  const timer = useRef(0);
  useEffect(() => setText(value), [value]);
  return html`<input
    class="header-filter"
    value=${text}
    placeholder=${placeholder}
    aria-label=${label}
    onInput=${(event) => {
      const next = event.target.value;
      setText(next);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => onCommit(next), 250);
    }}
  />`;
}

function Row({ project, ctx, window }) {
  const status = ctx.statuses.get(project.status);
  const bar = barGeometry(project.start_date, project.end_date, window);
  const today = position(ctx.boot.today, window);
  const dates = `${formatMonth(project.start_date)} – ${formatMonth(project.end_date)}`;
  return html`<${Link}
    class="table__row table__link"
    href=${buildUrl({ view: "project", number: project.number, tab: "overview", ...filtersOf(ctx.route) })}
    aria-label=${`#${project.number} ${project.name}`}
  >
    <span class="table__number">#${project.number}</span>
    <span class="table__project">
      <span class="table__name">${project.name}</span>
      <span class="table__sub">${project.org_node_name}</span>
    </span>
    <span class="table__person">
      <${Avatar} person=${project.coordinator} />
      <span>${project.coordinator.name}</span>
    </span>
    <span class="avatar-stack">
      ${project.members.map((m) => html`<${Avatar} key=${m.id} person=${m} ring=${true} />`)}
    </span>
    <span><${StatusPill} status=${status} /></span>
    <span class="timeline">
      <span class="timeline__track" style=${{ "--hue": status.hue }}>
        <span
          class=${`timeline__bar${status.gray ? " dot--gray" : ""}`}
          style=${{ left: `${bar.left}%`, width: `${bar.width}%`, "--hue": status.hue }}
        ></span>
        <span class="timeline__today" style=${{ left: `${today}%` }}></span>
      </span>
      <span class="timeline__dates">${dates}</span>
    </span>
  <//>`;
}

// ------------------------------------------------------------------ the view

export function ProjectsView({ ctx, counts }) {
  const { route, boot, me, toast } = ctx;
  const key = filterKey(route);
  const [list, setList] = useState(() => emptyList(key));
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const loading = useRef(false);
  const sentinel = useRef(null);
  const window_ = timelineWindow(boot.today);

  // New filters: start over, and load the first page.
  useEffect(() => {
    setList((current) => reset(current, key));
    setError("");
    loading.current = false;
    let cancelled = false;
    api("projects", { params: listParams(route) })
      .then((page) => !cancelled && setList((current) => firstPage(current, key, page)))
      .catch((failure) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [key]);

  const more = useCallback(async () => {
    if (loading.current || list.nextAfter === null || list.key !== key) return;
    loading.current = true;
    try {
      const page = await api("projects", { params: { ...listParams(route), after: list.nextAfter } });
      setList((current) => nextPage(current, key, page));
    } catch (failure) {
      toast(messageOf(failure), "error");
    } finally {
      loading.current = false;
    }
  }, [list.nextAfter, list.key, key]);

  // Load the next page when the end of the list scrolls into view (PL-7).
  useEffect(() => {
    const target = sentinel.current;
    if (!target || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) more();
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [more]);

  const canCreate = me.permissions["project.edit"].everywhere || me.permissions["project.edit"].node_ids.length > 0;
  // Header filters commit after a pause; two edited in quick succession must not undo each other.
  const setFilter = (field) => (value) =>
    navigate(ctx.urlFor({ ...currentRoute(), [field]: value }), { replace: true });

  return html`<div class="page">
    <div class="list-header">
      <${Crumbs}
        ctx=${ctx}
        eyebrow="Projects"
        nodeId=${route.node}
        nodeCounts=${counts.nodes}
        onGo=${(id) => navigate(ctx.urlFor({ ...route, node: id === ctx.tree.root.id ? null : id, status: null }))}
      />
      <span class="list-count" aria-live="polite">${plural(list.loaded ? list.total : (counts.total ?? 0), "project", "projects")}</span>
      <div class="list-header__spacer"></div>
      <${ProjectsExport} route=${route} />
      ${canCreate
        ? html`<button class="btn btn--dark" onClick=${() => setCreating(true)}>+ New project</button>`
        : null}
    </div>
    <${StatusChips} ctx=${ctx} counts=${counts} />
    <div class="table-card">
      <div class="table">
        <div class="table__row table__head">
          <span>No.</span>
          <${HeaderFilter} value=${route.name} placeholder="Project ⌕" label="Filter by project name" onCommit=${setFilter("name")} />
          <${HeaderFilter} value=${route.coordinator} placeholder="Coordinator ⌕" label="Filter by coordinator" onCommit=${setFilter("coordinator")} />
          <span>People</span>
          <span>Status</span>
          <span>Timeline</span>
        </div>
        ${list.items.map((p) => html`<${Row} key=${p.number} project=${p} ctx=${ctx} window=${window_} />`)}
        ${error ? html`<div class="empty" role="alert">${error}</div>` : null}
        ${list.loaded && list.items.length === 0
          ? html`<div class="empty">No projects match. Try another branch or clear the search.</div>`
          : null}
        ${list.nextAfter !== null
          ? html`<div class="list-more" ref=${sentinel}>
              <button class="btn" onClick=${more}>Load more</button>
            </div>`
          : null}
      </div>
    </div>
    ${list.loaded && list.nextAfter === null && list.items.length > 0
      ? html`<div class="list-end">${plural(list.items.length, "project", "projects")} shown</div>`
      : null}
    ${creating
      ? html`<${NewProjectDialog}
          ctx=${ctx}
          onClose=${() => setCreating(false)}
          onCreated=${(project) => {
            setCreating(false);
            navigate(buildUrl({ view: "project", number: project.number, tab: "overview" }));
          }}
        />`
      : null}
  </div>`;
}
