// People planning: planned days, time spent and the two compared, per person and bucket
// (PPL-1 – PPL-7). The server computes the numbers and classes; this view shows them.
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { Crumbs } from "../components/crumbs.js";
import { TimeExport } from "../components/exportmenu.js";
import { Avatar } from "../components/ui.js";
import { html } from "../html.js";
import { plural } from "../lib/format.js";
import {
  LEGENDS, MODES, PERIODS, cellView, gridTemplate, hiddenNote, lineTotal, toneClass, totalView,
} from "../lib/planning.js";
import { buildUrl } from "../lib/routes.js";
import { Link, navigate } from "../router.js";

const SUBS = {
  planned: "Planned days per person per quarter, against the days each person has available.",
  spent: "Time booked on projects and other work, against the time each person had available.",
  compare: "Time spent on the projects people are members of, against what was planned for them.",
};

function Segmented({ label, options, value, onPick }) {
  return html`<div class="segmented" role="group" aria-label=${label}>
    ${options.map(
      (o) => html`<button key=${o.key} type="button" aria-pressed=${value === o.key ? "true" : "false"} onClick=${() => onPick(o.key)}>
        ${o.label}
      </button>`,
    )}
  </div>`;
}

function Cell({ cell, mode, unit }) {
  const view = cellView(cell, mode, unit);
  return html`<div class=${`pp-cell ${toneClass(view.cls)}`} title=${view.title || undefined}>
    <span class="pp-cell__value">${view.label}</span>
    ${view.sub ? html`<span class="pp-cell__sub">${view.sub}</span>` : null}
  </div>`;
}

function Lines({ ctx, state, mode, template }) {
  if (state.error) return html`<div class="pp-lines" role="alert">${state.error}</div>`;
  if (!state.data) return html`<div class="pp-lines muted">Loading…</div>`;
  const { lines, unit } = state.data;
  if (lines.length === 0) return html`<div class="pp-lines muted">Nothing here for this period.</div>`;
  return html`<div class="pp-lines">
    ${lines.map((line, index) => {
      const status = line.status ? ctx.statuses.get(line.status) : null;
      return html`<div key=${`${line.kind}-${line.number ?? index}`} class="pp-line" style=${{ gridTemplateColumns: template }}>
        <div class="pp-line__name">
          <span class=${`dot${status?.gray ? " dot--gray" : ""}`} style=${{ "--hue": status?.hue ?? 285 }} aria-hidden="true"></span>
          ${line.number !== null
            ? html`<${Link} class="pp-line__link" href=${buildUrl({ view: "project", number: line.number, tab: "people" })}>${line.name}<//>
              ${line.kind === "non_member" ? html`<span class="pp-line__tag">not a member</span>` : null}`
            : html`<span class="pp-line__text">${line.name}</span>`}
        </div>
        <span class="pp-line__total">${lineTotal(line, mode, unit)}</span>
        ${line.cells.map((cell, i) => {
          const view = cellView(cell, mode, unit);
          const text = view.label === "–" ? "" : view.sub && mode === "compare" ? `${view.label}/${view.sub.replace(/^of /, "")}` : view.label;
          return html`<span key=${i} class=${`pp-line__cell ${mode === "compare" && cell.reference !== null ? toneClass(cell.cls) + "-text" : ""}`}>${text}</span>`;
        })}
      </div>`;
    })}
  </div>`;
}

