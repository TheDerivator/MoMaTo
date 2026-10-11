// Unit tests for static/js/lib/gantt.js against tests/fixtures/task_status.json, plus the geometry
// of the quarter axis on hand-computed cases. [PG-1] [PG-2] [PG-3] [PG-5] [R4.6]
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  MIN_BAR_WIDTH, STATUS_HUES, axisFor, effectiveEnd, isSlipped, place, quarterLabel, quarterStart,
  quarterWidth, quartersBetween, statusText, taskDateProblem, taskRow, taskStatus, taskSubline,
  timelinePercent, timelineText, todayPlace,
} from "../../momato/static/js/lib/gantt.js";

const table = JSON.parse(readFileSync(new URL("../fixtures/task_status.json", import.meta.url)));
const TODAY = "2026-10-08";

test("[R4.6] task status from the shared table", () => {
  for (const row of table.status) {
    assert.equal(taskStatus(row.progress, row.planned_start, row.today), row.status, JSON.stringify(row));
  }
});

test("[R4.6] slipped and effective end from the shared table", () => {
  for (const row of table.slipped) {
    assert.equal(isSlipped(row.planned_end, row.revised_end), row.slipped, JSON.stringify(row));
    assert.equal(effectiveEnd(row.planned_end, row.revised_end), row.effective_end);
  }
});

test("[R4.6] status text and timeline text from the shared table", () => {
  for (const row of table.status_text) assert.equal(statusText(row.status, row.progress), row.text);
  for (const row of table.timeline) {
    assert.equal(timelineText(row.start, row.end, row.today), row.text, JSON.stringify(row));
  }
  assert.equal(timelinePercent("2026-01-01", "2026-01-01", "2026-01-01"), 100);
});

test("[PG-5] dates must make sense", () => {
  assert.equal(taskDateProblem("2026-10-01", "2026-10-31", null), "");
  assert.equal(taskDateProblem("2026-10-01", "2026-10-01", null), "");
  assert.ok(taskDateProblem("2026-10-02", "2026-10-01", null));
  assert.ok(taskDateProblem("2026-10-01", "2026-10-31", "2026-10-31"));
  assert.ok(taskDateProblem("2026-10-01", "2026-10-31", "2026-10-15"));
  assert.equal(taskDateProblem("2026-10-01", "2026-10-31", "2026-11-15"), "");
  assert.ok(taskDateProblem("", "2026-10-31", null));
});

test("[PG-1] quarters and their labels", () => {
  assert.equal(quarterStart("2026-11-17"), "2026-10-01");
  assert.equal(quarterStart("2026-01-01"), "2026-01-01");
  assert.equal(quarterStart("2026-03-31"), "2026-01-01");
  assert.equal(quarterLabel("2026-10-01"), "Q4/26");
  assert.equal(quarterLabel("2027-01-01"), "Q1/27");
  assert.deepEqual(quartersBetween("2026-11-15", "2027-02-10"), ["2026-10-01", "2027-01-01"]);
  assert.deepEqual(quartersBetween("2026-10-01", "2026-12-31"), ["2026-10-01"]);
});

test("[PG-1] a project across a year boundary has the quarters it touches", () => {
  const project = { start_date: "2025-11-03", end_date: "2027-03-31" };
  const axis = axisFor(project, []);
  assert.deepEqual(axis.quarters, [
    "2025-10-01", "2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01", "2027-01-01",
  ]);
  assert.equal(axis.start, "2025-10-01");
  assert.equal(axis.end, "2027-04-01");
  assert.equal(quarterWidth(axis), 100 / 6);
});

test("[PG-1] a task beyond the project end widens the axis", () => {
  const project = { start_date: "2026-10-01", end_date: "2026-12-18" };
  const tasks = [
    { planned_start: "2026-10-05", planned_end: "2026-12-11", revised_end: "2027-02-12" },
    { planned_start: "2026-09-14", planned_end: "2026-09-30", revised_end: null },
  ];
  const axis = axisFor(project, tasks);
  assert.deepEqual(axis.quarters, ["2026-07-01", "2026-10-01", "2027-01-01"]);
});

test("positions are percentages of the axis, clamped", () => {
  const axis = { quarters: ["2026-01-01", "2026-04-01"], start: "2026-01-01", end: "2026-07-01" };
  assert.equal(place("2026-01-01", axis), 0);
  assert.equal(place("2025-06-01", axis), 0);
  assert.equal(place("2026-07-01", axis), 100);
  assert.equal(place("2027-01-01", axis), 100);
  const april = place("2026-04-01", axis); // 90 of 181 days
  assert.ok(Math.abs(april - (90 / 181) * 100) < 1e-9);
});

