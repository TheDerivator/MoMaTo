// Action plans: a plan's timeline by department, totals, selected project and feed (AP-1 – AP-8).
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { Crumbs } from "../components/crumbs.js";
import { ConfirmDialog, Dialog, PersonPicker } from "../components/dialogs.js";
import { ProjectSearch } from "../components/projectsearch.js";
import { Avatar, StatusPill, useDismiss } from "../components/ui.js";
import { html } from "../html.js";
import { formatDate, plural, relativeDate } from "../lib/format.js";
import {
  PLAN_HUES, changeText, chosenPlan, meter, meterText, metaLine, plansInBranch, reachCovers,
  reachableNodes, statusDots, windowMonths, windowYears,
} from "../lib/plans.js";
import { buildUrl } from "../lib/routes.js";
import { barGeometry, position, timelineWindow } from "../lib/timeline.js";
import { pathTo } from "../lib/tree.js";
import { Link, navigate } from "../router.js";

const PLAIN_PLAN = { name: "", description: "", owner_org_node_id: null, coordinator: null, hue: PLAN_HUES[0] };

// ------------------------------------------------------------------ the plan dialog

function PlanDialog({ ctx, plan, defaultNode, onClose, onSaved }) {
  const { boot, tree, me } = ctx;
  const nodes = reachableNodes(me.permissions["plan.manage"], tree);
  const editing = Boolean(plan);
  const person = (id) => boot.people.find((p) => p.id === id);
  const start = editing
    ? { ...plan, coordinator: person(plan.coordinator_id) ?? null }
    : {
        ...PLAIN_PLAN,
        owner_org_node_id: nodes.some((n) => n.id === defaultNode) ? defaultNode : nodes[0]?.id,
        coordinator: me.person_id ? person(me.person_id) ?? null : null,
      };
  const [name, setName] = useState(start.name);
  const [description, setDescription] = useState(start.description);
  const [owner, setOwner] = useState(start.owner_org_node_id);
  const [coordinator, setCoordinator] = useState(start.coordinator);
  const [hue, setHue] = useState(start.hue);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (!coordinator) return setError("Choose a coordinator.");
    setBusy(true);
    setError("");
    const body = {
      name: name.trim(),
      description: description.trim(),
      owner_org_node_id: Number(owner),
      coordinator_id: coordinator.id,
      hue,
    };
    try {
      const saved = editing
        ? await api(`plans/${plan.id}`, { method: "PATCH", body: { ...body, version: plan.version } })
        : await api("plans", { method: "POST", body });
      await onSaved(saved);
      onClose();
    } catch (failure) {
      setError(messageOf(failure));
      setBusy(false);
    }
  };

  return html`<${Dialog} title=${editing ? "Edit plan" : "New plan"} onClose=${onClose}>
    <form class="form" onSubmit=${submit}>
      <label class="field">
        <span class="field__label">Name</span>
        <input class="input" value=${name} maxlength="200" required onInput=${(e) => setName(e.target.value)} />
      </label>
      <label class="field">
        <span class="field__label">Description</span>
        <textarea class="textarea" value=${description} maxlength="5000" onInput=${(e) => setDescription(e.target.value)}></textarea>
      </label>
      <label class="field">
        <span class="field__label">Owned by</span>
        <select class="select" value=${owner} required onChange=${(e) => setOwner(e.target.value)}>
          ${nodes.map((n) => html`<option key=${n.id} value=${n.id} selected=${n.id === Number(owner)}>${"– ".repeat(n.depth)}${n.name}</option>`)}
        </select>
      </label>
      <${PersonPicker} label="Coordinator" value=${coordinator} onChange=${setCoordinator} required=${true} />
      <div class="field" role="radiogroup" aria-label="Colour">
        <span class="field__label">Colour</span>
        <div class="swatches">
          ${PLAN_HUES.map(
            (h) => html`<button
              key=${h}
              type="button"
              role="radio"
              aria-checked=${h === hue ? "true" : "false"}
              aria-label=${`Hue ${h}`}
              class=${`swatch-button${h === hue ? " swatch-button--on" : ""}`}
              style=${{ "--hue": h }}
              onClick=${() => setHue(h)}
            ></button>`,
          )}
        </div>
      </div>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" onClick=${onClose}>Cancel</button>
        <button class="btn btn--dark" type="submit" disabled=${busy}>${editing ? "Save" : "Create plan"}</button>
      </div>
    </form>
  <//>`;
}

