// The Planning tab's rules and geometry (PG-1 – PG-5, R4.6): task status, the quarter axis and
// where bars, extensions and milestones sit. Mirrors momato/domain/tasks.py; both pass
// tests/fixtures/task_status.json.
import { formatDate, formatShortDate, parseIso } from "./format.js";

const DAY_MS = 86_400_000;
export const FULL_PROGRESS = 100;
export const MIN_BAR_WIDTH = 0.8; // percent of the axis: a one-day task stays visible

/** Bar colours by derived status (PG-3). */
export const STATUS_HUES = { done: 155, running: 285, planned: 235 };
export const STATUS_LABELS = { done: "Done", running: "Running", planned: "Planned" };

// ------------------------------------------------------------------ rules (R4.6)

/** Done at 100 %; Running once progress is above 0 or the start has come; else Planned. */
export function taskStatus(progress, plannedStart, today) {
  if (progress >= FULL_PROGRESS) return "done";
  if (progress > 0 || plannedStart <= today) return "running";
  return "planned";
}

export function isSlipped(plannedEnd, revisedEnd) {
  return revisedEnd !== null && revisedEnd !== undefined && revisedEnd > plannedEnd;
}

export function effectiveEnd(plannedEnd, revisedEnd) {
  return revisedEnd ?? plannedEnd;
}

/** "Where we are": running tasks read "45% · running", the others their status. */
export function statusText(status, progress) {
  return status === "running" ? `${progress}% · running` : STATUS_LABELS[status];
}

function wholeDays(fromIso, toIsoDate) {
  return Math.round((parseIso(toIsoDate) - parseIso(fromIso)) / DAY_MS);
}

/** How much of the span is behind us, rounded half up; 100 for a one-day span. */
export function timelinePercent(start, end, today) {
  const span = wholeDays(start, end);
  if (span <= 0) return 100;
  const elapsed = Math.min(Math.max(wholeDays(start, today), 0), span);
  return Math.floor((elapsed * 100 * 2 + span) / (2 * span));
}

/** "Starts 3 Nov 2025", "Ended 19 Dec 2025" or "45% of the timeline behind us". */
export function timelineText(start, end, today) {
  if (today < start) return `Starts ${formatDate(start)}`;
  if (today > end) return `Ended ${formatDate(end)}`;
  return `${timelinePercent(start, end, today)}% of the timeline behind us`;
}

/** PG-5: an end is not before its start, and a revised end is after the planned end. */
export function taskDateProblem(plannedStart, plannedEnd, revisedEnd) {
  if (!plannedStart || !plannedEnd) return "Give the task a start and an end.";
  if (plannedEnd < plannedStart) return "The end of a task cannot be before its start.";
  if (revisedEnd && revisedEnd <= plannedEnd) return "A revised end must be after the planned end.";
  return "";
}

// ------------------------------------------------------------------ the axis

/** The first day of the quarter that contains `iso`. */
export function quarterStart(iso) {
  const [year, month] = iso.split("-").map(Number);
  const first = Math.floor((month - 1) / 3) * 3 + 1;
  return `${year}-${String(first).padStart(2, "0")}-01`;
}

function nextQuarter(startIso) {
  const [year, month] = startIso.split("-").map(Number);
  return month >= 10 ? `${year + 1}-01-01` : `${year}-${String(month + 3).padStart(2, "0")}-01`;
}

/** "Q4/26". */
export function quarterLabel(startIso) {
  const [year, month] = startIso.split("-").map(Number);
  return `Q${Math.floor((month - 1) / 3) + 1}/${String(year % 100).padStart(2, "0")}`;
}

/** Every quarter from the one with the earliest date to the one with the latest. */
export function quartersBetween(fromIso, toIsoDate) {
  const quarters = [];
  let current = quarterStart(fromIso);
  const last = quarterStart(toIsoDate);
  while (current <= last) {
    quarters.push(current);
    current = nextQuarter(current);
  }
  return quarters;
}

/** The axis: whole quarters that cover the project's span and all its tasks (PG-1). */
export function axisFor(project, tasks) {
  let first = project.start_date;
  let last = project.end_date;
  for (const task of tasks) {
    if (task.planned_start < first) first = task.planned_start;
    const end = effectiveEnd(task.planned_end, task.revised_end);
    if (end > last) last = end;
  }
  const quarters = quartersBetween(first, last);
  return {
    quarters,
    start: quarters[0],
    end: nextQuarter(quarters[quarters.length - 1]), // exclusive: the first day after the axis
  };
}

/** A date's place on the axis as a percentage, clamped to 0 to 100. */
export function place(iso, axis) {
  const start = parseIso(axis.start).getTime();
  const end = parseIso(axis.end).getTime();
  const at = parseIso(iso).getTime();
  return Math.min(100, Math.max(0, ((at - start) / (end - start)) * 100));
}

/** Where today's line goes; null when today is outside the axis (PG-1). */
export function todayPlace(today, axis) {
  return today >= axis.start && today < axis.end ? place(today, axis) : null;
}

/** Width of one quarter column as a percentage of the axis (for the grid lines). */
export function quarterWidth(axis) {
  return 100 / axis.quarters.length;
}

// ------------------------------------------------------------------ rows

/** The line under a task's name: "5 Jan – 20 Mar · Running · slipped". */
export function taskSubline(task, today) {
  const status = taskStatus(task.progress, task.planned_start, today);
  const end = effectiveEnd(task.planned_end, task.revised_end);
  const slipped = isSlipped(task.planned_end, task.revised_end) ? " · slipped" : "";
  return `${formatShortDate(task.planned_start)} – ${formatShortDate(end)} · ${STATUS_LABELS[status]}${slipped}`;
}

/**
 * Everything a task row draws, as percentages of the axis: the planned bar, how much of it is
 * filled, the dashed extension to a revised end, and the milestone diamond.
 */
export function taskRow(task, axis, today) {
  const status = taskStatus(task.progress, task.planned_start, today);
  const left = place(task.planned_start, axis);
  const right = place(task.planned_end, axis);
  const slipped = isSlipped(task.planned_end, task.revised_end);
  let filled = task.progress;
  if (slipped) {
    // Progress is measured against the revised duration, so a slipped task is filled less.
    const planned = Math.max(1, wholeDays(task.planned_start, task.planned_end));
    const revised = wholeDays(task.planned_start, task.revised_end);
    filled = Math.min(100, Math.max(0, (task.progress * revised) / planned));
  }
  return {
    status,
    hue: STATUS_HUES[status],
    bar: { left, width: Math.max(MIN_BAR_WIDTH, right - left) },
    filled,
    extension: slipped
      ? { left: right, width: place(task.revised_end, axis) - right }
      : null,
    milestone: task.is_milestone ? place(effectiveEnd(task.planned_end, task.revised_end), axis) : null,
    subline: taskSubline(task, today),
  };
}
