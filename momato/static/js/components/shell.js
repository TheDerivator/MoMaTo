// The application shell: organisation tree pane, main menu, top bar (SH-1..SH-7).
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { html } from "../html.js";
import { formatLongDate, initials } from "../lib/format.js";
import { menuItem, usesTree } from "../lib/routes.js";
import { hoursNumber } from "../lib/format.js";
import { nodeLabel, treeRows } from "../lib/tree.js";
import { Link, navigate } from "../router.js";
import { Avatar } from "./ui.js";

const NAV = [
  { key: "projects", label: "Projects", hue: 285, icon: "nav-projects" },
  { key: "plans", label: "Action plans", hue: 60, icon: "nav-plans" },
  { key: "people", label: "People planning", hue: 235, icon: "nav-people" },
  { key: "timesheet", label: "My timesheet", hue: 155, icon: "nav-timesheet" },
];

const TREE_HINTS = {
  projects: "Filters the project list",
  plans: "Shows plans owned in this branch",
  people: "Filters the people shown",
};

/** The link of a main-menu item: Projects, People and Plans keep the selected node (SH-4). */
export function navTarget(key, node) {
  const withNode = (path) => (node ? `${path}?node=${node}` : path);
  if (key === "projects") return withNode("projects");
  if (key === "plans") return withNode("plans");
  if (key === "people") return withNode("people");
  return "timesheet";
}

// ------------------------------------------------------------------ tree pane

export function TreePane({ ctx, counts }) {
  const { route, tree, ui, setUi, narrow, overlay, setOverlay, selectedNode } = ctx;
  const collapsed = useMemo(() => new Set(ui.collapsedNodes), [ui.collapsedNodes]);
  const rows = useMemo(() => treeRows(tree, collapsed, counts), [tree, collapsed, counts]);
  const applies = usesTree(route);
  // Wide: the remembered state. Narrow: a rail, with the pane opened over the page on request.
  const open = applies && (narrow ? overlay === "tree" : !ui.treeCollapsed);

  const expand = () => {
    if (!applies) navigate(navTarget("projects", selectedNode));
    if (narrow) setOverlay("tree");
    else setUi({ ...ui, treeCollapsed: false });
  };
  const rail = html`<button
    class="tree-rail"
    title="Show organisation"
    aria-label="Show organisation"
    aria-expanded=${open ? "true" : "false"}
    inert=${open}
    onClick=${expand}
  >
    <span class="tree-rail__button" aria-hidden="true">»</span>
    ${applies ? html`<span class="tree-rail__name">${nodeLabel(tree, selectedNode)}</span>` : null}
  </button>`;
  if (!open) return rail;

  const toggleNode = (id) => {
    const next = new Set(collapsed);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setUi({ ...ui, collapsedNodes: [...next] });
  };
  const select = (id) => {
    const root = tree.root.id;
    const base = { ...route, node: id === root ? null : id };
    if (route.view === "plans") base.project = null; // a selection belongs to the plan it was made in
    navigate(ctx.urlFor(base));
  };

  const pane = html`<nav class="tree-pane" aria-label="Organisation">
    <div class="tree-pane__head">
      <span class="eyebrow">Organisation</span>
      <button
        class="icon-button"
        title="Collapse pane"
        aria-label="Collapse organisation pane"
        onClick=${() => (narrow ? setOverlay(null) : setUi({ ...ui, treeCollapsed: true }))}
      >
        «
      </button>
    </div>
    <div class="tree-pane__hint">${TREE_HINTS[route.view] ?? ""}</div>
    ${rows.map((row) => {
      const selected = row.id === selectedNode;
      return html`<div
        class=${`tree-item${selected ? " tree-item--selected" : ""}${row.depth <= 1 ? " tree-item--shallow" : ""}`}
        style=${{ paddingLeft: `${6 + row.depth * 14}px` }}
        key=${row.id}
      >
        ${row.hasChildren
          ? html`<button
              class="tree-item__chevron"
              aria-label=${row.expanded ? `Collapse ${row.name}` : `Expand ${row.name}`}
              aria-expanded=${row.expanded ? "true" : "false"}
              onClick=${() => toggleNode(row.id)}
            >
              ${row.expanded ? "▾" : "▸"}
            </button>`
          : html`<span class="tree-item__chevron" aria-hidden="true"></span>`}
        <button class="tree-row" aria-current=${selected ? "true" : undefined} onClick=${() => select(row.id)}>
          <span class="tree-row__name">${row.name}</span>
          <span class="tree-row__count">${row.count}</span>
        </button>
      </div>`;
    })}
  </nav>`;
  return narrow ? html`${rail}${pane}` : pane;
}