// ------------------------------------------------------------------ pieces of the page

/** "⋯" next to the name: edit or delete the plan (AP-3). */
function PlanMenu({ onEdit, onDelete }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useDismiss(ref, open, () => setOpen(false));
  const choose = (action) => () => {
    setOpen(false);
    action();
  };
  return html`<div class="plan-menu popover-anchor" ref=${ref}>
    <button
      type="button"
      class="icon-button"
      aria-label="Plan actions"
      aria-haspopup="menu"
      aria-expanded=${open ? "true" : "false"}
      onClick=${() => setOpen(!open)}
    >
      ⋯
    </button>
    ${open
      ? html`<div class="popover popover--below" role="menu" aria-label="Plan actions">
          <button type="button" role="menuitem" class="menu-item" onClick=${choose(onEdit)}>
            <span class="menu-item__name">Edit plan</span>
          </button>
          <button type="button" role="menuitem" class="menu-item" onClick=${choose(onDelete)}>
            <span class="menu-item__name">Delete plan</span>
          </button>
        </div>`
      : null}
  </div>`;
}

function Meter({ days, thick = false }) {
  const m = meter(days);
  return html`<span class=${`plan-meter${thick ? " plan-meter--thick" : ""}`} aria-hidden="true">
    <span class="plan-meter__fill" style=${{ width: `${m.logged}%` }}></span>
    <span class="plan-meter__tick" style=${{ left: `${m.expected}%` }}></span>
  </span>`;
}

function Totals({ overview }) {
  const { days } = overview;
  const plainDays = (v) => String(Math.round(v * 10) / 10);
  return html`<section class="card plan-totals" aria-label="Totals">
    <div class="plan-totals__figure">
      <span class="plan-totals__number">${plainDays(days.logged)}</span>
      <span class="muted">of ${plainDays(days.planned)} planned days logged across ${plural(overview.project_count, "project", "projects")}</span>
    </div>
    <div class="plan-totals__meter"><${Meter} days=${days} thick=${true} /></div>
    <span class="muted plan-totals__note">Tick = expected by today</span>
  </section>`;
}

function Timeline({ ctx, overview, selected, onSelect, collapsed, onToggle }) {
  const { boot } = ctx;
  const window_ = useMemo(() => timelineWindow(boot.today), [boot.today]);
  const years = windowYears(window_);
  const monthWidth = 100 / windowMonths(window_);
  const today = position(boot.today, window_);
  const order = boot.statuses.map((s) => s.key);

  return html`<section class="card plan-timeline" aria-label="Timeline">
    <div class="plan-timeline__table">
      <div class="plan-timeline__row plan-timeline__row--head">
        <span class="plan-timeline__label">Department / project</span>
        <div class="plan-timeline__years">
          ${years.map((y) => html`<span key=${y} class="plan-timeline__year">${y}</span>`)}
        </div>
        <span class="plan-timeline__label plan-timeline__label--days">Days</span>
      </div>
      ${overview.groups.length === 0
        ? html`<div class="empty">No projects attached to this plan yet.</div>`
        : null}
      ${overview.groups.map((group) => {
        const open = !collapsed.has(group.org_node_id);
        const span = barGeometry(group.start_date, group.end_date, window_);
        return html`<div key=${group.org_node_id} class="plan-group">
          <div class="plan-timeline__row plan-group__head">
            <button
              type="button"
              class="plan-group__toggle"
              aria-expanded=${open ? "true" : "false"}
              onClick=${() => onToggle(group.org_node_id)}
            >
              <span class="plan-group__chevron" aria-hidden="true">${open ? "▾" : "▸"}</span>
              <span class="plan-group__name">${group.name}</span>
              <span class="plan-group__count">${group.projects.length}</span>
              ${group.is_owner ? html`<span class="plan-group__owner">Owner</span>` : null}
              <span class="plan-group__dots" aria-hidden="true">
                ${statusDots(group.status_counts, order).map(
                  (key, i) => html`<span key=${i} class=${`dot${ctx.statuses.get(key)?.gray ? " dot--gray" : ""}`} style=${{ "--hue": ctx.statuses.get(key)?.hue ?? 285 }}></span>`,
                )}
              </span>
            </button>
            <div class="plan-lane" aria-hidden="true">
              <span class="plan-lane__span" style=${{ left: `${span.left}%`, width: `${span.width}%` }}></span>
              <span class="plan-lane__today" style=${{ left: `${today}%` }}></span>
            </div>
            <div class="plan-days">
              <span class="plan-days__text">${meterText(group.days)}</span>
              <${Meter} days=${group.days} />
            </div>
          </div>
          ${open
            ? group.projects.map((project) => {
                const status = ctx.statuses.get(project.status);
                const bar = barGeometry(project.start_date, project.end_date, window_);
                const on = selected === project.number;
                return html`<div
                  key=${project.number}
                  class=${`plan-timeline__row plan-project${on ? " plan-project--on" : ""}`}
                >
                  <button
                    type="button"
                    class="plan-project__button"
                    aria-pressed=${on ? "true" : "false"}
                    onClick=${() => onSelect(on ? null : project.number)}
                  >
                    <span class="plan-project__name">${project.name}</span>
                    <${StatusPill} status=${status} />
                  </button>
                  <div class="plan-lane plan-lane--grid" style=${{ "--month": `${monthWidth}%` }} aria-hidden="true">
                    <span
                      class="plan-lane__bar"
                      style=${{ left: `${bar.left}%`, width: `${bar.width}%`, "--hue": status.hue }}
                    ></span>
                    <span class="plan-lane__today" style=${{ left: `${today}%` }}></span>
                  </div>
                  <div class="plan-days">
                    <span class="plan-days__text">${meterText(project.days)}</span>
                    <${Meter} days=${project.days} />
                  </div>
                </div>`;
              })
            : null}
        </div>`;
      })}
    </div>
  </section>`;
}

