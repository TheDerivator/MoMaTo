// Unit tests for static/js/lib/timesheet.js against tests/fixtures/booking.json and
// week_states.json (the same tables the Python domain passes). [R4.8] [R4.9] [TS-5] [TS-6] [TS-11]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  LINE_HUES, addStep, cardNote, cellKey, celebration, fillFraction, lineDayMinutes, lineHue,
  lineWeekMinutes, viaOnDay, pickerChoices, pickerOrder, reachedPlan, removeStep, taskWeekMinutes,
  weekRange, weekView,
} from "../../momato/static/js/lib/timesheet.js";

const booking = JSON.parse(readFileSync(new URL("../fixtures/booking.json", import.meta.url)));
const states = JSON.parse(readFileSync(new URL("../fixtures/week_states.json", import.meta.url)));

test("[R4.8] booking cases from the shared table", () => {
  for (const c of booking.cases) {
    const step = c.step ?? 60;
    const cap = c.cap ?? 600;
    const result =
      c.op === "add"
        ? addStep(c.day, c.line, c.task, { step, cap })
        : removeStep(c.day, c.line, c.task, { step, picker: c.picker });
    assert.deepEqual(result.day, c.expect_day, c.name);
    assert.equal(result.changed, c.changed, c.name);
  }
});

test("[R4.9] week states from the shared table", () => {
  for (const c of states.cases) {
    const view = weekView(c.targets, c.booked, {
      todayIndex: c.today_index,
      submitted: c.submitted,
      weekNumber: c.week_number,
    });
    assert.equal(view.state, c.state, c.name);
    assert.equal(view.fullDays, c.full_days, c.name);
    assert.deepEqual(view.openDays, c.open_days, c.name);
    assert.equal(view.title, c.title, c.name);
    assert.equal(view.cta, c.cta, c.name);
    assert.equal(view.headline, c.headline, c.name);
    assert.equal(view.subline, c.subline, c.name);
    assert.deepEqual(view.days.map((d) => d.tag), c.tags, c.name);
  }
});

test("a cell key joins the line and the task", () => {
  assert.equal(cellKey("project:4102", "task:12"), "project:4102:task:12");
});

// ---- picker, notes, fills

const PROJECT = {
  key: "project:4102",
  kind: "project",
  planned_minutes: 840,
  choices: [
    { key: "task:1", name: "Study", status: "done", position: 0 },
    { key: "task:2", name: "Offers", status: "done", position: 1 },
    { key: "task:3", name: "Installation", status: "running", position: 2 },
    { key: "task:4", name: "Commissioning", status: "planned", position: 3 },
    { key: "task:5", name: "Handover", status: "planned", position: 4 },
    { key: "general", name: "General", status: null, position: 10000 },
  ],
  minutes: { "task:3": [180, 240, 0, 0, 0] },
};

test("[TS-6] the picker: running tasks, the next planned one, then General", () => {
  assert.deepEqual(pickerOrder(PROJECT), ["task:3", "task:4", "general"]);
});

test("[TS-6] a task with time this week is always listed", () => {
  const withDone = { ...PROJECT, minutes: { ...PROJECT.minutes, "task:1": [0, 60, 0, 0, 0] } };
  assert.deepEqual(pickerOrder(withDone), ["task:3", "task:4", "general", "task:1"]);
  const withLaterTask = { ...PROJECT, minutes: { "task:5": [60, 0, 0, 0, 0] } };
  assert.deepEqual(pickerOrder(withLaterTask), ["task:3", "task:4", "task:5", "general"]);
});

test("[TS-6] categories keep the profile's order", () => {
  const other = {
    key: "other_work",
    kind: "other_work",
    choices: [{ key: "meetings" }, { key: "training" }, { key: "admin" }],
    minutes: {},
  };
  assert.deepEqual(pickerOrder(other), ["meetings", "training", "admin"]);
  assert.deepEqual(pickerChoices(other), other.choices);
});

