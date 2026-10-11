// My timesheet: the summary card, the days and the fill-up cards (TS-1 – TS-12).
// Every change shows at once and is saved as the cell's new absolute minutes (TS-9).
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";

import { ApiError, api, messageOf, sendOnExit } from "../api.js";
import { Celebration } from "../components/celebration.js";
import { useDismiss } from "../components/ui.js";
import { html } from "../html.js";
import { formatHours, hoursNumber } from "../lib/format.js";
import { createSaveQueue } from "../lib/savequeue.js";
import {
  addStep, cardNote, celebration, cellKey, fillFraction, lineDayMinutes, lineHue,
  lineWeekMinutes, pickerChoices, pickerOrder, reachedPlan, removeStep, taskWeekMinutes, viaOnDay,
  weekRange,
  weekView,
} from "../lib/timesheet.js";
import { Link } from "../router.js";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const SELECTED_KEY = "momato-timesheet";

function readSelected() {
  try {
    return JSON.parse(localStorage.getItem(SELECTED_KEY) ?? "{}") ?? {};
  } catch {
    return {};
  }
}

function rememberSelected(map) {
  try {
    localStorage.setItem(SELECTED_KEY, JSON.stringify(map));
  } catch {
    // blocked storage: the choice just does not persist
  }
}

/** The numbers of a day of the month, from the week's Monday. */
function dayNumber(mondayIso, index) {
  const date = new Date(`${mondayIso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + index);
  return date.getUTCDate();
}

function isoOfDay(mondayIso, index) {
  const date = new Date(`${mondayIso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + index);
  return date.toISOString().slice(0, 10);
}

// ------------------------------------------------------------------ project picker

function AddProject({ onPick, taken }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState([]);
  const ref = useRef(null);
  const input = useRef(null);
  useDismiss(ref, open, () => setOpen(false));

  useEffect(() => {
    if (!open) return undefined;
    input.current?.focus();
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api("search/projects", { params: { q: query, bookable: true } })
        .then((found) => !cancelled && setHits(found.filter((h) => !taken.includes(h.number))))
        .catch(() => !cancelled && setHits([]));
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  return html`<div class="popover-anchor ts-add" ref=${ref}>
    <button type="button" class="btn" aria-haspopup="dialog" aria-expanded=${open ? "true" : "false"} onClick=${() => setOpen(!open)}>
      + Add project
    </button>
    ${open
      ? html`<div class="popover popover--below ts-add__popover" role="dialog" aria-label="Add a project">
          <input
            ref=${input}
            class="input"
            role="combobox"
            aria-expanded="true"
            aria-controls="ts-add-results"
            aria-label="Find a project"
            placeholder="Number or name"
            value=${query}
            onInput=${(e) => setQuery(e.target.value)}
            onKeyDown=${(e) => e.key === "Escape" && setOpen(false)}
          />
          <div id="ts-add-results" role="listbox" aria-label="Projects">
            ${hits.length === 0 ? html`<div class="empty" role="option" aria-selected="false">No project found.</div>` : null}
            ${hits.map(
              (hit) => html`<button
                key=${hit.number}
                type="button"
                role="option"
                aria-selected="false"
                class="menu-item"
                onClick=${() => {
                  setOpen(false);
                  onPick(hit);
                }}
              >
                <span class="menu-item__name">#${hit.number} ${hit.name}</span>
              </button>`,
            )}
          </div>
        </div>`
      : null}
  </div>`;
}

// ------------------------------------------------------------------ one card

function LineCard({ line, hue, day, dayLabel, working, selected, onSelect, onPlus, onMinus, step, ctx }) {
  const choices = pickerChoices(line);
  const booked = lineWeekMinutes(line.minutes);
  const planned = line.planned_minutes;
  const fill = fillFraction(planned, booked);
  const reached = reachedPlan(line, booked);
  const dayMinutes = lineDayMinutes(line.minutes, day);
  const via = viaOnDay(line, day);
  const chosen = choices.find((c) => c.key === selected) ?? choices[0];
  const status = line.status ? ctx.statuses.get(line.status) : null;
  const sub =
    line.kind === "project"
      ? `#${line.number}${status ? ` · ${status.label}` : ""}`
      : line.kind === "other_work"
        ? "Meetings, training, admin"
        : "Vacation, out of office";
  const planText = planned ? ` of ${hoursNumber(Math.round(planned / 60) * 60)}` : "";
  return html`<article
    class=${`ts-card${reached ? " ts-card--reached" : ""}`}
    style=${{ "--hue": hue }}
    aria-label=${line.name}
    data-line=${line.key}
  >
    <div class="ts-card__fill" style=${{ height: `${fill * 100}%` }}></div>
    ${reached ? html`<span class="ts-card__badge" title="Planned hours reached" aria-label="Planned hours reached">✓</span>` : null}
    <div class="ts-card__body">
      <span class="ts-card__sub">${sub}</span>
      ${line.kind === "project"
        ? html`<${Link} class="ts-card__title ts-card__title--link" href=${`projects/${line.number}`} title="Open project">${line.name}<//>`
        : html`<span class="ts-card__title">${line.name}</span>`}
      <span class="ts-card__note">${cardNote(line, booked)}</span>
      <div class="ts-tasks" role="group" aria-label=${`Task for ${line.name}`}>
        ${choices.map((choice) => {
          const week = taskWeekMinutes(line.minutes, choice.key);
          const on = chosen && choice.key === chosen.key;
          return html`<button
            key=${choice.key}
            type="button"
            class=${`ts-task${on ? " ts-task--on" : ""}`}
            aria-pressed=${on ? "true" : "false"}
            onClick=${() => onSelect(choice.key)}
          >
            <span class="ts-task__dot" aria-hidden="true"></span>
            <span class="ts-task__name">${choice.name}</span>
            <span class="ts-task__hours">${week ? formatHours(week) : ""}</span>
          </button>`;
        })}
      </div>
      <div class="ts-card__spacer"></div>
      <div class="ts-card__day">
        <span class="ts-card__hours" aria-label=${`${hoursNumber(dayMinutes)} hours on ${dayLabel}`}>${hoursNumber(dayMinutes)}</span>
        <span class="ts-card__unit">h on ${dayLabel}</span>
      </div>
      <span class="ts-card__week">${hoursNumber(booked)}${planText} h this week</span>
      <div class="ts-card__buttons">
        <button
          type="button"
          class="ts-minus"
          aria-label=${`Remove ${formatHours(step)} from ${line.name}`}
          disabled=${!working}
          onClick=${onMinus}
        >
          −
        </button>
        <button
          type="button"
          class="ts-plus"
          aria-label=${`Add ${formatHours(step)} to ${line.name}`}
          disabled=${!working}
          onClick=${onPlus}
        >
          +${formatHours(step)}
        </button>
      </div>
      <span class="ts-card__goes">goes to ${chosen?.name ?? "General"}</span>
      ${via.length ? html`<span class="ts-card__via">via ${via.join(", ")}</span>` : null}
    </div>
  </article>`;
}

// ------------------------------------------------------------------ the view

export function TimesheetView({ ctx }) {
  const { route, boot, toast, appearance } = ctx;
  const label = route.week; // null: the current week
  const [data, setData] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [minutes, setMinutes] = useState({}); // line key → { task key → [5] }
  const [extra, setExtra] = useState([]); // lines added with "+ Add project"
  const [submitted, setSubmitted] = useState(false);
  const [day, setDay] = useState(0);
  const [selected, setSelected] = useState(readSelected);
  const [party, setParty] = useState(false);
  const queue = useRef(null);
  const latest = useRef({ minutes: {}, week: "" });

  // ---- loading a week
  const load = useCallback(async () => {
    setPhase("loading");
    try {
      const body = await api(label ? `timesheet/${label}` : "timesheet");
      setData(body);
      const map = {};
      for (const line of body.lines) map[line.key] = line.minutes;
      latest.current = { minutes: map, week: body.week };
      setMinutes(map);
      setExtra([]);
      setSubmitted(body.submitted);
      setDay(body.is_current ? Math.min(body.today_index, 4) : 0);
      setPhase("ready");
      for (const line of body.lines) {
        for (const [task, week] of Object.entries(line.minutes)) {
          week.forEach((value, index) =>
            queue.current?.known({ day: isoOfDay(body.monday, index), line: line.key, task }, value),
          );
        }
      }
    } catch (error) {
      setPhase(error instanceof ApiError && error.status === 422 ? "refused" : "error");
    }
  }, [label]);

  useEffect(() => {
    queue.current = createSaveQueue({
      send: (cell) =>
        api(`timesheet/${cell.week}/cells`, {
          method: "PUT",
          body: { day: cell.day, line: cell.line, task: cell.task, minutes: cell.minutes },
        }),
      onSaved: (_cell, result) => setSubmitted(result.submitted),
      onFailed: (cell, error, restoreTo) => {
        toast(`${messageOf(error)} The change was not saved.`, "error");
        setCell(cell.line, cell.task, new Date(`${cell.day}T00:00:00Z`).getUTCDay() - 1, restoreTo, false);
      },
    });
    // Closing the page must not lose what is still waiting to be saved.
    const onHide = () => {
      for (const cell of queue.current?.takePending() ?? []) {
        sendOnExit(`timesheet/${cell.week}/cells`, {
          body: { day: cell.day, line: cell.line, task: cell.task, minutes: cell.minutes },
        });
      }
    };
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      queue.current?.flush();
    };
  }, []);

  useEffect(() => {
    queue.current?.flush().finally(load);
  }, [label]);

  // ---- the lines on screen
  const lines = useMemo(() => {
    if (!data) return [];
    const known = new Set(data.lines.map((l) => l.key));
    const withMinutes = [...data.lines, ...extra.filter((l) => !known.has(l.key))].map((l) => ({
      ...l,
      minutes: minutes[l.key] ?? l.minutes,
    }));
    // projects first (planned by hours, then the rest), then Other work and Time off
    const projects = withMinutes.filter((l) => l.kind === "project");
    const rest = withMinutes.filter((l) => l.kind !== "project");
    return [...projects, ...rest];
  }, [data, extra, minutes]);

  // ---- derived week
  const targets = data ? data.days.map((d) => d.target_minutes) : [0, 0, 0, 0, 0];
  const perDay = [0, 1, 2, 3, 4].map((d) => lines.reduce((sum, l) => sum + lineDayMinutes(l.minutes, d), 0));
  const view = data
    ? weekView(targets, perDay, {
        todayIndex: data.today_index,
        submitted,
        weekNumber: data.iso_week,
      })
    : null;

  // The sidebar's card follows this week while it is the current one (TS-15).
  useEffect(() => {
    if (!data || !view || !data.is_current) return;
    ctx.setWeekCard?.({
      week: data.week,
      week_number: data.iso_week,
      today_index: data.today_index,
      days: view.days.map((d, i) => ({
        index: i, date: isoOfDay(data.monday, i), target_minutes: d.target, minutes: d.minutes,
        full: d.full, open: d.open, tag: d.tag, fill: d.fill,
      })),
      submitted,
      state: {
        state: view.state, full_days: view.fullDays, working_days: view.workingDays,
        open_days: view.openDays, total_minutes: view.totalMinutes, target_minutes: view.targetMinutes,
        title: view.title, cta: view.cta, headline: view.headline, subline: view.subline,
      },
    });
  }, [data, JSON.stringify(perDay), submitted]);

  // ---- changing a cell
  function setCell(line, task, dayIndex, value, send = true) {
    setMinutes((current) => {
      const week = { ...(current[line] ?? {}) };
      const cells = [...(week[task] ?? [0, 0, 0, 0, 0])];
      cells[dayIndex] = value;
      week[task] = cells;
      const next = { ...current, [line]: week };
      latest.current.minutes = next;
      return next;
    });
    if (send && data) {
      setSubmitted(false); // a change reopens a submitted week (TS-10)
      queue.current?.set({
        week: data.week,
        day: isoOfDay(data.monday, dayIndex),
        line,
        task,
        minutes: value,
      });
    }
  }

  function dayCells(index) {
    const cells = {};
    for (const [lineKey, tasks] of Object.entries(latest.current.minutes)) {
      for (const [task, week] of Object.entries(tasks)) cells[cellKey(lineKey, task)] = week[index];
    }
    return cells;
  }

  function selectedTask(line) {
    const choices = pickerChoices(line);
    return choices.find((c) => c.key === selected[line.key])?.key ?? choices[0]?.key ?? "general";
  }

  const book = (line, direction) => {
    if (!data) return;
    const task = selectedTask(line);
    const options = { step: data.step_minutes, cap: data.cap_minutes };
    const cells = dayCells(day);
    const result =
      direction > 0
        ? addStep(cells, line.key, task, options)
        : removeStep(cells, line.key, task, { ...options, picker: pickerOrder(line) });
    if (!result.changed) return;
    const prefix = `${line.key}:`;
    const changedTask = result.changed.slice(prefix.length);
    setCell(line.key, changedTask, day, result.day[result.changed]);
  };

  const choose = (line, task) => {
    const next = { ...selected, [line.key]: task };
    setSelected(next);
    rememberSelected(next);
  };

  const addProject = async (hit) => {
    try {
      const tasks = await api(`projects/${hit.number}/tasks`);
      const key = `project:${hit.number}`;
      const extraLine = {
        key,
        kind: "project",
        number: hit.number,
        name: hit.name,
        status: hit.status,
        planned_minutes: null,
        unplanned: true,
        choices: [
          ...tasks.map((t) => ({ key: `task:${t.id}`, name: t.name, status: t.status, position: t.position })),
          { key: "general", name: "General", status: null, position: 10000 },
        ],
        minutes: {},
      };
      setExtra((current) => (current.some((l) => l.key === key) ? current : [...current, extraLine]));
    } catch (error) {
      toast(messageOf(error), "error");
    }
  };

  const submit = async () => {
    if (!data || submitted) return;
    await queue.current?.flush();
    try {
      const result = await api(`timesheet/${data.week}/submit`, { method: "POST" });
      setSubmitted(result.submitted);
      if (appearance.celebrate) setParty(true);
    } catch (error) {
      toast(messageOf(error), "error");
    }
  };

  if (phase === "refused") {
    return html`<div class="placeholder">
      <h1>That week is not open</h1>
      <p class="muted">Weeks that have not started cannot be booked.</p>
      <${Link} href="timesheet">Back to this week<//>
    </div>`;
  }
  if (phase === "error") return html`<div class="placeholder" role="alert">Your timesheet could not be loaded.</div>`;
  if (!data || !view) return html`<div class="placeholder muted">Loading…</div>`;

  const totalMinutes = view.totalMinutes;
  const targetMinutes = view.targetMinutes;
  const percent = Math.min(100, (totalMinutes / Math.max(1, targetMinutes)) * 100);
  const complete = totalMinutes >= targetMinutes && targetMinutes > 0;
  const dayLabel = DAY_LABELS[day];
  const summary = celebration(lines, data.iso_week, totalMinutes);
  const takenNumbers = lines.filter((l) => l.kind === "project").map((l) => l.number);

  return html`<div class="timesheet">
    <div class="ts-head">
      <div class="ts-head__text">
        <span class="ts-head__range">Week ${data.iso_week} · ${weekRange(data.monday, data.friday)}</span>
        <h1 class="ts-head__title">${view.headline}</h1>
      </div>
      <nav class="ts-weeks" aria-label="Weeks">
        <${Link} class="icon-button ts-weeks__button" href=${`timesheet/${data.previous}`} aria-label="Previous week">‹<//>
        ${data.is_current
          ? html`<span class="ts-weeks__current">This week</span>`
          : html`<${Link} class="btn" href="timesheet">This week<//>`}
        ${data.next
          ? html`<${Link} class="icon-button ts-weeks__button" href=${`timesheet/${data.next}`} aria-label="Next week">›<//>`
          : html`<span class="icon-button ts-weeks__button ts-weeks__button--off" aria-hidden="true">›</span>`}
      </nav>
    </div>

    <section class="ts-summary card" aria-label="Week summary">
      <div class=${`ts-ring${complete ? " ts-ring--full" : ""}`} style=${{ "--pct": percent }} role="img" aria-label=${`${hoursNumber(totalMinutes)} of ${hoursNumber(targetMinutes)} hours`}>
        <div class="ts-ring__inner">
          <span class="ts-ring__hours">${hoursNumber(totalMinutes)}</span>
          <span class="ts-ring__of">of ${hoursNumber(targetMinutes)} h</span>
        </div>
      </div>
      <div class="ts-summary__main">
        <div class="ts-stack" aria-hidden="true">
          ${lines.map((line, index) => {
            const booked = lineWeekMinutes(line.minutes);
            return booked
              ? html`<span key=${line.key} class="ts-stack__part" style=${{ "--hue": lineHue(index), width: `${(booked / Math.max(1, targetMinutes)) * 100}%` }}></span>`
              : null;
          })}
        </div>
        <div class="ts-days" role="group" aria-label="Day">
          ${view.days.map((d) => {
            const fullHours = hoursNumber(d.target);
            return html`<button
              key=${d.index}
              type="button"
              class=${`ts-day${day === d.index ? " ts-day--on" : ""}${d.full ? " ts-day--full" : ""}${d.open ? " ts-day--open" : ""}`}
              aria-pressed=${day === d.index ? "true" : "false"}
              disabled=${!d.working}
              onClick=${() => setDay(d.index)}
            >
              <span class="ts-day__top">
                <b>${DAY_LABELS[d.index]}</b>
                <span class="ts-day__date">${dayNumber(data.monday, d.index)}</span>
                <span class="ts-day__tag">${{ done: "✓", today: "Today", next: "Next", open: "Open", "": "" }[d.tag]}</span>
              </span>
              <span class="ts-day__bar"><span class="ts-day__fill" style=${{ width: `${d.fill * 100}%` }}></span></span>
              <span class="ts-day__hours">${hoursNumber(d.minutes)} / ${fullHours} h</span>
            </button>`;
          })}
        </div>
      </div>
      <button
        type="button"
        class=${`ts-submit${submitted ? " ts-submit--done" : ""}`}
        aria-disabled=${submitted ? "true" : undefined}
        onClick=${submit}
      >
        ${submitted ? "Submitted ✓" : "Submit week"}
      </button>
    </section>

    <p class="ts-hint muted">
      Adding to <b>${DAY_NAMES[day]}</b>. In each card, pick the task you worked on; the card fills up
      towards your planned hours.
    </p>

    <div class="ts-cards">
      ${lines.map(
        (line, index) => html`<${LineCard}
          key=${line.key}
          line=${line}
          hue=${lineHue(index)}
          day=${day}
          dayLabel=${dayLabel}
          working=${view.days[day].working}
          selected=${selectedTask(line)}
          onSelect=${(task) => choose(line, task)}
          onPlus=${() => book(line, 1)}
          onMinus=${() => book(line, -1)}
          step=${data.step_minutes}
          ctx=${ctx}
        />`,
      )}
    </div>
    <div class="ts-foot">
      <${AddProject} onPick=${addProject} taken=${takenNumbers} />
    </div>

    ${party
      ? html`<${Celebration}
          summary=${summary}
          totalMinutes=${totalMinutes}
          targetMinutes=${targetMinutes}
          onClose=${() => setParty(false)}
        />`
      : null}
  </div>`;
}
