// The Logbook tab: filter chips and a timeline of changes to the important fields (LB-2 – LB-4).
import { useEffect, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { ViaBadge } from "../components/ui.js";
import { html } from "../html.js";
import { formatDate } from "../lib/format.js";
import { FILTERS, clip, dayOf, hasPair, sentence } from "../lib/logbook.js";

function Value({ text, className }) {
  const [open, setOpen] = useState(false);
  const { text: shown, clipped } = clip(text);
  if (!clipped) return html`<span class=${className}>${text}</span>`;
  return html`<span class=${className}>
    ${open ? text : shown}
    <button type="button" class="link-button value__toggle" aria-expanded=${open ? "true" : "false"} onClick=${() => setOpen(!open)}>
      ${open ? "less" : "more"}
    </button>
  </span>`;
}

function Entry({ entry, viewerId }) {
  const said = sentence(entry, viewerId);
  const pair = hasPair(entry);
  const showValue = entry.field !== "created";
  return html`<li class="log-entry">
    <time class="log-entry__date" datetime=${entry.at}>${formatDate(dayOf(entry.at))}</time>
    <span class="log-entry__dot" style=${{ "--hue": entry.hue }} aria-hidden="true"></span>
    <div class="log-entry__body">
      <span class="log-entry__sentence"><b>${said.who}</b><${ViaBadge} via=${entry.via} /> ${said.verb} <b>${said.what}</b></span>
      ${showValue
        ? html`<div class="log-entry__values" style=${{ "--hue": entry.hue }}>
            ${pair
              ? html`<${Value} className="log-chip log-chip--old" text=${entry.from_value} />
                  <span class="log-entry__arrow" aria-hidden="true">→</span>`
              : null}
            <${Value} className="log-chip log-chip--new" text=${entry.to_value ?? ""} />
          </div>`
        : null}
    </div>
  </li>`;
}

export function ProjectLogbook({ ctx, project }) {
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(null);
  const [error, setError] = useState("");
  const number = project.number;

  useEffect(() => {
    let cancelled = false;
    api(`projects/${number}/log`, { params: { filter: filter === "all" ? "" : filter } })
      .then((body) => {
        if (!cancelled) {
          setPage(body);
          setError("");
        }
      })
      .catch((failure) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [number, filter, project.log_count]);

  return html`<div class="logbook">
    <div class="status-chips" role="group" aria-label="Filter the logbook">
      ${FILTERS.map(
        (f) => html`<button
          key=${f.key}
          type="button"
          class="chip chip--plain"
          aria-pressed=${filter === f.key ? "true" : "false"}
          onClick=${() => setFilter(f.key)}
        >
          ${f.label}
        </button>`,
      )}
    </div>
    ${error ? html`<div class="empty" role="alert">${error}</div>` : null}
    ${page
      ? page.items.length === 0
        ? html`<p class="muted">No changes recorded${filter === "all" ? "" : " for this filter"}.</p>`
        : html`<ol class="card log-list" aria-label="Changes, newest first">
            ${page.items.map((entry) => html`<${Entry} key=${entry.id} entry=${entry} viewerId=${ctx.me.person_id} />`)}
          </ol>`
      : html`<div class="muted">Loading…</div>`}
  </div>`;
}