test("[TS-5] the note of a card", () => {
  const planned = { kind: "project", planned_minutes: 840 };
  assert.equal(cardNote(planned, 0), "14 h planned");
  assert.equal(cardNote(planned, 420), "7 h to go");
  assert.equal(cardNote(planned, 840), "Right on plan");
  assert.equal(cardNote(planned, 1020), "3 h over plan");
  assert.equal(cardNote({ kind: "project", planned_minutes: null }, 120), "Not planned");
  assert.equal(cardNote({ kind: "time_off", planned_minutes: null }, 480), "8 h this week");
  assert.equal(cardNote({ kind: "project", planned_minutes: 836.36 }, 0), "14 h planned");
});

test("[TS-5] fill and the reached badge", () => {
  assert.equal(fillFraction(840, 420), 0.5);
  assert.equal(fillFraction(840, 1200), 1);
  assert.equal(fillFraction(null, 60), 0);
  assert.equal(fillFraction(0, 60), 0);
  assert.equal(reachedPlan({ planned_minutes: 840 }, 840), true);
  assert.equal(reachedPlan({ planned_minutes: 836.36 }, 840), true); // planned hours are rounded
  assert.equal(reachedPlan({ planned_minutes: 840 }, 780), false);
  assert.equal(reachedPlan({ planned_minutes: null }, 780), false);
});

test("sums over a line", () => {
  assert.equal(lineDayMinutes(PROJECT.minutes, 1), 240);
  assert.equal(lineWeekMinutes(PROJECT.minutes), 420);
  assert.equal(taskWeekMinutes(PROJECT.minutes, "task:3"), 420);
  assert.equal(taskWeekMinutes(PROJECT.minutes, "task:9"), 0);
});

test("[TS-4] colours cycle through the five hues", () => {
  assert.deepEqual(LINE_HUES, [285, 155, 235, 60, 330]);
  assert.equal(lineHue(0), 285);
  assert.equal(lineHue(5), 285);
  assert.equal(lineHue(7), 235);
});

test("[TS-11] the celebration counts lines with planned hours", () => {
  const lines = [
    { key: "a", name: "A", kind: "project", planned_minutes: 480, minutes: { x: [480, 0, 0, 0, 0] } },
    { key: "b", name: "B", kind: "project", planned_minutes: 480, minutes: { x: [240, 0, 0, 0, 0] } },
    { key: "c", name: "C", kind: "project", planned_minutes: null, minutes: { x: [60, 0, 0, 0, 0] } },
    { key: "off", name: "Time off", kind: "time_off", planned_minutes: null, minutes: {} },
  ];
  const result = celebration(lines, 41, 2400);
  assert.equal(result.headline, "Week 41 is in");
  assert.equal(result.summary, "40 hours logged. 1 of 2 lines reached their planned hours.");
  assert.deepEqual(result.chips.map((c) => [c.key, c.booked, c.planned]), [["a", 480, 480], ["b", 240, 480]]);
  assert.equal(celebration(lines, 41, 60).summary, "1 hour logged. 1 of 2 lines reached their planned hours.");
});

test("a week's range reads like the design", () => {
  assert.equal(weekRange("2026-10-05", "2026-10-09"), "5 – 9 October 2026");
  assert.equal(weekRange("2026-09-28", "2026-10-02"), "28 September – 2 October 2026");
  assert.equal(weekRange("2026-12-28", "2027-01-01"), "28 December 2026 – 1 January 2027");
});

test("[TOK-3] a card names the tokens that booked a day", () => {
  const line = {
    via: {
      "task:1": [null, "Claude Code", null, null, null],
      "task:2": [null, "Claude Code", "Script", null, null],
    },
  };
  assert.deepEqual(viaOnDay(line, 1), ["Claude Code"]);
  assert.deepEqual(viaOnDay(line, 2), ["Script"]);
  assert.deepEqual(viaOnDay(line, 0), []);
  assert.deepEqual(viaOnDay({}, 0), []);
});