function Summary({ ctx, project, plan, canRemove, onClose, onRemove }) {
  const status = ctx.statuses.get(project.status);
  return html`<section class="card plan-summary" aria-label="Selected project">
    <div class="plan-summary__head">
      <${StatusPill} status=${status} />
      <span class="muted">#${project.number}</span>
      <span class="plan-summary__spacer"></span>
      <button type="button" class="icon-button" aria-label="Back to the whole plan" title="Back to the whole plan" onClick=${onClose}>×</button>
    </div>
    <h2 class="plan-summary__name">${project.name}</h2>
    <div class="plan-summary__who">
      <${Avatar} person=${project.coordinator} size=${24} />
      <span class="muted">${project.coordinator.name} · ${formatDate(project.start_date)} – ${formatDate(project.end_date)}</span>
    </div>
    <p class="plan-summary__goal">${project.goal}</p>
    <div class="plan-summary__days">
      <span class="muted">Days logged</span>
      <b>${meterText(project.days)}</b>
    </div>
    <${Meter} days=${project.days} thick=${true} />
    <div class="plan-summary__actions">
      <${Link} class="btn btn--dark" href=${buildUrl({ view: "project", number: project.number, tab: "overview" })}>Open project →<//>
      ${canRemove
        ? html`<button type="button" class="btn btn--ghost" onClick=${onRemove}>Remove from plan</button>`
        : null}
    </div>
  </section>`;
}

