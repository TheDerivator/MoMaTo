// Unit tests for static/js/lib/fields.js: every detail field type shows and parses back. [DT-2] [DT-3]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_TAGS, MAX_TEXT, displayValue, editorKind, editorText, isEmpty, parseInput, parseTags,
  referencedProjects, sameValue,
} from "../../momato/static/js/lib/fields.js";

const field = (type, label = "Field") => ({ key: "f", label, type });
const LOOKUP = {
  people: new Map([[7, { name: "Anna Claes" }]]),
  projects: new Map([[4102, { name: "Sensor retrofit" }]]),
};

test("every type has an editor", () => {
  const kinds = {
    text: "text", long_text: "textarea", number: "number", date: "date", choice: "choice",
    tags: "tags", person: "person", project: "project", yes_no: "yesno",
  };
  for (const [type, kind] of Object.entries(kinds)) assert.equal(editorKind(field(type)), kind, type);
  assert.equal(editorKind({ key: "number", core: "number", type: null }), "text");
});

test("values are shown as the design shows them", () => {
  assert.equal(displayValue(field("text"), "ERP-4410"), "ERP-4410");
  assert.equal(displayValue(field("number"), 12.5), "12.5");
  assert.equal(displayValue(field("date"), "2026-03-02"), "2 Mar 2026");
  assert.equal(displayValue(field("tags"), ["a", "b"]), "a, b");
  assert.equal(displayValue(field("yes_no"), true), "Yes");
  assert.equal(displayValue(field("yes_no"), false), "No");
  assert.equal(displayValue(field("person"), 7, LOOKUP), "Anna Claes");
  assert.equal(displayValue(field("person"), 99, LOOKUP), "Person 99");
  assert.equal(displayValue(field("project"), 4102, LOOKUP), "#4102 Sensor retrofit");
  assert.equal(displayValue(field("project"), 5000, LOOKUP), "#5000");
  assert.equal(displayValue(field("choice"), "Cost saving"), "Cost saving");
  assert.equal(displayValue(field("text"), null), "");
  assert.equal(displayValue(field("tags"), []), "");
  assert.equal(displayValue(field("yes_no"), null), "");
});

test("typed text becomes the value the server accepts", () => {
  assert.deepEqual(parseInput(field("text"), "  hello "), { value: "hello" });
  assert.deepEqual(parseInput(field("text"), "   "), { value: null });
  assert.ok(parseInput(field("text", "Sponsor"), "x".repeat(MAX_TEXT + 1)).error.includes("Sponsor"));
  assert.ok(parseInput(field("long_text", "Notes"), "x".repeat(10_001)).error);
  assert.deepEqual(parseInput(field("long_text"), "line\nbreak"), { value: "line\nbreak" });
  assert.deepEqual(parseInput(field("number"), "12,5"), { value: 12.5 });
  assert.deepEqual(parseInput(field("number"), "0"), { value: 0 });
  assert.ok(parseInput(field("number"), "abc").error);
  assert.deepEqual(parseInput(field("date"), "2026-10-08"), { value: "2026-10-08" });
  assert.ok(parseInput(field("date"), "8/10/2026").error);
  assert.deepEqual(parseInput(field("tags"), "a, B ,a,, c"), { value: ["a", "B", "c"] });
  assert.deepEqual(parseInput(field("tags"), ""), { value: null });
  assert.deepEqual(parseInput(field("tags"), ["x", "y"]), { value: ["x", "y"] });
  assert.ok(parseInput(field("tags"), Array.from({ length: MAX_TAGS + 1 }, (_, i) => `t${i}`).join(",")).error);
  assert.ok(parseInput(field("tags"), "x".repeat(51)).error);
  assert.deepEqual(parseInput(field("choice"), "Cost saving"), { value: "Cost saving" });
  assert.deepEqual(parseInput(field("person"), 7), { value: 7 });
  assert.deepEqual(parseInput(field("yes_no"), false), { value: false });
  assert.deepEqual(parseInput(field("project"), null), { value: null });
});

test("a value shown in an editor parses back to itself", () => {
  const cases = [
    [field("text"), "ERP-4410"],
    [field("long_text"), "one\ntwo"],
    [field("number"), 12.5],
    [field("date"), "2026-03-02"],
    [field("tags"), ["a", "b c"]],
    [field("choice"), "Cost saving"],
  ];
  for (const [f, value] of cases) {
    assert.deepEqual(parseInput(f, editorText(f, value)), { value }, f.type);
  }
  assert.equal(editorText(field("text"), null), "");
});

test("tags are trimmed and unique ignoring case", () => {
  assert.deepEqual(parseTags(" a , A,b"), ["a", "b"]);
  assert.deepEqual(parseTags(""), []);
});

test("an unchanged value sends nothing", () => {
  assert.equal(sameValue(null, ""), true);
  assert.equal(sameValue(undefined, []), true);
  assert.equal(sameValue("a", "a"), true);
  assert.equal(sameValue(["a", "b"], ["a", "b"]), true);
  assert.equal(sameValue(["a"], ["a", "b"]), false);
  assert.equal(sameValue(["a", "b"], ["a", "c"]), false);
  assert.equal(sameValue(0, null), false);
  assert.equal(sameValue(false, null), false);
  assert.equal(isEmpty(0), false);
  assert.equal(isEmpty(false), false);
});

test("the projects a card refers to", () => {
  const cards = [
    { fields: [{ key: "original", type: "project" }, { key: "erp", type: "text" }] },
    { fields: [{ key: "parent", type: "project" }] },
  ];
  assert.deepEqual(referencedProjects(cards, { original: 4102, erp: "x", parent: 4102 }), [4102]);
  assert.deepEqual(referencedProjects(cards, { original: 4102, parent: 3202 }), [4102, 3202]);
  assert.deepEqual(referencedProjects(cards, {}), []);
});
