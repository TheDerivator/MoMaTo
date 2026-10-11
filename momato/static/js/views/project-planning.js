// The Planning tab: the project's tasks on a quarter axis, and the task dialog (PG-1 – PG-5).
import { useMemo, useState } from "preact/hooks";

import { ApiError, api, messageOf } from "../api.js";
import { ConfirmDialog, Dialog } from "../components/dialogs.js";
import { html } from "../html.js";
import { formatHours, plural } from "../lib/format.js";
import {
  axisFor, quarterLabel, quarterStart, quarterWidth, taskDateProblem, taskRow, todayPlace,
} from "../lib/gantt.js";

function Legend() {
  return html`<span class="legend">
    <span class="legend__item"><span class="legend__swatch legend__swatch--planned"></span>Planned</span>
    <span class="legend__item"><span class="legend__swatch legend__swatch--progress"></span>Progress</span>
    <span class="legend__item"><span class="legend__swatch legend__swatch--revised"></span>Revised end</span>
    <span class="legend__item"><span class="legend__swatch legend__swatch--milestone"></span>Milestone</span>
  </span>`;
}

function TaskDialog({ project, task, onClose, onSaved }) {
  const adding = !task;
  const [name, setName] = useState(task?.name ?? "");
  const [start, setStart] = useState(task?.planned_start ?? project.start_date);
  const [end, setEnd] = useState(task?.planned_end ?? project.end_date);
  const [revised, setRevised] = useState(task?.revised_end ?? "");
  const [milestone, setMilestone] = useState(task?.is_milestone ?? false);
  const [progress, setProgress] = useState(String(task?.progress ?? 0));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const base = `projects/${project.number}/tasks`;

  const save = async (event) => {
    event.preventDefault();
    const problem = taskDateProblem(start, end, revised || null);
    const percent = Number(progress);
    if (!name.trim()) return setError("A task needs a name.");
    if (problem) return setError(problem);
    if (!Number.isInteger(percent) || percent < 0 || percent > 100) {
      return setError("Progress is a whole number from 0 to 100.");
    }
    setBusy(true);
    setError("");
    const fields = {
      name: name.trim(),
      planned_start: start,
      planned_end: end,
      is_milestone: milestone,
      progress: percent,
    };
    try {
      if (adding) {
        await api(base, { method: "POST", body: { ...fields, revised_end: revised || null } });
      } else {
        await api(`${base}/${task.id}`, {
          method: "PATCH",
          body: {
            ...fields,
            version: task.version,
            revised_end: revised || null,
            clear_revised_end: !revised,
          },
        });
      }
      await onSaved();
      onClose();
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status === 409
          ? "Someone else changed this task. Close this and open it again."
          : messageOf(failure),
      );
      setBusy(false);
    }
  };

  const move = async (direction) => {
    setBusy(true);
    try {
      await api(`${base}/${task.id}/move`, { method: "POST", body: { direction } });
      await onSaved();
      onClose();
    } catch (failure) {
      setError(messageOf(failure));
      setBusy(false);
    }
  };

  const index = project.tasks.findIndex((t) => t.id === task?.id);

  return html`<${Dialog} title=${adding ? "Add task" : "Edit task"} onClose=${onClose}>
    <form class="form" onSubmit=${save}>
      <label class="field">
        <span class="field__label">Name</span>
        <input class="input" value=${name} maxlength="200" required onInput=${(e) => setName(e.target.value)} />
      </label>
      <div class="field-row">
        <label class="field">
          <span class="field__label">Planned start</span>
          <input class="input" type="date" value=${start} required onInput=${(e) => setStart(e.target.value)} />
        </label>
        <label class="field">
          <span class="field__label">Planned end</span>
          <input class="input" type="date" value=${end} required onInput=${(e) => setEnd(e.target.value)} />
        </label>
      </div>
      <div class="field-row">
        <label class="field">
          <span class="field__label">Revised end (optional)</span>
          <input class="input" type="date" value=${revised} onInput=${(e) => setRevised(e.target.value)} />
        </label>
        <label class="field">
          <span class="field__label">Progress (%)</span>
          <input
            class="input"
            type="number"
            min="0"
            max="100"
            step="1"
            value=${progress}
            onInput=${(e) => setProgress(e.target.value)}
          />
        </label>
      </div>
      <label class="check-row">
        <input type="checkbox" checked=${milestone} onChange=${(e) => setMilestone(e.target.checked)} />
        This task is a milestone
      </label>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions dialog__actions--split">
        ${!adding
          ? html`<span class="dialog__group">
              <button type="button" class="btn btn--ghost" disabled=${busy || index <= 0} onClick=${() => move("up")}>Move up</button>
              <button type="button" class="btn btn--ghost" disabled=${busy || index >= project.tasks.length - 1} onClick=${() => move("down")}>Move down</button>
              <button type="button" class="btn btn--ghost btn--danger" disabled=${busy} onClick=${() => setRemoving(true)}>Delete</button>
            </span>`
          : html`<span></span>`}
        <span class="dialog__group">
          <button type="button" class="btn btn--ghost" onClick=${onClose}>Cancel</button>
          <button type="submit" class="btn btn--dark" disabled=${busy}>${adding ? "Add task" : "Save"}</button>
        </span>
      </div>
    </form>
    ${removing
      ? html`<${ConfirmDialog}
          title="Delete this task?"
          confirmLabel="Delete task"
          onClose=${() => setRemoving(false)}
          onConfirm=${async () => {
            try {
              await api(`${base}/${task.id}`, { method: "DELETE" });
              await onSaved();
              onClose();
            } catch (failure) {
              setError(messageOf(failure));
            }
          }}
        >
          <p>
            ${task.booked_minutes > 0
              ? `${formatHours(task.booked_minutes)} booked on “${task.name}” move to General.`
              : `“${task.name}” has no hours booked.`}
          </p>
        <//>`
      : null}
  <//>`;
}

