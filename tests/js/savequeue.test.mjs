// Unit tests for static/js/lib/savequeue.js: coalescing, order and rollback. [TS-9]
import assert from "node:assert/strict";
import { test } from "node:test";

import { createSaveQueue } from "../../momato/static/js/lib/savequeue.js";

const cell = (minutes, task = "general", day = "2026-10-07", line = "project:4102") => ({
  day, line, task, minutes,
});

function harness({ fail = () => false } = {}) {
  const sent = [];
  const saved = [];
  const failed = [];
  const queue = createSaveQueue({
    delay: 0,
    send: async (c) => {
      sent.push(c);
      if (fail(c)) throw new Error("refused");
      return { ok: true };
    },
    onSaved: (c) => saved.push(c),
    onFailed: (c, error, restoreTo) => failed.push({ c, message: error.message, restoreTo }),
  });
  return { queue, sent, saved, failed };
}

test("quick changes to one cell become one request with the latest value", async () => {
  const { queue, sent } = harness();
  queue.known(cell(0), 0);
  for (let minutes = 60; minutes <= 600; minutes += 60) queue.set(cell(minutes));
  await queue.flush();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].minutes, 600);
});

test("different cells are sent one after the other, each once", async () => {
  const { queue, sent } = harness();
  queue.set(cell(60, "task:1"));
  queue.set(cell(120, "task:2"));
  queue.set(cell(180, "task:1"));
  await queue.flush();
  assert.deepEqual(sent.map((c) => [c.task, c.minutes]), [["task:1", 180], ["task:2", 120]]);
});

test("a value back at what is stored sends nothing", async () => {
  const { queue, sent } = harness();
  queue.known(cell(120), 120);
  queue.set(cell(180));
  queue.set(cell(120));
  await queue.flush();
  assert.equal(sent.length, 0);
});

test("a refused save reports the last stored value to roll back to", async () => {
  const { queue, failed, saved } = harness({ fail: (c) => c.minutes === 540 });
  queue.known(cell(0), 0);
  queue.set(cell(60));
  await queue.flush();
  assert.equal(saved.length, 1);
  queue.set(cell(540));
  await queue.flush();
  assert.equal(failed.length, 1);
  assert.equal(failed[0].restoreTo, 60);
  assert.equal(failed[0].message, "refused");
  // and the queue keeps working afterwards
  queue.set(cell(120));
  await queue.flush();
  assert.equal(saved.length, 2);
});

test("changes made while a request is in flight are sent afterwards", async () => {
  const sent = [];
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const queue = createSaveQueue({
    delay: 0,
    send: async (c) => {
      sent.push(c.minutes);
      if (sent.length === 1) await gate;
    },
  });
  queue.set(cell(60));
  const first = queue.flush();
  await new Promise((resolve) => setTimeout(resolve, 5));
  queue.set(cell(120)); // arrives while 60 is being saved
  release();
  await first;
  await queue.flush();
  assert.deepEqual(sent, [60, 120]);
  assert.equal(queue.busy, false);
});

test("keys identify day, line and task", () => {
  const { queue } = harness();
  assert.equal(queue.keyOf(cell(1)), "2026-10-07|project:4102|general");
});

test("what is still waiting can be taken when the page goes away", async () => {
  const { queue, sent } = harness();
  queue.known(cell(60, "task:1"), 60);
  queue.set(cell(120, "task:1"));
  queue.set(cell(60, "task:2"));
  queue.set(cell(60, "task:1")); // back to what is stored: nothing to send for it
  const waiting = queue.takePending();
  assert.deepEqual(waiting.map((c) => [c.task, c.minutes]), [["task:2", 60]]);
  await queue.flush();
  assert.equal(sent.length, 0); // taken cells are not sent again
});
