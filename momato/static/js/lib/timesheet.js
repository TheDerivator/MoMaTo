// The timesheet's rules without any layout (TS-12): the + and − steps (R4.8), the states of a
// week (R4.9), the task picker order and the numbers the cards show. Mirrors
// momato/domain/timesheet.py; both pass tests/fixtures/booking.json and week_states.json.
import { formatHours, hoursNumber } from "./format.js";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five"];
export const PAST_WEEK = 7; // the "today index" of a week that is over
export const LINE_HUES = [285, 155, 235, 60, 330];

/** A cell of a day is keyed "line:task". */
export function cellKey(line, task) {
  return `${line}:${task}`;
}

function total(day) {
  return Object.values(day).reduce((sum, minutes) => sum + minutes, 0);
}

// ------------------------------------------------------------------ booking (R4.8)

/** +: a step on the selected task unless the day (time off too) would pass the cap. */
export function addStep(day, line, task, { step, cap }) {
  if (total(day) + step > cap) return { day, changed: null };
  const key = cellKey(line, task);
  return { day: { ...day, [key]: (day[key] ?? 0) + step }, changed: key };
}

/** −: one step from the selected task, else from the first task of the line that has time. */
export function removeStep(day, line, task, { step, picker }) {
  for (const candidate of [task, ...picker.filter((t) => t !== task)]) {
    const key = cellKey(line, candidate);
    const value = day[key] ?? 0;
    if (value > 0) return { day: { ...day, [key]: Math.max(0, value - step) }, changed: key };
  }
  return { day, changed: null };
}

// ------------------------------------------------------------------ week states (R4.9)

function capitalised(word) {
  return word[0].toUpperCase() + word.slice(1);
}

function openDayNames(openDays) {
  if (openDays.length === 1) return WEEKDAYS[openDays[0]];
  if (openDays.length === 2) return `${WEEKDAYS[openDays[0]]} and ${WEEKDAYS[openDays[1]]}`;
  return `${openDays.length} days`;
}

/** Full / open / tag of each weekday; `todayIndex` is Monday 0 in the current week, 7 later. */
export function dayViews(targets, booked, todayIndex) {
  return targets.map((target, index) => {
    const minutes = booked[index];
    const working = target > 0;
    const full = working && minutes >= target;
    const open = working && index < todayIndex - 1 && !full;
    let tag = "";
    if (!working) tag = "";
    else if (full) tag = "done";
    else if (index === todayIndex) tag = "today";
    else if (index > todayIndex) tag = "next";
    else if (open) tag = "open";
    const fill = working ? Math.min(1, minutes / target) : 0;
    return { index, target, minutes, working, full, open, tag, fill };
  });
}

/** The week's state with the texts of the week card (TS-15) and the headline (TS-2). */
export function weekView(targets, booked, { todayIndex, submitted, weekNumber }) {
  const days = dayViews(targets, booked, todayIndex);
  const working = days.filter((d) => d.working);
  const fullDays = working.filter((d) => d.full).length;
  const openDays = working.filter((d) => d.open).map((d) => d.index);
  const totalMinutes = booked.reduce((sum, m) => sum + m, 0);
  const targetMinutes = targets.reduce((sum, m) => sum + m, 0);
  const logged = `${hoursNumber(totalMinutes)} of ${hoursNumber(targetMinutes)} h`;
  let view;
  if (submitted) {
    const hours = hoursNumber(totalMinutes);
    view = {
      state: "submitted",
      title: `Week ${weekNumber} submitted ✓`,
      cta: "View week →",
      headline: "Week submitted",
      subline: `${hours} ${hours === "1" ? "hour" : "hours"} logged. Enjoy the weekend.`,
    };
  } else if (openDays.length) {
    const names = openDayNames(openDays);
    view = {
      state: "open",
      title: `${names} still open`,
      cta: "Catch up →",
      headline: `Let's catch up on ${names}`,
      subline: `Catching up takes a minute. ${logged} logged so far.`,
    };
  } else if (working.length && fullDays === working.length) {
    const verb = working.length === 1 ? "day is" : "days are";
    view = {
      state: "full",
      title: "Full week done!",
      cta: "Submit week →",
      headline: "Your week is full. Ready to submit?",
      subline: `All ${NUMBER_WORDS[working.length]} ${verb} in. One tap to submit.`,
    };
  } else {
    const nextUp = working.find((d) => !d.full);
    let subline = `${logged} logged.`;
    if (nextUp) subline += ` Next up: ${WEEKDAYS[nextUp.index]}.`;
    if (fullDays) {
      const count = capitalised(NUMBER_WORDS[fullDays]);
      const noun = fullDays === 1 ? "day" : "days";
      view = {
        state: "partial",
        title: `${count} ${noun} done!`,
        cta: "Keep going →",
        headline: `${count} ${noun} done, ${working.length - fullDays} to go`,
        subline,
      };
    } else {
      view = {
        state: "fresh",
        title: "Fresh week, let's go",
        cta: "Keep going →",
        headline: "Let's fill in your week",
        subline,
      };
    }
  }
  return {
    ...view,
    days,
    fullDays,
    workingDays: working.length,
    openDays,
    totalMinutes,
    targetMinutes,
  };
}