export function ProjectPlanning({ ctx, project, refresh }) {
  const [dialog, setDialog] = useState(null); // { task } to edit, { task: null } to add
  const today = ctx.boot.today;
  const editor = project.can_edit;
  const axis = useMemo(() => axisFor(project, project.tasks), [project.start_date, project.end_date, project.tasks]);
  const now = todayPlace(today, axis);
  const nowQuarter = quarterStart(today);
  const width = quarterWidth(axis);

  return html`<section class="gantt card" aria-label="Task timeline">
    <div class="gantt__head">
      <b class="gantt__count">${plural(project.tasks.length, "task", "tasks")}</b>
      <${Legend} />
      <span class="gantt__spacer"></span>
      ${editor
        ? html`<button type="button" class="btn btn--dark" onClick=${() => setDialog({ task: null })}>+ Add task</button>`
        : null}
    </div>
    <div class="gantt__grid">
      <div class="gantt__corner">Task</div>
      <div class="gantt__axis">
        ${axis.quarters.map(
          (q) => html`<div key=${q} class=${`gantt__quarter${q === nowQuarter ? " gantt__quarter--now" : ""}`}>${quarterLabel(q)}</div>`,
        )}
        ${now !== null ? html`<span class="gantt__today-pill" style=${{ left: `${now}%` }}>Today</span>` : null}
      </div>
      ${project.tasks.length === 0
        ? html`<p class="gantt__empty muted">
            No tasks yet.${editor ? " Add the first one to start the timeline." : ""}
          </p>`
        : null}
      ${project.tasks.map((task) => {
        const row = taskRow(task, axis, today);
        const open = editor ? () => setDialog({ task }) : undefined;
        return html`<div key=${task.id} class=${`gantt__task${editor ? " gantt__task--editable" : ""}`} onClick=${open}>
          <div class="gantt__label">
            ${editor
              ? html`<button type="button" class="gantt__name gantt__name--button" onClick=${(e) => { e.stopPropagation(); open(); }}>${task.name}</button>`
              : html`<span class="gantt__name">${task.name}</span>`}
            <span class="gantt__sub">${row.subline}${task.is_milestone ? " · milestone" : ""}</span>
          </div>
          <div class="gantt__lane" style=${{ "--hue": row.hue, "--quarter": `${width}%` }} aria-hidden="true">
            <span class="gantt__bar" style=${{ left: `${row.bar.left}%`, width: `${row.bar.width}%` }}>
              <span class="gantt__fill" style=${{ width: `${row.filled}%` }}></span>
            </span>
            ${row.extension
              ? html`<span class="gantt__extension" style=${{ left: `${row.extension.left}%`, width: `${row.extension.width}%` }}></span>`
              : null}
            ${row.milestone !== null
              ? html`<span class="gantt__milestone" style=${{ left: `${row.milestone}%` }}></span>`
              : null}
            ${now !== null ? html`<span class="gantt__today" style=${{ left: `${now}%` }}></span>` : null}
          </div>
        </div>`;
      })}
    </div>
    ${dialog
      ? html`<${TaskDialog}
          project=${project}
          task=${dialog.task}
          onClose=${() => setDialog(null)}
          onSaved=${refresh}
        />`
      : null}
  </section>`;
}
