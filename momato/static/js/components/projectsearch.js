// Choose a project with a server-side search, inside a popover (SH-12, AP-7).
import { useEffect, useId, useRef, useState } from "preact/hooks";

import { api } from "../api.js";
import { html } from "../html.js";
import { useDismiss } from "./ui.js";

export function ProjectSearch({ onPick, onClose, exclude = [], bookable = false, title = "Find a project" }) {
  const [text, setText] = useState("");
  const [hits, setHits] = useState([]);
  const ref = useRef(null);
  const input = useRef(null);
  const listId = useId();
  useDismiss(ref, true, onClose);

  useEffect(() => {
    input.current?.focus();
  }, []);
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api("search/projects", { params: { q: text, bookable: bookable || undefined } })
        .then((found) => !cancelled && setHits(found.filter((h) => !exclude.includes(h.number))))
        .catch(() => !cancelled && setHits([]));
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
      placeholder="Number or name"
      value=${text}
      onInput=${(e) => setText(e.target.value)}
    />
    <div id=${listId} role="listbox" aria-label="Projects">
      ${hits.length === 0 ? html`<div class="empty" role="option" aria-selected="false">No project found.</div>` : null}
      ${hits.map(
        (hit) => html`<button
          key=${hit.number}
          type="button"
          role="option"
          aria-selected="false"
          class="menu-item"
          onClick=${() => onPick(hit)}
        >
          <span class="menu-item__name">#${hit.number} ${hit.name}</span>
          <span class="menu-item__count">${hit.org_node_name}</span>
        </button>`,
      )}
    </div>
  </div>`;
}
