// Administration › Audit log: sign-ins and account, rights and organisation changes (ADM-6).
import { useCallback, useEffect, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { html } from "../html.js";
import { actionLabel, detailsText } from "../lib/admin.js";

const PAGE = 50;
const KINDS = [
  { value: "", label: "Everything" },
  { value: "auth.", label: "Sign-ins" },
  { value: "user.", label: "Accounts and rights" },
  { value: "person.", label: "People" },
  { value: "org.", label: "Organisation" },
  { value: "role.", label: "Roles" },
  { value: "access.", label: "Default access" },
];

function when(iso) {
  const date = new Date(iso);
  const day = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const time = date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${day}, ${time}`;
}

export function AuditLog() {
  const [kind, setKind] = useState("");
  const [entries, setEntries] = useState(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (before = null) => {
      try {
        const page = await api("admin/audit", {
          params: { limit: PAGE, before_id: before ?? undefined, action: kind || undefined },
        });
        setEntries((current) => (before === null ? page : [...(current ?? []), ...page]));
        setMore(page.length === PAGE);
        setError("");
      } catch (failure) {
        setError(messageOf(failure));
      }
    },
    [kind],
  );
  useEffect(() => {
    setEntries(null);
    load();
  }, [load]);

  return html`<section class="card admin-card" aria-label="Audit log">
    <div class="admin-toolbar">
      <label class="field admin-toolbar__field">
        <span class="field__label">Show</span>
        <select class="select" value=${kind} onChange=${(e) => setKind(e.target.value)}>
          ${KINDS.map((k) => html`<option key=${k.value} value=${k.value} selected=${k.value === kind}>${k.label}</option>`)}
        </select>
      </label>
    </div>
    ${error ? html`<div class="empty" role="alert">${error}</div>` : null}
    ${entries === null && !error ? html`<div class="muted">Loading…</div>` : null}
    ${entries && entries.length === 0 ? html`<div class="empty">Nothing recorded yet.</div>` : null}
    ${entries && entries.length > 0
      ? html`<div class="admin-scroll">
          <table class="admin-table">
            <thead>
              <tr><th>When</th><th>Who</th><th>What</th><th>About</th><th>Details</th></tr>
            </thead>
            <tbody>
              ${entries.map(
                (e) => html`<tr key=${e.id}>
                  <td class="admin-table__when">${when(e.at)}</td>
                  <td>${e.actor ?? html`<span class="muted">the system</span>`}</td>
                  <td><b>${actionLabel(e.action)}</b></td>
                  <td>${e.target_type ? `${e.target_type} ${e.target_id ?? ""}` : "–"}</td>
                  <td class="admin-table__details">${detailsText(e.details)}</td>
                </tr>`,
              )}
            </tbody>
          </table>
        </div>`
      : null}
    ${more
      ? html`<button type="button" class="btn" onClick=${() => load(entries.at(-1).id)}>Show older</button>`
      : null}
  </section>`;
}
