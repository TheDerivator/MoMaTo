// Unit tests for static/js/lib/editor.js: the composer's text operations. [RM-1] [RM-2]
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  TEMPLATE, insertBlock, lineEnd, prefixLines, removeFragment, withTemplate, wrap,
} from "../../momato/static/js/lib/editor.js";

test("wrapping surrounds the selection or a placeholder and selects it", () => {
  assert.deepEqual(wrap("a big cat", 2, 5, "**"), { text: "a **big** cat", start: 4, end: 7 });
  assert.deepEqual(wrap("ab", 1, 1, "`", "`", "code"), { text: "a`code`b", start: 2, end: 6 });
  assert.deepEqual(wrap("", 0, 0, "[", "](https://)", "link text"), {
    text: "[link text](https://)", start: 1, end: 10,
  });
});

test("prefixing touches every line of the selection from its line start", () => {
  const result = prefixLines("one\ntwo\nthree", 5, 9, "- ");
  assert.equal(result.text, "one\n- two\n- three");
  assert.deepEqual(prefixLines("solo", 2, 2, "- "), { text: "- solo", start: 4, end: 2 + 2 });
});

test("a block goes on its own line after the line of the caret", () => {
  assert.equal(lineEnd("abc\ndef", 1), 3);
  assert.equal(lineEnd("abc", 1), 3);
  const text = "first line\nsecond";
  const result = insertBlock(text, lineEnd(text, 3), "![x](api/attachments/a/x.png)");
  assert.equal(result.text, "first line\n![x](api/attachments/a/x.png)\nsecond");
  assert.equal(insertBlock("", 0, "B").text, "B");
  assert.equal(insertBlock("a\n", 2, "B").text, "a\nB");
  assert.equal(insertBlock("text", 4, "B").text, "text\nB");
  assert.equal(insertBlock("text", 4, "B").start, 6);
});

test("removing an image takes its line break too", () => {
  const image = "![x](u)";
  assert.equal(removeFragment(`before\n${image}\nafter`, image), "before\nafter");
  assert.equal(removeFragment(`only ${image}`, image), "only ");
  assert.equal(removeFragment("none", image), "none");
});

test("the template starts a fresh paragraph and puts the caret after Done", () => {
  assert.equal(TEMPLATE, "Done:\n- \n\nNext steps:\n- ");
  assert.deepEqual(withTemplate(""), { text: TEMPLATE, start: 8, end: 8 });
  assert.deepEqual(withTemplate("  \n"), { text: TEMPLATE, start: 8, end: 8 });
  const after = withTemplate("Some text");
  assert.equal(after.text, `Some text\n\n${TEMPLATE}`);
  assert.equal(after.text.slice(after.start - 8, after.start), "Done:\n- ");
  assert.equal(withTemplate("Some text\n").text, `Some text\n\n${TEMPLATE}`);
  assert.equal(withTemplate("Some text\n\n").text, `Some text\n\n${TEMPLATE}`);
});
