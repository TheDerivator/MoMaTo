// In-place editing for editors: a value is a button; a click turns it into an input that commits
// on Enter or blur and cancels on Escape (PP-3, OV-1, OV-4, DT-3).
import { useEffect, useId, useLayoutEffect, useRef, useState } from "preact/hooks";

import { api } from "../api.js";
import { html } from "../html.js";
import { useDismiss } from "./ui.js";

/**
 * `kind`: "text", "textarea" (Ctrl+Enter commits), "date", "number" or "select" (`options` of
 * `{ value, label }`, commits on change). `onCommit(text)` receives the typed text; the caller
 * decides whether it differs from the value. Without `editable` it is plain text. A heading
 * passes `describe: false`, so its button is named by its own text.
 */
export function InlineEdit({
  value,
  kind = "text",
  options = [],
  editable,
  onCommit,
  label,
  display,
  empty = "–",
  className = "",
  as = "span",
  maxLength,
  hint = "Click to edit",
  describe = true,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const input = useRef(null);
  const trigger = useRef(null);
  const finished = useRef(false);
  const restore = useRef(false);
  const shown = display ?? (value === null || value === undefined || value === "" ? empty : String(value));

  // Layout effect: the input has the focus as soon as it is there, so typing never goes astray.
  useLayoutEffect(() => {
    if (editing) {
      input.current?.focus();
      input.current?.select?.();
    } else if (restore.current) {
      restore.current = false;
      trigger.current?.focus();
    }
  }, [editing]);

  if (!editable) return html`<${as} class=${className}>${shown}<//>`;

  const begin = () => {
    finished.current = false;
    setDraft(value === null || value === undefined ? "" : String(value));
    setEditing(true);
  };
  const finish = (commit, text = draft) => {
    if (finished.current) return;
    finished.current = true;
    restore.current = true;
    setEditing(false);
    if (commit) onCommit(text);
  };

  if (!editing) {
    return html`<button
      type="button"
      ref=${trigger}
      class=${`inline-edit ${className}`}
      title=${hint}
      aria-label=${describe ? `${label}: ${shown}. Edit` : undefined}
      onClick=${begin}
    >
      ${shown}
    </button>`;
  }

  const keys = (event) => {
    if (event.key === "Escape") {
      event.stopPropagation();
      finish(false);
    } else if (event.key === "Enter" && kind !== "textarea") {
      event.preventDefault();
      finish(true);
    } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      finish(true);
    }
  };

  if (kind === "select") {
    return html`<select
      ref=${input}
      class="inline-input"
      aria-label=${label}
      value=${draft}
      onChange=${(e) => finish(true, e.target.value)}
      onKeyDown=${keys}
      onBlur=${() => finish(false)}
    >
      ${options.map((o) => html`<option key=${o.value} value=${o.value} selected=${String(o.value) === draft}>${o.label}</option>`)}
    </select>`;
  }
  if (kind === "textarea") {
    return html`<textarea
      ref=${input}
      class="inline-input inline-input--area"
      aria-label=${label}
      rows="4"
      maxlength=${maxLength}
      value=${draft}
      onInput=${(e) => setDraft(e.target.value)}
      onKeyDown=${keys}
      onBlur=${() => finish(true)}
    ></textarea>`;
  }
  return html`<input
    ref=${input}
    class="inline-input"
    type=${kind === "date" ? "date" : "text"}
    inputmode=${kind === "number" ? "decimal" : undefined}
    aria-label=${label}
    maxlength=${maxLength}
    value=${draft}
    onInput=${(e) => setDraft(e.target.value)}
    onKeyDown=${keys}
    onBlur=${() => finish(true)}
  />`;
}

/** Search people on the server and pick one, inside a popover (PD-4, OV-4). */
export function PersonSearch({ onPick, onClose, exclude = [], title = "Find a person" }) {
  const [text, setText] = useState("");
  const [results, setResults] = useState([]);
  const ref = useRef(null);
  const input = useRef(null);
  const listId = useId();
  useDismiss(ref, true, onClose);

  useEffect(() => {
    input.current?.focus();
  }, []);
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api("search/people", { params: { q: text } });
        if (!cancelled) setResults(found.filter((p) => !exclude.includes(p.id)));
      } catch {
        if (!cancelled) setResults([]);
      }
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [text]);

  return html`<div ref=${ref} class="popover popover--below person-search" role="dialog" aria-label=${title}>
    <input
      ref=${input}
      class="input"
      role="combobox"
      aria-expanded="true"
      aria-controls=${listId}
      aria-autocomplete="list"
      aria-label=${title}
      placeholder="Type a name"
      value=${text}
      onInput=${(e) => setText(e.target.value)}
    />
    <div id=${listId} role="listbox" aria-label="People">
      ${results.length === 0 ? html`<div class="empty" role="option" aria-selected="false">No one found.</div>` : null}
      ${results.map(
        (p) => html`<button
          key=${p.id}
          type="button"
          role="option"
          aria-selected="false"
          class="menu-item"
          onClick=${() => onPick(p)}
        >
          <span class="menu-item__name">${p.name}</span>
          <span class="menu-item__count">${p.job_title ?? ""}</span>
        </button>`,
      )}
    </div>
  </div>`;
}
