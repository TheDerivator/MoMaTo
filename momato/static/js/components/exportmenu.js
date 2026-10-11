// "Export": a popover that downloads what is on screen as CSV or Excel (EXP-1 – EXP-3).
import { useRef, useState } from "preact/hooks";

import { html } from "../html.js";
import { FORMATS, defaultPeriod, periodProblem, projectsExportUrl, timeExportUrl } from "../lib/exports.js";
import { useDismiss } from "./ui.js";

function Links({ title, urlFor, disabled = false }) {
  return html`<div class="export-links" role="group" aria-label=${title}>
    ${FORMATS.map((f) =>
      disabled
        ? html`<span key=${f.key} class="menu-item menu-item--off" aria-disabled="true">${f.label}</span>`
        : html`<a key=${f.key} class="menu-item" href=${urlFor(f.key)} download>${f.label}</a>`,
    )}
  </div>`;
}

/** The project list with the filters in force. */
export function ProjectsExport({ route }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useDismiss(ref, open, () => setOpen(false));
  return html`<div class="popover-anchor" ref=${ref}>
    <button
      type="button"
      class="btn"
      aria-haspopup="dialog"
      aria-expanded=${open ? "true" : "false"}
      onClick=${() => setOpen(!open)}
    >Export</button>
    ${open
      ? html`<div class="popover popover--below export-popover" role="dialog" aria-label="Export the project list">
          <span class="popover__title">The list as filtered</span>
          <${Links} title="Project list" urlFor=${(format) => projectsExportUrl(route, format)} />
        </div>`
      : null}
  </div>`;
}

/** Booked time of a period for the branch on screen. */
export function TimeExport({ node, buckets, today }) {
  const [open, setOpen] = useState(false);
  const initial = defaultPeriod(buckets, today);
  const [start, setStart] = useState(initial.start);
  const [end, setEnd] = useState(initial.end);
  const ref = useRef(null);
  useDismiss(ref, open, () => setOpen(false));
  const problem = periodProblem(start, end);
  const begin = () => {
    if (!open) {
      const fresh = defaultPeriod(buckets, today);
      setStart(fresh.start);
      setEnd(fresh.end);
    }
    setOpen(!open);
  };
  return html`<div class="popover-anchor" ref=${ref}>
    <button
      type="button"
      class="btn"
      aria-haspopup="dialog"
      aria-expanded=${open ? "true" : "false"}
      onClick=${begin}
    >Export time</button>
    ${open
      ? html`<div class="popover popover--below export-popover" role="dialog" aria-label="Export booked time">
          <span class="popover__title">Time booked by the people shown</span>
          <div class="export-period">
            <label class="field">
              <span class="field__label">From</span>
              <input class="input" type="date" value=${start} onInput=${(e) => setStart(e.target.value)} />
            </label>
            <label class="field">
              <span class="field__label">To</span>
              <input class="input" type="date" value=${end} onInput=${(e) => setEnd(e.target.value)} />
            </label>
          </div>
          ${problem ? html`<div class="field__error" role="alert">${problem}</div>` : null}
          <${Links}
            title="Time entries"
            disabled=${Boolean(problem)}
            urlFor=${(format) => timeExportUrl({ start, end, node }, format)}
          />
        </div>`
      : null}
  </div>`;
}
