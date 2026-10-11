// Administration › Single sign-on: the configured providers and which of their groups hold roles
// (AUTH-3, ADM-5).
import { useCallback, useEffect, useMemo, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { html } from "../html.js";
import { parseScope, scopeOptions } from "../lib/admin.js";

const KINDS = {
  redirect: "sign-in page of the provider",
  ambient: "trusted proxy header",
  negotiate: "Windows sign-in by MoMaTo itself",
};

export function SsoPage({ ctx }) {
  const [providers, setProviders] = useState(null);
  const [mappings, setMappings] = useState(null);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const options = useMemo(() => scopeOptions(ctx.tree), [ctx.tree]);

  const [provider, setProvider] = useState("");
  const [group, setGroup] = useState("");
  const [roleKey, setRoleKey] = useState("");
  const [scope, setScope] = useState("global");

  const load = useCallback(async () => {
    try {
      const [found, listed, roleList] = await Promise.all([
        api("admin/sso-providers"),
        api("admin/group-mappings"),
        api("admin/roles"),
      ]);
      setProviders(found);
      setMappings(listed);
      setRoles(roleList);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const chosenProvider = provider || providers?.[0]?.name || "";
  const chosenRole = roleKey || roles[0]?.key || "";

  const change = async (request, message) => {
    try {
      setMappings(await request());
      ctx.toast(message);
    } catch (failure) {
      ctx.toast(messageOf(failure), "error");
    }
  };
  const add = (event) => {
    event.preventDefault();
    change(
      () =>
        api("admin/group-mappings", {
          method: "POST",
          body: { provider: chosenProvider, group_name: group.trim(), role_key: chosenRole, ...parseScope(scope) },
        }),
      "Group mapped.",
    ).then(() => setGroup(""));
  };

  if (error) return html`<div class="empty" role="alert">${error}</div>`;
  if (!providers || !mappings) return html`<div class="muted">Loading…</div>`;
  return html`<div class="admin-stack">
    <section class="card admin-card" aria-label="Providers">
      <h2 class="card__title">Providers</h2>
      ${providers.length === 0
        ? html`<p class="muted admin-note">
            Single sign-on is not switched on: people sign in with their MoMaTo password. It is
            configured with environment variables (see docs/AUTH.md).
          </p>`
        : html`<ul class="admin-assignments">
            ${providers.map(
              (p) => html`<li key=${p.name} class="admin-assignment">
                <span><b>${p.display_name}</b> <span class="muted">(${p.name}) · ${KINDS[p.kind] ?? p.kind}</span></span>
              </li>`,
            )}
          </ul>`}
      <p class="muted admin-note">
        People are matched on their email or Windows login name at their first sign-in; prepare them
        under People. What a group holds is added to what a person has of their own.
      </p>
    </section>

    <section class="card admin-card" aria-label="Group mappings">
      <h2 class="card__title">Groups and roles</h2>
      <ul class="admin-assignments">
        ${mappings.length === 0 ? html`<li class="muted">No group holds a role.</li>` : null}
        ${mappings.map(
          (m) => html`<li key=${m.id} class="admin-assignment">
            <span><b>${m.group_name}</b> <span class="muted">(${m.provider})</span> → ${m.role_name} · ${m.scope_label}</span>
            <button
              type="button"
              class="btn btn--ghost"
              aria-label=${`Remove the mapping of ${m.group_name}`}
              onClick=${() => change(() => api(`admin/group-mappings/${m.id}`, { method: "DELETE" }), "Mapping removed.")}
            >Remove</button>
          </li>`,
        )}
      </ul>
      ${providers.length
        ? html`<form class="admin-inline admin-inline--form" onSubmit=${add}>
            <label class="field">
              <span class="field__label">Provider</span>
              <select class="select" value=${chosenProvider} onChange=${(e) => setProvider(e.target.value)}>
                ${providers.map((p) => html`<option key=${p.name} value=${p.name} selected=${p.name === chosenProvider}>${p.display_name}</option>`)}
              </select>
            </label>
            <label class="field">
              <span class="field__label">Group (as the provider sends it)</span>
              <input class="input" value=${group} required maxlength="255" onInput=${(e) => setGroup(e.target.value)} />
            </label>
            <label class="field">
              <span class="field__label">Role</span>
              <select class="select" value=${chosenRole} onChange=${(e) => setRoleKey(e.target.value)}>
                ${roles.map((r) => html`<option key=${r.key} value=${r.key} selected=${r.key === chosenRole}>${r.name}</option>`)}
              </select>
            </label>
            <label class="field">
              <span class="field__label">Where</span>
              <select class="select" value=${scope} onChange=${(e) => setScope(e.target.value)}>
                ${options.map((o) => html`<option key=${o.value} value=${o.value} selected=${o.value === scope}>${o.label}</option>`)}
              </select>
            </label>
            <button type="submit" class="btn btn--dark admin-inline__go">Map</button>
          </form>`
        : null}
    </section>
  </div>`;
}
