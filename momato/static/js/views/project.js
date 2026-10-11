// The project page: top line, badges, title, tabs (PP-1 – PP-7). The tabs are in their own files.
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";

import { ApiError, api, messageOf } from "../api.js";
import { InlineEdit } from "../components/inline.js";
import { StatusPill, useDismiss } from "../components/ui.js";
import { html } from "../html.js";
import { buildUrl, filtersOf, listRouteOf } from "../lib/routes.js";
import { pathTo } from "../lib/tree.js";
import { Link, navigate } from "../router.js";
import { ProjectDetails } from "./project-details.js";
import { ProjectLogbook } from "./project-logbook.js";
import { ProjectOverview } from "./project-overview.js";
import { ProjectPeople } from "./project-people.js";
import { ProjectPlanning } from "./project-planning.js";
import { ProjectRemarks } from "./project-remarks.js";
import { NotFound } from "./pages.js";

const TABS = [
  { key: "overview", label: "Overview" },
  { key: "planning", label: "Planning" },
  { key: "people", label: "People & days" },
  { key: "remarks", label: "Remarks", count: "remark_count" },
  { key: "logbook", label: "Logbook", count: "log_count" },
  { key: "details", label: "All details" },
];

/**
 * The project and its edits. Edits show at once and roll back with a toast when refused
 * (SH-10); they are sent one after the other, each with the version the last one returned.
 * A stale version (409) says so and reloads the project (PP-6).
 */
function useProject(number, toast) {
  const [project, setProject] = useState(null);
  const [phase, setPhase] = useState("loading"); // loading | ready | missing | error
  const latest = useRef(null);
  const chain = useRef(Promise.resolve());

  const commit = useCallback((next) => {
    latest.current = next;
    setProject(next);
  }, []);

  const load = useCallback(async () => {
    try {
      commit(await api(`projects/${number}`));
      setPhase("ready");
    } catch (error) {
      setPhase(error instanceof ApiError && error.status === 404 ? "missing" : "error");
    }
  }, [number, commit]);

  useEffect(() => {
    latest.current = null;
    setProject(null);
    setPhase("loading");
    chain.current = Promise.resolve();
    load();
  }, [number]);

  const edit = useCallback(
    (fields, preview = {}) => {
      const run = async () => {
        const before = latest.current;
        if (!before) return;
        commit({ ...before, ...preview });
        try {
          commit(
            await api(`projects/${number}`, {
              method: "PATCH",
              body: { version: before.version, ...fields },
            }),
          );
        } catch (error) {
          if (error instanceof ApiError && error.status === 409) {
            toast("Someone else changed this project. It has been reloaded.", "error");
            await load();
          } else {
            commit(before);
            toast(messageOf(error), "error");
          }
        }
      };
      chain.current = chain.current.then(run, run);
      return chain.current;
    },
    [number, commit, load, toast],
  );

  /** A change with its own endpoint that answers with the project (members, action plans). */
  const act = useCallback(
    async (path, method, { preview = null, body } = {}) => {
      const before = latest.current;
      if (preview && before) commit({ ...before, ...preview });
      try {
        commit(await api(`projects/${number}/${path}`, { method, body }));
      } catch (error) {
        if (before) commit(before);
        toast(messageOf(error), "error");
      }
    },
    [number, commit, toast],
  );

  return { project, phase, edit, act, refresh: load };
}

