// Unit tests for static/js/lib/plans.js: branches, rights, wording and meters of action plans.
// [AP-2] [AP-3] [AP-4] [AP-5] [AP-7]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PLAN_HUES, changeText, chosenPlan, departmentsText, meter, meterText, metaLine, plansInBranch,
  reachCovers, reachableNodes, statusDots, windowMonths, windowYears,
} from "../../momato/static/js/lib/plans.js";
import { buildTree } from "../../momato/static/js/lib/tree.js";

const org = [
  { id: 1, parent_id: null, name: "Brightwater", position: 0, is_department: false },
  { id: 2, parent_id: 1, name: "STL", position: 0, is_department: true },
  { id: 3, parent_id: 1, name: "R&D", position: 1, is_department: true },
  { id: 4, parent_id: 2, name: "Quality", position: 0, is_department: false },
  { id: 5, parent_id: 3, name: "Coatings", position: 0, is_department: false },
];
const tree = buildTree(org);
const PLANS = [
  { id: 10, name: "Digital plant", owner_org_node_id: 4 },
  { id: 11, name: "Zero defects", owner_org_node_id: 5 },
  { id: 12, name: "Energy", owner_org_node_id: 2 },
];

test("[AP-2] a branch shows the plans owned inside it", () => {
  assert.deepEqual(plansInBranch(PLANS, tree, null).map((p) => p.id), [10, 11, 12]);
  assert.deepEqual(plansInBranch(PLANS, tree, 2).map((p) => p.id), [10, 12]);
  assert.deepEqual(plansInBranch(PLANS, tree, 4).map((p) => p.id), [10]);
  assert.deepEqual(plansInBranch(PLANS, tree, 3).map((p) => p.id), [11]);
  assert.deepEqual(plansInBranch([], tree, 2), []);
});

test("the plan shown is the one asked for when the branch has it, else the first", () => {
  const visible = plansInBranch(PLANS, tree, 2);
  assert.equal(chosenPlan(visible, 12).id, 12);
  assert.equal(chosenPlan(visible, 11).id, 10);
  assert.equal(chosenPlan(visible, null).id, 10);
  assert.equal(chosenPlan([], 10), null);
});

test("rights reach a node when everywhere or when a branch above it is covered", () => {
  assert.equal(reachCovers({ everywhere: true, node_ids: [] }, tree, 5), true);
  assert.equal(reachCovers({ everywhere: false, node_ids: [2] }, tree, 4), true);
  assert.equal(reachCovers({ everywhere: false, node_ids: [2] }, tree, 2), true);
  assert.equal(reachCovers({ everywhere: false, node_ids: [2] }, tree, 5), false);
  assert.equal(reachCovers({ everywhere: false, node_ids: [] }, tree, 4), false);
  assert.equal(reachCovers({ everywhere: false, node_ids: [2] }, tree, 999), false);
});

test("the nodes a reach covers, root first", () => {
  assert.deepEqual(reachableNodes({ everywhere: true, node_ids: [] }, tree).map((n) => n.id), [1, 2, 4, 3, 5]);
  assert.deepEqual(reachableNodes({ everywhere: false, node_ids: [2] }, tree).map((n) => n.id), [2, 4]);
  assert.deepEqual(reachableNodes({ everywhere: false, node_ids: [] }, tree), []);
});

test("[AP-3] the meta line", () => {
  const overview = { owner_name: "Quality", coordinator: { name: "Anna Claes" }, department_count: 3 };
  assert.deepEqual(metaLine(overview, ["STL", "Quality"]), {
    owner: "STL › Quality",
    rest: "coordinated by Anna Claes · includes projects from 3 departments",
  });
  assert.equal(metaLine(overview, []).owner, "Quality");
  assert.equal(departmentsText(1), "includes projects from 1 department");
  assert.equal(departmentsText(0), "includes no projects yet");
});

test("[AP-4] meters are clamped percentages and read 'logged / planned d'", () => {
  assert.deepEqual(meter({ logged_percent: 42.5, expected_percent: 60 }), { logged: 42.5, expected: 60 });
  assert.deepEqual(meter({ logged_percent: 140, expected_percent: -3 }), { logged: 100, expected: 0 });
  assert.equal(meterText({ logged: 12.04, planned: 20 }), "12 / 20 d");
  assert.equal(meterText({ logged: 12.25, planned: 20.5 }), "12.3 / 20.5 d");
});

test("[AP-5] the timeline window covers whole years and months", () => {
  const window = { start: "2025-01-01", end: "2027-12-31" };
  assert.deepEqual(windowYears(window), [2025, 2026, 2027]);
  assert.equal(windowMonths(window), 36);
});

test("[AP-5] a group's status dots follow the status order and are limited", () => {
  const order = ["progress", "hold", "finished"];
  assert.deepEqual(statusDots({ finished: 1, progress: 2 }, order), ["progress", "progress", "finished"]);
  assert.equal(statusDots({ progress: 20 }, order).length, 8);
  assert.deepEqual(statusDots({}, order), []);
});

test("[AP-6] a logbook item says what changed", () => {
  assert.equal(changeText({ field: "Status" }), "changed status");
  assert.equal(changeText({}), "changed ");
});

test("the palette is fixed", () => {
  assert.ok(PLAN_HUES.length >= 5);
  assert.ok(PLAN_HUES.every((h) => Number.isInteger(h) && h >= 0 && h < 360));
});