function Feed({ ctx, items, title }) {
  return html`<section class="card plan-feed" aria-label=${title}>
    <h2 class="card__title">${title}</h2>
    ${items?.length === 0 ? html`<span class="muted">No updates yet.</span>` : null}
    ${(items ?? []).map((item, index) => {
      const href = buildUrl({ view: "project", number: item.project_number, tab: item.tab });
      const day = item.at.slice(0, 10);
      return html`<${Link} key=${index} class="plan-feed__item" href=${href}>
        <${Avatar} person=${item.actor} size=${28} />
        <span class="plan-feed__text">
          <span class="plan-feed__who"><b>${item.actor.name}</b> · ${relativeDate(day, ctx.boot.today)}</span>
          <span class="plan-feed__project">#${item.project_number} ${item.project_name}</span>
          ${item.kind === "remark"
            ? html`<span class="plan-feed__excerpt">${item.excerpt}</span>`
            : html`<span class="plan-feed__change">
                <span class="muted">${changeText(item)}</span>
                ${item.from_value !== null ? html`<span class="log-chip log-chip--old">${item.from_value}</span><span aria-hidden="true">→</span>` : null}
                <span class="log-chip log-chip--new" style=${{ "--hue": 285 }}>${item.to_value}</span>
              </span>`}
        </span>
      <//>`;
    })}
  </section>`;
}

// ------------------------------------------------------------------ the view

export function PlansView({ ctx, counts }) {
  const { route, boot, tree, me, toast } = ctx;
  const node = route.node;
  const visible = useMemo(() => plansInBranch(boot.plans, tree, node), [boot.plans, tree, node]);
  const plan = chosenPlan(visible, route.plan);
  const [overview, setOverview] = useState(null);
  const [feed, setFeed] = useState(null);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState(() => new Set());
  const [dialog, setDialog] = useState(null); // "new" | "edit"
  const [removing, setRemoving] = useState(false);
  const [adding, setAdding] = useState(false);
  const selected = route.project;

  const planId = plan?.id ?? null;
  const manage = me.permissions["plan.manage"];
  const canManage = plan ? reachCovers(manage, tree, plan.owner_org_node_id) : false;
  const canCreate = reachableNodes(manage, tree).length > 0;
  const canLink = canManage || me.permissions["project.edit"].everywhere || me.permissions["project.edit"].node_ids.length > 0;

  const url = (patch) => buildUrl({ ...route, ...patch });
  const go = (patch, options) => navigate(url(patch), options);

  const loadOverview = useCallback(async () => {
    if (planId === null) return;
    try {
      setOverview(await api(`plans/${planId}/overview`));
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [planId]);
  const selectedProject = useMemo(() => {
    if (!overview || selected === null) return null;
    for (const group of overview.groups) {
      const found = group.projects.find((p) => p.number === selected);
      if (found) return found;
    }
    return null;
  }, [overview, selected]);

  // The feed follows the project shown in the summary: a number in the URL that is not in this
  // plan (after changing branch) is ignored.
  const focus = selectedProject?.number ?? null;
  const loadFeed = useCallback(async () => {
    if (planId === null) return;
    try {
      setFeed(await api(`plans/${planId}/feed`, { params: { project: focus } }));
    } catch {
      setFeed({ items: [] });
    }
  }, [planId, focus]);

  useEffect(() => {
    setOverview(null);
    setFeed(null);
    loadOverview();
  }, [planId, plan?.project_count]);
  useEffect(() => {
    if (overview) loadFeed();
  }, [overview, focus]);

  const ownerPath = plan ? pathTo(tree, plan.owner_org_node_id).slice(1).map((n) => n.name) : [];
  const toggle = (id) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const afterSave = async (saved) => {
    await ctx.reload();
    if (saved?.id) go({ plan: saved.id, project: null }, { replace: true });
  };

  const addProject = async (hit) => {
    setAdding(false);
    try {
      await api(`plans/${planId}/projects`, { method: "POST", body: { number: hit.number } });
      await ctx.reload();
      await loadOverview();
      await loadFeed();
      go({ project: hit.number }, { replace: true });
    } catch (failure) {
      toast(messageOf(failure), "error");
    }
  };

  const removeProject = async () => {
    try {
      await api(`plans/${planId}/projects/${selected}`, { method: "DELETE" });
      await ctx.reload();
      go({ project: null }, { replace: true });
    } catch (failure) {
      toast(messageOf(failure), "error");
    }
  };

  const crumb = (nodeId) => pathTo(tree, nodeId ?? tree.root.id).at(-1)?.name ?? tree.root.name;

  return html`<div class="page plans-page">
    <div class="list-header">
      <${Crumbs}
        ctx=${ctx}
        eyebrow="Action plans"
        nodeId=${node}
        nodeCounts=${counts}
        onGo=${(id) => go({ node: id === tree.root.id ? null : id, plan: null, project: null })}
      />
      <span class="list-count" aria-live="polite">${plural(visible.length, "plan", "plans")}</span>
      <div class="list-header__spacer"></div>
      ${canCreate ? html`<button class="btn btn--dark" onClick=${() => setDialog("new")}>+ New plan</button>` : null}
    </div>

    ${visible.length === 0
      ? html`<div class="card plan-empty">
          <h2 class="plan-empty__title">No action plans owned by ${crumb(node)}</h2>
          <p class="muted">Plans belong to the department that owns them. Go up a level${canCreate ? " or start a new one here" : ""}.</p>
        </div>`
      : html`
          <div class="segmented plan-tabs" role="group" aria-label="Action plans">
            ${visible.map(
              (p) => html`<button
                key=${p.id}
                type="button"
                class="plan-tab"
                aria-pressed=${plan?.id === p.id ? "true" : "false"}
                onClick=${() => go({ plan: p.id, project: null })}
              >
                <span class="swatch" style=${{ "--hue": p.hue }} aria-hidden="true"></span>
                <span class="plan-tab__name">${p.name}</span>
                <span class="plan-tab__count">${p.project_count}</span>
              </button>`,
            )}
          </div>

          ${plan
            ? html`<div class="plan-intro">
                <span class="plan-meta">
                  ${overview
                    ? html`Owned by <b>${metaLine(overview, ownerPath).owner}</b> · ${metaLine(overview, ownerPath).rest}`
                    : html`Owned by <b>${ownerPath.join(" › ")}</b>`}
                </span>
                <div class="plan-intro__title">
                  <h2 class="plan-name">${plan.name}</h2>
                  ${canManage
                    ? html`<${PlanMenu} onEdit=${() => setDialog("edit")} onDelete=${() => setRemoving(true)} />`
                    : null}
                </div>
                ${plan.description ? html`<p class="plan-description">${plan.description}</p>` : null}
              </div>`
            : null}

          ${error ? html`<div class="empty" role="alert">${error}</div>` : null}
          ${overview ? html`<${Totals} overview=${overview} />` : html`<div class="muted">Loading…</div>`}

          ${overview
            ? html`<div class="plan-body">
                <div class="plan-body__main">
                  <${Timeline}
                    ctx=${ctx}
                    overview=${overview}
                    selected=${selected}
                    onSelect=${(number) => go({ plan: planId, project: number })}
                    collapsed=${collapsed}
                    onToggle=${toggle}
                  />
                  ${canLink
                    ? html`<div class="plan-adder popover-anchor">
                        <button type="button" class="btn" aria-haspopup="dialog" onClick=${() => setAdding(true)}>+ Add project</button>
                        ${adding
                          ? html`<${ProjectSearch}
                              title="Add a project to this plan"
                              onClose=${() => setAdding(false)}
                              onPick=${addProject}
                            />`
                          : null}
                      </div>`
                    : null}
                </div>
                <div class="plan-body__side">
                  ${selectedProject
                    ? html`<${Summary}
                        ctx=${ctx}
                        project=${selectedProject}
                        plan=${plan}
                        canRemove=${canLink}
                        onClose=${() => go({ project: null })}
                        onRemove=${removeProject}
                      />`
                    : null}
                  <${Feed}
                    ctx=${ctx}
                    items=${feed?.items ?? null}
                    title=${selectedProject ? "Latest on this project" : "Recent across this plan"}
                  />
                </div>
              </div>`
            : null}
        `}

    ${dialog === "new"
      ? html`<${PlanDialog} ctx=${ctx} plan=${null} defaultNode=${node ?? tree.root.id} onClose=${() => setDialog(null)} onSaved=${afterSave} />`
      : null}
    ${dialog === "edit" && plan
      ? html`<${PlanDialog} ctx=${ctx} plan=${plan} onClose=${() => setDialog(null)} onSaved=${afterSave} />`
      : null}
    ${removing && plan
      ? html`<${ConfirmDialog}
          title=${`Delete “${plan.name}”?`}
          confirmLabel="Delete plan"
          onClose=${() => setRemoving(false)}
          onConfirm=${async () => {
            try {
              await api(`plans/${plan.id}`, { method: "DELETE" });
              await ctx.reload();
              go({ plan: null, project: null }, { replace: true });
            } catch (failure) {
              toast(messageOf(failure), "error");
            }
          }}
        >
          <p>The plan is removed; its projects stay and lose this plan from their pills.</p>
        <//>`
      : null}
  </div>`;
}