export function PeopleView({ ctx, counts }) {
  const { route, tree } = ctx;
  const mode = route.mode;
  const period = route.period;
  const node = route.node;
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(() => new Set(route.person ? [route.person] : []));
  const [lines, setLines] = useState({}); // person id → { data | error }
  const timer = useRef(0);

  // The filter text goes to the server after a pause (the people of a large branch are many).
  const onFilter = (text) => {
    setFilter(text);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setQuery(text), 250);
  };

  const key = `${node}|${mode}|${period}|${query}`;
  useEffect(() => {
    let cancelled = false;
    setError("");
    api("people-planning", { params: { node, mode, period, q: query } })
      .then((body) => {
        if (cancelled) return;
        setData(body);
        setLines({}); // the lines belong to a mode and period
      })
      .catch((failure) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [key]);

  const loadLines = useCallback(
    async (person) => {
      setLines((current) => ({ ...current, [person]: {} }));
      try {
        const body = await api(`people-planning/${person}`, { params: { mode, period } });
        setLines((current) => ({ ...current, [person]: { data: body } }));
      } catch (failure) {
        setLines((current) => ({ ...current, [person]: { error: messageOf(failure) } }));
      }
    },
    [mode, period],
  );

  // Rows opened by the URL (person=) or by the user load their lines when the table is there.
  useEffect(() => {
    if (!data) return;
    for (const person of open) {
      if (!lines[person]) loadLines(person);
    }
  }, [data, open]);

  const toggle = (person) => {
    const next = new Set(open);
    if (next.has(person)) next.delete(person);
    else next.add(person);
    setOpen(next);
  };

  const go = (patch) => navigate(buildUrl({ ...route, ...patch }));
  const template = data ? gridTemplate(data.buckets.length) : "";
  const unit = data?.unit ?? "days";
  const note = data ? hiddenNote(data.hidden_count) : "";

  const rows = useMemo(() => data?.rows ?? [], [data]);

  return html`<div class="page people-page">
    <div class="list-header">
      <${Crumbs}
        ctx=${ctx}
        eyebrow="People planning"
        nodeId=${node}
        nodeCounts=${counts}
        onGo=${(id) => go({ node: id === tree.root.id ? null : id, person: null })}
      />
      <span class="list-count" aria-live="polite">${data ? plural(data.total_count, "person", "people") : ""}</span>
      <div class="list-header__spacer"></div>
      <${TimeExport} node=${node} buckets=${data?.buckets} today=${ctx.boot.today} />
      <div class="pp-switches">
        <${Segmented} label="Mode" options=${MODES} value=${mode} onPick=${(key) => go({ mode: key })} />
        ${mode !== "planned"
          ? html`<${Segmented} label="Period" options=${PERIODS} value=${period} onPick=${(key) => go({ period: key })} />`
          : null}
      </div>
    </div>
    <p class="pp-sub muted">${SUBS[mode]}</p>
    <div class="pp-legend-row">
      <span class="pp-range">${data?.range_label ?? ""}</span>
      <span class="list-header__spacer"></span>
      ${LEGENDS[mode].map(
        (item) => html`<span key=${item.cls} class="pp-legend"><span class=${`pp-legend__swatch ${toneClass(item.cls)}`}></span>${item.label}</span>`,
      )}
    </div>

    ${error ? html`<div class="empty" role="alert">${error}</div>` : null}
    ${note ? html`<p class="pp-hidden" role="note">${note}</p>` : null}

    <div class="table-card pp-card">
      <div class="pp-table">
        <div class="pp-row pp-row--head" style=${{ gridTemplateColumns: template || undefined }}>
          <div class="pp-head__person">
            <input
              class="header-filter"
              value=${filter}
              placeholder="Person ⌕"
              aria-label="Filter by person"
              onInput=${(e) => onFilter(e.target.value)}
            />
          </div>
          <span class="pp-head__label">${mode === "planned" ? String(ctx.boot.today.slice(0, 4)) : "Total"}</span>
          ${(data?.buckets ?? []).map(
            (b) => html`<div key=${b.start} class=${`pp-head__bucket${b.current ? " pp-head__bucket--now" : ""}`}>
              <span>${b.key}</span>
              ${b.sub ? html`<span class="pp-head__sub">${b.sub}</span>` : null}
            </div>`,
          )}
        </div>
        ${data && rows.length === 0
          ? html`<div class="empty">${
              data.hidden_count && mode !== "planned"
                ? "You may not see the hours of the people in this branch."
                : "No people match. Try another branch or clear the filter."
            }</div>`
          : null}
        ${rows.map((row) => {
          const isOpen = open.has(row.person.id);
          const total = totalView(row.total, mode, unit);
          return html`<div key=${row.person.id} class="pp-person">
            <div class="pp-row pp-row--person" style=${{ gridTemplateColumns: template }}>
              <div class="pp-person__who">
                <button
                  type="button"
                  class="pp-person__toggle"
                  aria-expanded=${isOpen ? "true" : "false"}
                  aria-label=${`${row.person.name}: ${isOpen ? "hide" : "show"} projects`}
                  onClick=${() => toggle(row.person.id)}
                >
                  <span class="pp-person__chevron" aria-hidden="true">${isOpen ? "▾" : "▸"}</span>
                  <${Avatar} person=${row.person} size=${32} />
                  <span class="pp-person__text">
                    <span class="pp-person__name">${row.person.name}</span>
                    <span class="pp-person__node">${row.org_node_name ?? ""}</span>
                  </span>
                </button>
              </div>
              <div class="pp-total">
                <span class="pp-total__value">${total.label}</span>
                <span class=${`pp-total__sub${total.tone ? ` pp-total__sub--${total.tone}` : ""}`}>${total.sub}</span>
              </div>
              ${row.cells.map((cell, i) => html`<${Cell} key=${i} cell=${cell} mode=${mode} unit=${unit} />`)}
            </div>
            ${isOpen
              ? html`<${Lines} ctx=${ctx} state=${lines[row.person.id] ?? {}} mode=${mode} template=${template} />`
              : null}
          </div>`;
        })}
      </div>
    </div>
  </div>`;
}