test("[PG-1] today's line is drawn only when today is on the axis", () => {
  const axis = { quarters: ["2026-10-01"], start: "2026-10-01", end: "2027-01-01" };
  assert.ok(todayPlace("2026-10-08", axis) > 0);
  assert.equal(todayPlace("2026-09-30", axis), null);
  assert.equal(todayPlace("2027-01-01", axis), null);
  assert.equal(todayPlace("2026-10-01", axis), 0);
});

test("[PG-2][PG-3] bar geometry of a running, a done and a planned task", () => {
  const axis = { quarters: ["2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"], start: "2026-01-01", end: "2027-01-01" };
  const running = taskRow(
    { planned_start: "2026-04-01", planned_end: "2026-06-30", revised_end: null, is_milestone: false, progress: 40 },
    axis, TODAY,
  );
  assert.equal(running.status, "running");
  assert.equal(running.hue, STATUS_HUES.running);
  assert.ok(Math.abs(running.bar.left - (90 / 365) * 100) < 1e-9);
  assert.ok(Math.abs(running.bar.width - (90 / 365) * 100) < 1e-9);
  assert.equal(running.filled, 40);
  assert.equal(running.extension, null);
  assert.equal(running.milestone, null);

  const done = taskRow(
    { planned_start: "2026-01-05", planned_end: "2026-02-27", revised_end: null, is_milestone: false, progress: 100 },
    axis, TODAY,
  );
  assert.equal(done.status, "done");
  assert.equal(done.hue, 155);

  const planned = taskRow(
    { planned_start: "2026-11-02", planned_end: "2026-12-18", revised_end: null, is_milestone: false, progress: 0 },
    axis, TODAY,
  );
  assert.equal(planned.status, "planned");
  assert.equal(planned.hue, 235);
});

test("[PG-2] a slipped task gets a dashed extension and is filled against the revised length", () => {
  const axis = { quarters: ["2026-01-01"], start: "2026-01-01", end: "2026-04-01" }; // 90 days
  const row = taskRow(
    { planned_start: "2026-01-01", planned_end: "2026-01-31", revised_end: "2026-03-02", is_milestone: false, progress: 50 },
    axis, TODAY,
  );
  assert.ok(row.extension);
  assert.ok(Math.abs(row.extension.left - (row.bar.left + row.bar.width)) < 1e-9); // starts where the bar ends
  assert.ok(Math.abs(row.extension.width - (30 / 90) * 100) < 1e-9); // 30 more days of 90
  // 50 % of a 60-day revised span is 30 days; the planned bar is 30 days long, so it is full.
  assert.equal(row.filled, 100);
  assert.ok(row.subline.endsWith("· slipped"));
});

test("[PG-2] a slipped milestone sits at the revised end", () => {
  const axis = { quarters: ["2026-10-01"], start: "2026-10-01", end: "2027-01-01" };
  const planned = taskRow(
    { planned_start: "2026-11-01", planned_end: "2026-11-30", revised_end: null, is_milestone: true, progress: 0 },
    axis, TODAY,
  );
  const slipped = taskRow(
    { planned_start: "2026-11-01", planned_end: "2026-11-30", revised_end: "2026-12-15", is_milestone: true, progress: 0 },
    axis, TODAY,
  );
  assert.ok(Math.abs(planned.milestone - place("2026-11-30", axis)) < 1e-9);
  assert.ok(Math.abs(slipped.milestone - place("2026-12-15", axis)) < 1e-9);
  assert.ok(slipped.milestone > planned.milestone);
});

test("a one-day task keeps a visible bar and does not divide by zero", () => {
  const axis = { quarters: ["2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"], start: "2026-01-01", end: "2027-01-01" };
  const row = taskRow(
    { planned_start: "2026-05-05", planned_end: "2026-05-05", revised_end: "2026-05-20", is_milestone: false, progress: 10 },
    axis, TODAY,
  );
  assert.equal(row.bar.width, MIN_BAR_WIDTH);
  assert.ok(Number.isFinite(row.filled) && row.filled <= 100);
});

test("[PG-2] the line under a task's name", () => {
  const base = { planned_start: "2026-01-05", planned_end: "2026-03-20", revised_end: null, progress: 45 };
  assert.equal(taskSubline(base, TODAY), "5 Jan – 20 Mar · Running");
  assert.equal(taskSubline({ ...base, progress: 100 }, TODAY), "5 Jan – 20 Mar · Done");
  assert.equal(taskSubline({ ...base, revised_end: "2026-04-10" }, TODAY), "5 Jan – 10 Apr · Running · slipped");
  assert.equal(taskSubline({ ...base, planned_start: "2026-11-01", planned_end: "2026-11-30", progress: 0 }, TODAY), "1 Nov – 30 Nov · Planned");
});
