// The People & days tab: planned days per member and quarter, and what was logged (PD-1 – PD-5).
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { ConfirmDialog } from "../components/dialogs.js";
import { PersonSearch } from "../components/inline.js";
import { Avatar } from "../components/ui.js";
import { html } from "../html.js";
import { cellView, parseDays, totalView } from "../lib/days.js";
import { formatDays } from "../lib/format.js";
import { quarterLabel, quarterStart } from "../lib/gantt.js";

/** One cell: the planned days (editable), a bar of days logged against them, the line under it. */
function Cell({ row, cell, workdays, editable, onSet, toast }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const input = useRef(null);
  const finished = useRef(false);
  const view = cellView(cell);

  useLayoutEffect(() => {
    if (editing) {
      input.current?.focus();
      input.current?.select();
    }
  }, [editing]);

  const begin = () => {
    finished.current = false;
    setDraft(cell.planned > 0 ? String(cell.planned) : "");
    setEditing(true);
  };
  const finish = (commit) => {
    if (finished.current) return;
    finished.current = true;
    setEditing(false);
    if (!commit) return;
    const parsed = parseDays(draft, workdays);
    if (parsed.error) toast(parsed.error, "error");
    else if (parsed.value !== cell.planned) onSet(row.person.id, cell.quarter_start, parsed.value);
  };

  return html`<div class="days-cell">
    ${editing
      ? html`<input
          ref=${input}
          class="inline-input days-cell__input"
          inputmode="decimal"
          aria-label=${`Planned days for ${row.person.name} in ${quarterLabel(cell.quarter_start)}`}
          value=${draft}
          onInput=${(e) => setDraft(e.target.value)}
          onBlur=${() => finish(true)}
          onKeyDown=${(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              finish(true);
            } else if (e.key === "Escape") {
              e.stopPropagation();
              finish(false);
            }
          }}
        />`
      : editable
        ? html`<button
            type="button"
            class="inline-edit days-cell__value"
            aria-label=${`${row.person.name}, ${quarterLabel(cell.quarter_start)}: ${view.text}. Set planned days`}
            onClick=${begin}
          >
            ${view.text}
          </button>`
        : html`<span class="days-cell__value">${view.text}</span>`}
    <span class="days-bar" aria-hidden="true">
      <span class=${`days-bar__fill${view.over ? " days-bar__fill--over" : ""}`} style=${{ width: `${view.percent}%` }}></span>
    </span>
    <span class="days-cell__sub">${view.sub}</span>
  </div>`;
}

