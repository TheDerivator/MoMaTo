// People & days cells (PD-1 – PD-3): how a cell reads, and what may be typed into it.
import { formatDays } from "./format.js";

export const STEP = 0.5;

/** "12 d", or an en dash when nothing is planned. */
export function plannedText(planned) {
  return planned > 0 ? formatDays(planned) : "–";
}

/**
 * What a cell shows: the planned days, a bar of the days logged against them (red when over),
 * and "x logged" or "upcoming" for a quarter that has not started.
 */
export function cellView(cell) {
  const { planned, logged, upcoming } = cell;
  const percent = planned > 0 ? Math.min(100, (logged / planned) * 100) : logged > 0 ? 100 : 0;
  let sub = "";
  if (planned > 0 && upcoming && logged === 0) sub = "upcoming";
  else if (planned > 0 || logged > 0) sub = `${formatDays(logged).replace(/ d$/, "")} logged`;
  return { text: plannedText(planned), percent, over: logged > planned, sub };
}

/** The total column of a row: planned days and the days logged. */
export function totalView(plannedTotal, loggedTotal) {
  return { text: plannedText(plannedTotal), sub: `${formatDays(loggedTotal).replace(/ d$/, "")} logged` };
}

/**
 * Typed days for a cell: `{ value }` in steps of 0.5 from 0 to `max` (the quarter's working
 * days), else `{ error }`. A comma is accepted as the decimal separator.
 */
export function parseDays(text, max) {
  const trimmed = String(text).trim().replace(",", ".");
  if (trimmed === "") return { value: 0 };
  const value = Number(trimmed);
  if (!Number.isFinite(value) || !/^\d+(\.\d+)?$/.test(trimmed)) return { error: "Enter a number of days." };
  if (Math.round(value * 2) / 2 !== value) return { error: "Days go in steps of 0.5." };
  if (value > max) return { error: `This quarter has only ${max} working days.` };
  return { value };
}