// ------------------------------------------------------------------ main menu

function NavIcon({ item }) {
  return html`<span
    class=${`nav-icon nav-icon--${item.key}`}
    aria-hidden="true"
    style=${{ "--hue": item.hue }}
  ></span>`;
}

function UserRow({ ctx, collapsed }) {
  const { me, toggleAppearance } = ctx;
  const person = { name: me.name, hue: me.is_anonymous ? 285 : (ctx.myPerson?.hue ?? 285) };
  const role = me.is_anonymous ? "Not signed in" : (me.job_title ?? (me.is_system ? "System account" : ""));
  if (collapsed) {
    return html`<button class="icon-button" style=${{ width: "36px", height: "36px" }} title="Appearance" aria-label="Appearance" onClick=${toggleAppearance}>
      <${Avatar} person=${person} size=${32} />
    </button>`;
  }
  return html`<button class="user-row" title="Appearance" aria-label=${`Appearance and account of ${me.name}`} onClick=${toggleAppearance}>
    <${Avatar} person=${person} size=${32} />
    <span class="user-row__text">
      <span class="user-row__name">${me.name}</span>
      <span class="user-row__role">${role}</span>
    </span>
    <span aria-hidden="true">◐</span>
  </button>`;
}

// ------------------------------------------------------------------ week card (SH-2, TS-15)

const DAY_LETTERS = ["M", "T", "W", "T", "F"];

function dayDotClass(day, todayIndex) {
  const classes = ["week-dot"];
  if (day.full) classes.push("week-dot--full");
  else if (day.open) classes.push("week-dot--open");
  else if (day.index > todayIndex && day.minutes === 0) classes.push("week-dot--future");
  if (day.index === todayIndex) classes.push("week-dot--today");
  return classes.join(" ");
}

/** The current week at a glance; it opens the timesheet. */
function WeekCard({ card }) {
  if (!card) return null;
  const { state } = card;
  return html`<${Link}
    class=${`week-card week-card--${state.state}`}
    href="timesheet"
    aria-label=${`${state.title} ${state.subline}`}
  >
    <span class="week-card__head">
      <span class="eyebrow">Week ${card.week_number}</span>
      <span class="week-card__hours">${hoursNumber(state.total_minutes)}/${hoursNumber(state.target_minutes)} h</span>
    </span>
    <span class="week-card__title">${state.title}</span>
    <span class="week-card__days" aria-hidden="true">
      ${card.days.map(
        (day) => html`<span
          key=${day.index}
          class=${dayDotClass(day, card.today_index)}
          style=${{ "--fill": `${Math.round(day.fill * 100)}%` }}
        >${DAY_LETTERS[day.index]}</span>`,
      )}
    </span>
    <span class="week-card__sub">${state.subline}</span>
    <span class="week-card__cta">${state.cta}</span>
  <//>`;
}

/** The collapsed rail's version: a mini ring and five day bars. */
function WeekRail({ card }) {
  if (!card) return null;
  const percent = Math.min(100, (card.state.total_minutes / Math.max(1, card.state.target_minutes)) * 100);
  return html`<${Link}
    class="week-rail"
    href="timesheet"
    title=${card.state.title}
    aria-label=${`${card.state.title} ${card.state.subline}`}
  >
    <span class=${`week-rail__ring${percent >= 100 ? " week-rail__ring--full" : ""}`} style=${{ "--pct": percent }}>
      <span class="week-rail__hours">${hoursNumber(card.state.total_minutes)}</span>
    </span>
    <span class="week-rail__bars" aria-hidden="true">
      ${card.days.map(
        (day) => html`<span key=${day.index} class=${`week-rail__bar${day.full ? " week-rail__bar--full" : day.open ? " week-rail__bar--open" : ""}`}>
          <span class="week-rail__fill" style=${{ width: `${Math.round(day.fill * 100)}%` }}></span>
        </span>`,
      )}
    </span>
  <//>`;
}