export function ProjectPeople({ ctx, project, act, refresh }) {
  const [grid, setGrid] = useState(null);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState(null);
  const { toast } = ctx;
  const number = project.number;
  const editor = project.can_edit;

  const load = useCallback(async () => {
    try {
      setGrid(await api(`projects/${number}/planned-days`));
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [number]);
  useEffect(() => {
    load();
  }, [number]);

  const setCell = async (userId, quarter, days) => {
    const before = grid;
    // Shown at once; the server's grid replaces it, or the old one comes back with a message.
    setGrid({
      ...grid,
      rows: grid.rows.map((row) =>
        row.person.id !== userId
          ? row
          : {
              ...row,
              cells: row.cells.map((c) => (c.quarter_start === quarter ? { ...c, planned: days } : c)),
              planned_total: row.cells.reduce(
                (sum, c) => sum + (c.quarter_start === quarter ? days : c.planned),
                0,
              ),
            },
      ),
    });
    try {
      setGrid(
        await api(`projects/${number}/planned-days`, {
          method: "PUT",
          body: { user_id: userId, quarter_start: quarter, days },
        }),
      );
      refresh(); // the Days card follows
    } catch (failure) {
      setGrid(before);
      toast(messageOf(failure), "error");
    }
  };

  if (error && !grid) return html`<div class="empty" role="alert">${error}</div>`;
  if (!grid) return html`<div class="muted">Loading…</div>`;

  const nowQuarter = quarterStart(ctx.boot.today);
  const template = `minmax(200px, 1.5fr) repeat(${grid.quarters.length}, minmax(76px, 1fr)) 100px`;
  const memberIds = project.members.map((m) => m.id);

  return html`<div class="people-days">
    <section class="card people-days__card" aria-label="Planned days per person">
      <div class="people-days__table">
        <div class="people-days__row people-days__row--head" style=${{ gridTemplateColumns: template }}>
          <span class="days-head days-head--label">Person</span>
          ${grid.quarters.map(
            (q) => html`<span key=${q} class=${`days-head${q === nowQuarter ? " days-head--now" : ""}`}>${quarterLabel(q)}</span>`,
          )}
          <span class="days-head days-head--label">Total</span>
        </div>
        ${grid.rows.map((row) => {
          const total = totalView(row.planned_total, row.logged_total);
          return html`<div key=${row.person.id} class="people-days__row" style=${{ gridTemplateColumns: template }}>
            <div class="days-person">
              <${Avatar} person=${row.person} size=${32} />
              <div class="days-person__text">
                <span class="days-person__name">${row.person.name}</span>
                <span class="days-person__tag">${row.is_coordinator ? "Coordinator" : (row.person.job_title ?? "")}</span>
              </div>
              ${editor && !row.is_coordinator
                ? html`<button
                    type="button"
                    class="person-chip__remove"
                    aria-label=${`Remove ${row.person.name}`}
                    onClick=${() => setRemoving(row.person)}
                  >
                    ×
                  </button>`
                : null}
            </div>
            ${row.cells.map(
              (cell, index) => html`<${Cell}
                key=${cell.quarter_start}
                row=${row}
                cell=${cell}
                workdays=${grid.workdays[index]}
                editable=${editor}
                onSet=${setCell}
                toast=${toast}
              />`,
            )}
            <div class="days-total">
              <span class="days-total__value">${total.text}</span>
              <span class="days-cell__sub">${total.sub}</span>
            </div>
          </div>`;
        })}
        ${grid.also_booked.length > 0
          ? html`<div class="people-days__also">
              <h3 class="people-days__also-title">Also booked</h3>
              ${grid.also_booked.map(
                (row) => html`<div key=${row.person.id} class="people-days__row" style=${{ gridTemplateColumns: template }}>
                  <div class="days-person">
                    <${Avatar} person=${row.person} size=${32} />
                    <div class="days-person__text">
                      <span class="days-person__name">${row.person.name}</span>
                      <span class="days-person__tag">${row.person.job_title ?? ""}</span>
                    </div>
                  </div>
                  ${row.cells.map(
                    (cell) => html`<div key=${cell.quarter_start} class="days-cell">
                      <span class="days-cell__sub">${cell.logged > 0 ? `${formatDays(cell.logged)} logged` : ""}</span>
                    </div>`,
                  )}
                  <div class="days-total">
                    <span class="days-cell__sub">${formatDays(row.logged_total)} logged</span>
                  </div>
                </div>`,
              )}
            </div>`
          : null}
      </div>
    </section>
    <div class="people-days__foot">
      <span class="muted">Number: planned days. Bar: days logged against them.</span>
      <span class="people-days__spacer"></span>
      ${editor
        ? html`<span class="popover-anchor">
            <button type="button" class="btn btn--dark" onClick=${() => setAdding(true)}>+ Add person</button>
            ${adding
              ? html`<${PersonSearch}
                  title="Add a person"
                  exclude=${memberIds}
                  onClose=${() => setAdding(false)}
                  onPick=${async (person) => {
                    setAdding(false);
                    await act("members", "POST", {
                      body: { user_id: person.id },
                      preview: { members: [...project.members, person] },
                    });
                    await load(); // the grid changes with the members, once the server has answered
                  }}
                />`
              : null}
          </span>`
        : null}
    </div>
    ${removing
      ? html`<${ConfirmDialog}
          title=${`Remove ${removing.name}?`}
          confirmLabel="Remove"
          onClose=${() => setRemoving(null)}
          onConfirm=${async () => {
            await act(`members/${removing.id}`, "DELETE", {
              preview: { members: project.members.filter((m) => m.id !== removing.id) },
            });
            await load();
          }}
        >
          <p>
            ${removing.name} leaves this project and their planned days on it are removed. Hours they
            booked stay on the project.
          </p>
        <//>`
      : null}
  </div>`;
}
