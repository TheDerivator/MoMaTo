// Unit tests for static/js/lib/admin.js: sections, scopes, work patterns, sign-in names, audit words.
// [ADM-1] [ADM-2] [ADM-4] [ADM-5] [ADM-6]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  actionLabel, adminSections, canSetUpOrganisation, chosenSection, daysText, detailsText,
  hoursField, minutesFromText, parseScope, patternFromTexts, patternSummary, scopeOptions,
  scopeValue, suggestUsername,
} from "../../momato/static/js/lib/admin.js";
import { buildTree } from "../../momato/static/js/lib/tree.js";

const nobody = { everywhere: false, node_ids: [] };
const everywhere = { everywhere: true, node_ids: [] };
const rights = (org, users) => ({
  "org.manage": org ? everywhere : nobody,
  "users.manage": users ? everywhere : nobody,
});

test("[ADM-1] only org.manage held everywhere may name the organisation on a fresh installation", () => {
  assert.equal(canSetUpOrganisation(rights(true, false)), true);
  assert.equal(canSetUpOrganisation(rights(false, true)), false);
  assert.equal(canSetUpOrganisation({}), false);
  assert.equal(canSetUpOrganisation({ "org.manage": { everywhere: false, node_ids: [3] } }), false);
});

test("[ADM-1] [ADM-5] sections follow the two administration rights", () => {
  assert.deepEqual(adminSections(rights(false, false)), []);
  assert.deepEqual(adminSections(rights(true, false)).map((s) => s.key), ["org", "people"]);
  assert.deepEqual(adminSections(rights(false, true)).map((s) => s.key), ["people", "roles", "access", "sso", "audit"]);
  assert.deepEqual(adminSections(rights(true, true)).map((s) => s.key), ["org", "people", "roles", "access", "sso", "audit"]);
  // a right held only in a branch is not an administration right
  assert.deepEqual(adminSections({ "org.manage": { everywhere: false, node_ids: [3] } }), []);
});

test("the section shown is the one asked for when allowed, else the first", () => {
  const sections = adminSections(rights(true, true));
  assert.equal(chosenSection(sections, "audit").key, "audit");
  assert.equal(chosenSection(sections, "nope").key, "org");
  assert.equal(chosenSection(sections, null).key, "org");
  assert.equal(chosenSection([], "audit"), null);
});

const tree = buildTree([
  { id: 1, parent_id: null, name: "Brightwater", position: 0, is_department: false },
  { id: 2, parent_id: 1, name: "STL", position: 0, is_department: true },
  { id: 3, parent_id: 2, name: "Quality", position: 0, is_department: false },
  { id: 4, parent_id: 1, name: "R&D", position: 1, is_department: true },
]);

test("[ADM-5] scope choices: everywhere, own department, then every branch below the root", () => {
  assert.deepEqual(scopeOptions(tree), [
    { value: "global", label: "Everywhere" },
    { value: "own_department", label: "Own department" },
    { value: "node:2", label: "STL" },
    { value: "node:3", label: "STL › Quality" },
    { value: "node:4", label: "R&D" },
  ]);
});

test("a scope is one select value and back", () => {
  assert.equal(scopeValue("global", null), "global");
  assert.equal(scopeValue("own_department", null), "own_department");
  assert.equal(scopeValue("node", 7), "node:7");
  assert.deepEqual(parseScope("node:7"), { scope_kind: "node", node_id: 7 });
  assert.deepEqual(parseScope("global"), { scope_kind: "global", node_id: null });
  assert.deepEqual(parseScope("own_department"), { scope_kind: "own_department", node_id: null });
});

test("[ADM-2] durations are typed as hours, decimals or h:mm", () => {
  assert.equal(minutesFromText("8"), 480);
  assert.equal(minutesFromText("7.5"), 450);
  assert.equal(minutesFromText("7,5"), 450);
  assert.equal(minutesFromText("7:30"), 450);
  assert.equal(minutesFromText(" 0 "), 0);
  assert.equal(minutesFromText("12"), 720);
  for (const bad of ["", "abc", "13", "-1", "7:75", "1.234", "8h"]) assert.equal(minutesFromText(bad), null, bad);
  assert.equal(hoursField(450), "7.5");
  assert.equal(hoursField(480), "8");
});

test("[ADM-2] a work pattern needs five valid days", () => {
  assert.deepEqual(patternFromTexts(["8", "8", "8", "8", "4"]), [480, 480, 480, 480, 240]);
  assert.equal(patternFromTexts(["8", "8", "8", "8", "x"]), null);
});

test("[ADM-2] the pattern summary says the week and the days that differ", () => {
  assert.equal(patternSummary([480, 480, 480, 480, 480]), "40 h a week (8 h a day)");
  assert.equal(patternSummary([480, 480, 480, 480, 0]), "32 h a week (Mon 8, Tue 8, Wed 8, Thu 8, Fri 0)");
  assert.equal(patternSummary([0, 0, 0, 0, 0]), "0 h a week");
  assert.equal(patternSummary([450, 450, 450, 450, 450]), "37.5 h a week (7.5 h a day)");
});

test("[ADM-4] days show without trailing noise", () => {
  assert.equal(daysText(220), "220");
  assert.equal(daysText(176.0), "176");
  assert.equal(daysText(188.456), "188.46");
});

test("sign-in names are suggested like the server does", () => {
  assert.equal(suggestUsername("Chloé Martens"), "chloe.martens");
  assert.equal(suggestUsername("Tomás Rivera"), "tomas.rivera");
  assert.equal(suggestUsername("Søren Æbelø"), "soren.aebelo");
  assert.equal(suggestUsername("Anke  De-Smet "), "anke.de.smet");
  assert.equal(suggestUsername("???"), "user");
});

test("[ADM-6] actions read as words, unknown ones are made readable", () => {
  assert.equal(actionLabel("user.role_granted"), "Role granted");
  assert.equal(actionLabel("auth.login"), "Signed in");
  assert.equal(actionLabel("user.created"), "Account created");
  assert.equal(actionLabel("plan.moved_away"), "Plan moved away");
});

test("[ADM-6] details are one line", () => {
  assert.equal(detailsText({ role: "admin", scope: "global" }), "role: admin · scope: global");
  assert.equal(detailsText({ work_minutes: [480, 480] }), "work minutes: [480,480]");
  assert.equal(detailsText(null), "");
  assert.equal(detailsText({}), "");
});
