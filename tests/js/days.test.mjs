// Unit tests for static/js/lib/days.js: how a People & days cell reads, and what may be typed. [PD-2] [PD-3]
import assert from "node:assert/strict";
import { test } from "node:test";

import { STEP, cellView, parseDays, plannedText, totalView } from "../../momato/static/js/lib/days.js";

test("[PD-2] planned days read '12 d' or a dash", () => {
  assert.equal(plannedText(12), "12 d");
  assert.equal(plannedText(12.5), "12.5 d");
  assert.equal(plannedText(0), "–");
});

test("[PD-2] a cell: planned, bar of logged against planned, and the line under it", () => {
  assert.deepEqual(cellView({ planned: 12, logged: 6, upcoming: false }), {
    text: "12 d", percent: 50, over: false, sub: "6 logged",
  });
  assert.deepEqual(cellView({ planned: 10, logged: 12.5, upcoming: false }), {
    text: "10 d", percent: 100, over: true, sub: "12.5 logged",
  });
  assert.deepEqual(cellView({ planned: 8, logged: 0, upcoming: true }), {
    text: "8 d", percent: 0, over: false, sub: "upcoming",
  });
  assert.deepEqual(cellView({ planned: 8, logged: 0, upcoming: false }), {
    text: "8 d", percent: 0, over: false, sub: "0 logged",
  });
  assert.deepEqual(cellView({ planned: 0, logged: 0, upcoming: false }), {
    text: "–", percent: 0, over: false, sub: "",
  });
  assert.deepEqual(cellView({ planned: 0, logged: 3, upcoming: false }), {
    text: "–", percent: 100, over: true, sub: "3 logged",
  });
});

test("[PD-2] the total column", () => {
  assert.deepEqual(totalView(23, 11.5), { text: "23 d", sub: "11.5 logged" });
  assert.deepEqual(totalView(0, 0), { text: "–", sub: "0 logged" });
});

test("[PD-3] typed days go in steps of 0.5 from 0 to the quarter's working days", () => {
  assert.equal(STEP, 0.5);
  assert.deepEqual(parseDays("12", 65), { value: 12 });
  assert.deepEqual(parseDays(" 12,5 ", 65), { value: 12.5 });
  assert.deepEqual(parseDays("0", 65), { value: 0 });
  assert.deepEqual(parseDays("", 65), { value: 0 }); // empty clears the cell
  assert.deepEqual(parseDays("65", 65), { value: 65 });
  assert.ok(parseDays("65.5", 65).error.includes("65 working days"));
  assert.ok(parseDays("12.3", 65).error.includes("0.5"));
  assert.ok(parseDays("abc", 65).error);
  assert.ok(parseDays("-1", 65).error);
  assert.ok(parseDays("1e2", 65).error);
});