export function MainMenu({ ctx }) {
  const { route, ui, setUi, narrow, overlay, setOverlay, selectedNode } = ctx;
  const active = menuItem(route);
  const open = narrow ? overlay === "menu" : !ui.navCollapsed;
  const expand = () => (narrow ? setOverlay("menu") : setUi({ ...ui, navCollapsed: false }));
  const collapse = () => (narrow ? setOverlay(null) : setUi({ ...ui, navCollapsed: true }));
  const items = NAV.map((item) => {
    const href = navTarget(item.key, usesTree(route) || item.key === "timesheet" ? selectedNode : selectedNode);
    return { ...item, href };
  });

  const rail = html`<aside class="menu-rail" inert=${open}>
      <button class="menu-rail__logo" title="Expand menu" aria-label="Expand menu" onClick=${expand}>
        <span class="logo-mark"></span>
      </button>
      <nav class="menu-rail__nav" aria-label="Main">
        ${items.map(
          (item) => html`<${Link}
            key=${item.key}
            class="nav__item"
            href=${item.href}
            title=${item.label}
            aria-label=${item.label}
            aria-current=${item.key === active ? "page" : undefined}
          >
            <${NavIcon} item=${item} />
          <//>`,
        )}
      </nav>
      <div class="menu__spacer"></div>
      <${WeekRail} card=${ctx.weekCard} />
      <${UserRow} ctx=${ctx} collapsed=${true} />
      <button class="icon-button" title="Expand menu" aria-label="Expand menu" onClick=${expand}>»</button>
    </aside>`;
  if (!open) return rail;

  const menu = html`<aside class="menu">
    <div class="menu__logo">
      <span class="logo-mark"></span>
      <span class="menu__wordmark">momato</span>
      <button class="icon-button" title="Collapse menu" aria-label="Collapse menu" onClick=${collapse}>«</button>
    </div>
    <nav class="nav" aria-label="Main">
      ${items.map(
        (item) => html`<${Link}
          key=${item.key}
          class="nav__item"
          href=${item.href}
          aria-current=${item.key === active ? "page" : undefined}
        >
          <${NavIcon} item=${item} />${item.label}
        <//>`,
      )}
    </nav>
    <${WeekCard} card=${ctx.weekCard} />
    <div class="menu__spacer"></div>
    <${UserRow} ctx=${ctx} collapsed=${false} />
  </aside>`;
  return narrow ? html`${rail}${menu}` : menu;
}

// ------------------------------------------------------------------ top bar

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

export function TopBar({ ctx }) {
  const { route, boot, goSearch } = ctx;
  const input = useRef(null);
  const [text, setText] = useState(route.view === "projects" ? route.q : "");

  useEffect(() => {
    if (route.view === "projects") setText(route.q);
  }, [route.view === "projects" ? route.q : null]);

  useEffect(() => {
    const onKey = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const timer = useRef(0);
  const onInput = (event) => {
    const value = event.target.value;
    setText(value);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => goSearch(value), 250);
  };

  return html`<header class="topbar">
    <div class="search" role="search">
      <span class="search__glass" aria-hidden="true"></span>
      <input
        ref=${input}
        type="search"
        value=${text}
        onInput=${onInput}
        placeholder="Search projects, numbers, people"
        aria-label="Search projects"
      />
      <span class="search__chip" aria-hidden="true">${isMac ? "⌘K" : "Ctrl K"}</span>
    </div>
    <div class="topbar__spacer"></div>
    <span class="topbar__date">${formatLongDate(boot.today)}</span>
  </header>`;
}

export { initials };
