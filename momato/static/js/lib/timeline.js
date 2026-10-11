// Positions on a timeline window, for the Projects list and Action plans (R4.12, PL-4, D-029).

import { parseIso } from "./format.js";

const DAY_MS = 86_400_000;

/** From 1 January of last year to 31 December of next year. */
export function timelineWindow(todayIso) {
  const year = parseIso(todayIso).getUTCFullYear();
  return { start: `${year - 1}-01-01`, end: `${year + 1}-12-31` };
}

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

/** A date's place in the window as a percentage, clamped to 0 to 100. */
export function position(iso, window) {
  const start = parseIso(window.start).getTime();
  const end = parseIso(window.end).getTime();
  const at = parseIso(iso).getTime();
  return clamp(((at - start) / (end - start)) * 100, 0, 100);
}

/** The project bar: where it starts and how wide it is, at least 1 % wide (the design). */
export function barGeometry(startIso, endIso, window) {
  const left = position(startIso, window);
  const right = position(endIso, window);
  return { left, width: Math.max(1, right - left) };
}

/** Whole days from `a` to `b`. */
export function daysBetween(aIso, bIso) {
  return Math.round((parseIso(bIso) - parseIso(aIso)) / DAY_MS);
}
