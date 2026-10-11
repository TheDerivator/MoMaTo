// Unit tests for static/js/lib/appearance.js: mode, style and what is remembered. [APP-1] [APP-2]
import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULTS, STORAGE_KEY, apply, normalize, read, resolveMode, write } from "../../momato/static/js/lib/appearance.js";

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value;
    },
  };
}

test("the defaults follow the system mode, play it playful and celebrate", () => {
  assert.deepEqual(DEFAULTS, { mode: null, look: "playful", celebrate: true });
  assert.deepEqual(normalize(undefined), DEFAULTS);
  assert.deepEqual(normalize("nonsense"), DEFAULTS);
});

test("stored values are validated one by one", () => {
  assert.deepEqual(normalize({ mode: "dark", look: "boring", celebrate: false }), {
    mode: "dark", look: "boring", celebrate: false,
  });
  assert.deepEqual(normalize({ mode: "sepia", look: "managerial", celebrate: "yes" }), DEFAULTS);
});

test("[APP-2] the mode follows the system until chosen", () => {
  assert.equal(resolveMode({ mode: null }, true), "dark");
  assert.equal(resolveMode({ mode: null }, false), "light");
  assert.equal(resolveMode({ mode: "light" }, true), "light");
  assert.equal(resolveMode({ mode: "dark" }, false), "dark");
});

test("reading and writing survive broken or blocked storage", () => {
  const storage = fakeStorage();
  assert.deepEqual(read(storage), DEFAULTS);
  write(storage, { mode: "dark", look: "boring", celebrate: false });
  assert.deepEqual(JSON.parse(storage.data[STORAGE_KEY]), { mode: "dark", look: "boring", celebrate: false });
  assert.deepEqual(read(storage), { mode: "dark", look: "boring", celebrate: false });

  assert.deepEqual(read(fakeStorage({ [STORAGE_KEY]: "{not json" })), DEFAULTS);
  const blocked = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  assert.deepEqual(read(blocked), DEFAULTS);
  assert.doesNotThrow(() => write(blocked, DEFAULTS));
});

test("applying sets the attributes the stylesheet reads", () => {
  const root = { dataset: {}, style: {} };
  assert.equal(apply(root, { mode: null, look: "boring" }, true), "dark");
  assert.deepEqual(root.dataset, { mode: "dark", look: "boring" });
  assert.equal(root.style.colorScheme, "dark");
  apply(root, { mode: "light", look: "playful" }, true);
  assert.equal(root.dataset.mode, "light");
  assert.equal(root.dataset.look, "playful");
});
