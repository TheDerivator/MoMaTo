// Saving timesheet cells (TS-9): every change is sent as the cell's new absolute number of minutes,
// quick clicks on the same cell are coalesced into one request, requests go one after the other,
// and a refused save reports the last value the server confirmed so the screen can roll back.

/**
 * `send({ day, line, task, minutes })` resolves when the server accepted the value and rejects
 * when it refused. `confirmed(key)` is the last value known to be stored (the starting point
 * of a rollback). Callbacks: `onSaved(cell, result)`, `onFailed(cell, error, restoreTo)`.
 */
export function createSaveQueue({ send, onSaved, onFailed, delay = 250 }) {
  const pending = new Map(); // key → latest cell
  const confirmedValues = new Map(); // key → last stored minutes
  let timer = null;
  let running = null;

  const keyOf = (cell) => `${cell.day}|${cell.line}|${cell.task}`;

  async function drain() {
    while (pending.size) {
      const [key, cell] = pending.entries().next().value;
      pending.delete(key);
      if (confirmedValues.get(key) === cell.minutes) continue; // back to what is stored
      try {
        const result = await send(cell);
        confirmedValues.set(key, cell.minutes);
        onSaved?.(cell, result);
      } catch (error) {
        // Later changes to this cell are dropped: they were made on top of a value the server
        // refused, and the screen goes back to what is stored.
        pending.delete(key);
        onFailed?.(cell, error, confirmedValues.get(key) ?? 0);
      }
    }
  }

  function start() {
    timer = null;
    if (running) return running;
    running = drain().finally(() => {
      running = null;
      if (pending.size && timer === null) timer = setTimeout(start, 0);
    });
    return running;
  }

  return {
    /** Tell the queue what is stored for a cell (from a loaded week). */
    known(cell, minutes) {
      confirmedValues.set(keyOf(cell), minutes);
    },
    /** A cell changed: its latest value replaces any earlier one that is still waiting. */
    set(cell) {
      pending.set(keyOf(cell), cell);
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(start, delay);
    },
    /** The cells still waiting (the page is going away: they are sent without an answer). */
    takePending() {
      const cells = [...pending.values()].filter((c) => confirmedValues.get(keyOf(c)) !== c.minutes);
      pending.clear();
      if (timer !== null) clearTimeout(timer);
      timer = null;
      return cells;
    },
    /** Send everything now (before leaving a week, and in tests). */
    async flush() {
      if (timer !== null) clearTimeout(timer);
      timer = null;
      await start();
      while (pending.size || running) {
        await start();
      }
    },
    get busy() {
      return pending.size > 0 || running !== null;
    },
    keyOf,
  };
}