// ------------------------------------------------------------------ lines and cards

/** The names of the API tokens a line's time of `day` (0 = Monday) was booked through. */
export function viaOnDay(line, day) {
  const names = new Set();
  for (const marks of Object.values(line.via ?? {})) {
    if (marks[day]) names.add(marks[day]);
  }
  return [...names];
}

/** Minutes of a line on one weekday (all its tasks). */
export function lineDayMinutes(minutes, day) {
  return Object.values(minutes).reduce((sum, week) => sum + week[day], 0);
}

/** Minutes of a line over the week. */
export function lineWeekMinutes(minutes) {
  return Object.values(minutes).reduce((sum, week) => sum + week.reduce((a, b) => a + b, 0), 0);
}

/** Minutes of one task over the week. */
export function taskWeekMinutes(minutes, task) {
  return (minutes[task] ?? [0, 0, 0, 0, 0]).reduce((a, b) => a + b, 0);
}

/**
 * The choices of a line's picker, in order (TS-6): a project's Running tasks, then its next
 * Planned task, then General; tasks with time this week are always there. Categories keep the
 * profile's order.
 */
export function pickerChoices(line, minutes = line.minutes) {
  if (line.kind !== "project") return line.choices;
  const worked = (choice) => taskWeekMinutes(minutes, choice.key) > 0;
  const tasks = line.choices.filter((c) => c.key !== "general");
  const general = line.choices.find((c) => c.key === "general");
  const nextPlanned = tasks.find((c) => c.status === "planned");
  const shown = tasks.filter((c) => c.status === "running" || c === nextPlanned || worked(c));
  const done = shown.filter((c) => c.status === "done");
  const rest = shown.filter((c) => c.status !== "done");
  return [...rest, ...(general ? [general] : []), ...done];
}

/** The keys of a line's picker, for the − fallback. */
export function pickerOrder(line, minutes = line.minutes) {
  return pickerChoices(line, minutes).map((c) => c.key);
}

/** The line's colour: cards cycle through the five hues (TS-4). */
export function lineHue(index) {
  return LINE_HUES[index % LINE_HUES.length];
}

/** How full a fill-up card is: logged against planned, 0 to 1 (TS-5). */
export function fillFraction(plannedMinutes, bookedMinutes) {
  if (!plannedMinutes) return 0;
  return Math.min(1, bookedMinutes / plannedMinutes);
}

/** The note on a card (TS-5). */
export function cardNote(line, bookedMinutes) {
  if (line.kind === "time_off") return `${formatHours(bookedMinutes)} this week`;
  const planned = line.planned_minutes;
  if (planned === null || planned === undefined) return "Not planned";
  const rounded = Math.round(planned / 60) * 60;
  if (bookedMinutes === 0) return `${formatHours(rounded)} planned`;
  const difference = Math.round((planned - bookedMinutes) / 60) * 60;
  if (difference > 0) return `${formatHours(difference)} to go`;
  if (difference === 0) return "Right on plan";
  return `${formatHours(-difference)} over plan`;
}

/** Whether a card has reached its planned hours (the ✓ badge). */
export function reachedPlan(line, bookedMinutes) {
  const planned = line.planned_minutes;
  return planned !== null && planned !== undefined && planned > 0 && bookedMinutes >= Math.round(planned / 60) * 60;
}

/** The numbers of the celebration (TS-11): lines with planned hours and how many reached them. */
export function celebration(lines, weekNumber, totalMinutes) {
  const planned = lines.filter((l) => l.planned_minutes && l.kind !== "time_off");
  const chips = planned.map((line) => ({
    key: line.key,
    name: line.name,
    booked: lineWeekMinutes(line.minutes),
    planned: line.planned_minutes,
  }));
  const reached = planned.filter((l) => reachedPlan(l, lineWeekMinutes(l.minutes))).length;
  const hours = hoursNumber(totalMinutes);
  return {
    headline: `Week ${weekNumber} is in`,
    summary: `${hours} ${hours === "1" ? "hour" : "hours"} logged. ${reached} of ${planned.length} lines reached their planned hours.`,
    chips,
    reached,
    lines: planned.length,
  };
}

/** "5 – 9 October 2026" for a week's Monday and Friday. */
export function weekRange(mondayIso, fridayIso) {
  const months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  const [y1, m1, d1] = mondayIso.split("-").map(Number);
  const [y2, m2, d2] = fridayIso.split("-").map(Number);
  if (y1 === y2 && m1 === m2) return `${d1} – ${d2} ${months[m2 - 1]} ${y2}`;
  if (y1 === y2) return `${d1} ${months[m1 - 1]} – ${d2} ${months[m2 - 1]} ${y2}`;
  return `${d1} ${months[m1 - 1]} ${y1} – ${d2} ${months[m2 - 1]} ${y2}`;
}