/** Where the project is in the list it came from, and its neighbours (PP-1). */
function useNeighbours(route, ready) {
  const [found, setFound] = useState(null);
  const filters = JSON.stringify([route.node, route.status, route.q, route.name, route.coordinator]);
  useEffect(() => {
    if (!ready) return undefined;
    let cancelled = false;
    const ask = async (params) => api(`projects/${route.number}/neighbours`, { params });
    const own = { node: route.node, status: route.status, q: route.q, name: route.name, coordinator: route.coordinator };
    (async () => {
      try {
        let body = await ask(own);
        let kept = true;
        if (!body.in_list) {
          body = await ask({}); // not in that list (any more): step through everything instead
          kept = false;
        }
        if (!cancelled) setFound({ ...body, kept });
      } catch {
        if (!cancelled) setFound(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [route.number, filters, ready]);
  return found;
}

function Stepper({ route, found }) {
  if (!found) return null;
  const carry = found.kept ? filtersOf(route) : filtersOf({});
  const go = (number) =>
    number === null
      ? undefined
      : () => navigate(buildUrl({ view: "project", number, tab: route.tab, ...carry }));
  const label = found.position === null ? "" : `${found.position} of ${found.total}`;
  return html`<div class="stepper">
    <button class="icon-button stepper__button" aria-label="Previous project" disabled=${found.previous === null} onClick=${go(found.previous)}>‹</button>
    <span class="stepper__position">${label}</span>
    <button class="icon-button stepper__button" aria-label="Next project" disabled=${found.next === null} onClick=${go(found.next)}>›</button>
  </div>`;
}

function StatusMenu({ project, ctx, edit }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useDismiss(ref, open, () => setOpen(false));
  const status = ctx.statuses.get(project.status);
  if (!project.can_edit) return html`<${StatusPill} status=${status} />`;
  return html`<div class="popover-anchor" ref=${ref}>
    <button
      type="button"
      class="status-pill status-pill--button"
      style=${{ "--hue": status.hue }}
      aria-haspopup="menu"
      aria-expanded=${open ? "true" : "false"}
      onClick=${() => setOpen(!open)}
    >
      <span class=${`dot${status.gray ? " dot--gray" : ""}`} style=${{ "--hue": status.hue }}></span>
      ${status.label}<span class="status-pill__caret" aria-hidden="true">▾</span>
    </button>
    ${open
      ? html`<div class="popover popover--below" role="menu" aria-label="Status">
          ${ctx.boot.statuses.map(
            (s) => html`<button
              key=${s.key}
              role="menuitemradio"
              aria-checked=${s.key === project.status ? "true" : "false"}
              class=${`menu-item${s.key === project.status ? " menu-item--current" : ""}`}
              onClick=${() => {
                setOpen(false);
                if (s.key !== project.status) edit({ status: s.key }, { status: s.key });
              }}
            >
              <span class=${`dot${s.gray ? " dot--gray" : ""}`} style=${{ "--hue": s.hue }}></span>
              <span class="menu-item__name">${s.label}</span>
            </button>`,
          )}
        </div>`
      : null}
  </div>`;
}

function PlanBadges({ project, ctx, act }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useDismiss(ref, open, () => setOpen(false));
  const { plans } = ctx.boot;
  const linked = new Set(project.plan_ids);
  const swatch = (plan) => html`<span class="swatch" style=${{ "--hue": plan.hue }}></span>`;
  return html`
    ${plans
      .filter((p) => linked.has(p.id))
      .map(
        (plan) => html`<${Link} key=${plan.id} class="plan-pill" href=${`plans/${plan.id}`}>${swatch(plan)}${plan.name}<//>`,
      )}
    ${project.can_edit
      ? html`<div class="popover-anchor" ref=${ref}>
          <button
            type="button"
            class="plan-add"
            aria-haspopup="menu"
            aria-expanded=${open ? "true" : "false"}
            onClick=${() => setOpen(!open)}
          >
            + Action plan
          </button>
          ${open
            ? html`<div class="popover popover--below" role="menu" aria-label="Action plans">
                ${plans.length === 0 ? html`<div class="empty">There are no action plans yet.</div>` : null}
                ${plans.map((plan) => {
                  const on = linked.has(plan.id);
                  return html`<button
                    key=${plan.id}
                    role="menuitemcheckbox"
                    aria-checked=${on ? "true" : "false"}
                    class="menu-item"
                    onClick=${() =>
                      act(`plans/${plan.id}`, on ? "DELETE" : "PUT", {
                        preview: {
                          plan_ids: on
                            ? project.plan_ids.filter((id) => id !== plan.id)
                            : [...project.plan_ids, plan.id],
                        },
                      })}
                  >
                    <span class=${`check-box${on ? " check-box--on" : ""}`} aria-hidden="true">${on ? "✓" : ""}</span>
                    <span class="menu-item__name">${plan.name}</span>
                  </button>`;
                })}
              </div>`
            : null}
        </div>`
      : null}
  `;
}

export function ProjectView({ ctx }) {
  const { route, tree, toast } = ctx;
  const { project, phase, edit, act, refresh } = useProject(route.number, toast);
  const found = useNeighbours(route, phase === "ready");
  const trail = useMemo(
    () => (project ? pathTo(tree, project.org_node_id) : []),
    [tree, project?.org_node_id],
  );

  useEffect(() => {
    if (project) document.title = `#${project.number} ${project.name} · MoMaTo`;
  }, [project?.number, project?.name]);

  if (phase === "missing") return html`<${NotFound} />`;
  if (phase === "error") return html`<div class="placeholder" role="alert">The project could not be loaded.</div>`;
  if (!project) return html`<div class="placeholder muted">Loading…</div>`;

  const carry = filtersOf(route);
  const tab = route.tab;
  const tabUrl = (key) => buildUrl({ view: "project", number: project.number, tab: key, ...carry });
  const body = { ctx, project, edit, act, refresh };

  return html`<div class="page project-page">
    <div class="project-topline">
      <${Link} class="back-link" href=${buildUrl(listRouteOf(route))}>← Projects<//>
      <nav class="org-trail" aria-label="Department">
        ${trail.map(
          (node, index) => html`${index > 0 ? html`<span class="org-trail__sep" aria-hidden="true">/</span>` : null}
            <${Link} key=${node.id} class="org-trail__node" href=${buildUrl({ view: "projects", node: index === 0 ? null : node.id, status: null, q: "", name: "", coordinator: "" })}>${node.name}<//>`,
        )}
      </nav>
      <div class="project-topline__spacer"></div>
      <${Stepper} route=${route} found=${found} />
    </div>

    <div class="project-head">
      <div class="badges">
        <span class="number-pill">#${project.number}</span>
        <${StatusMenu} project=${project} ctx=${ctx} edit=${edit} />
        <${PlanBadges} project=${project} ctx=${ctx} act=${act} />
      </div>
      <h1 class="project-title">
        <${InlineEdit}
          value=${project.name}
          editable=${project.can_edit}
          label="Project title"
          hint="Click to rename"
          describe=${false}
          className="project-title__text"
          maxLength=${200}
          onCommit=${(text) => {
            const name = text.trim();
            if (name && name !== project.name) edit({ name }, { name });
          }}
        />
      </h1>
    </div>

    <nav class="tabs" aria-label="Project sections">
      ${TABS.map((t) => {
        const count = t.count ? project[t.count] : 0;
        return html`<${Link}
          key=${t.key}
          class=${`tab${tab === t.key ? " tab--active" : ""}`}
          href=${tabUrl(t.key)}
          aria-current=${tab === t.key ? "page" : undefined}
        >
          ${t.label}${count ? html`<span class="tab__count">${count}</span>` : null}
        <//>`;
      })}
    </nav>

    <div class="tab-panel">
      ${tab === "overview" ? html`<${ProjectOverview} ...${body} tabUrl=${tabUrl} />` : null}
      ${tab === "remarks" ? html`<${ProjectRemarks} ...${body} />` : null}
      ${tab === "logbook" ? html`<${ProjectLogbook} ...${body} />` : null}
      ${tab === "details" ? html`<${ProjectDetails} ...${body} />` : null}
      ${tab === "planning" ? html`<${ProjectPlanning} ...${body} />` : null}
      ${tab === "people" ? html`<${ProjectPeople} ...${body} />` : null}
    </div>
  </div>`;
}
