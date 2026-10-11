// Administration › Roles and Default access: what a role bundles, and what everybody holds
// without being given it (ADM-5, D-013).
import { useCallback, useEffect, useMemo, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { ConfirmDialog } from "../components/dialogs.js";
import { html } from "../html.js";
import { parseScope, scopeOptions } from "../lib/admin.js";
import { plural } from "../lib/format.js";

function PermissionChecks({ catalog, selected, onChange, disabled, name }) {
  const toggle = (value) =>
    onChange(selected.includes(value) ? selected.filter((p) => p !== value) : [...selected, value]);
  return html`<div class="admin-permissions" role="group" aria-label=${`Permissions of ${name}`}>
    ${catalog.map(
      (p) => html`<label key=${p.value} class="check-row admin-permission">
        <input type="checkbox" checked=${selected.includes(p.value)} disabled=${disabled} onChange=${() => toggle(p.value)} />
        <span>
          <b>${p.value}</b>
          <span class="muted"> ${p.description}${p.scoped ? "" : " (always everywhere)"}</span>
        </span>
      </label>`,
    )}
  </div>`;
}

function RoleCard({ role, catalog, onChanged, toast }) {
  const [name, setName] = useState(role.name);
  const [description, setDescription] = useState(role.description);
  const [permissions, setPermissions] = useState(role.permissions);
  const [asking, setAsking] = useState(false);
  const dirty =
    name !== role.name ||
    description !== role.description ||
    [...permissions].sort().join() !== [...role.permissions].sort().join();

  const call = async (request, message) => {
    try {
      await request();
      toast(message);
      await onChanged();
    } catch (failure) {
      toast(messageOf(failure), "error");
    }
  };
  return html`<section class="card admin-card" aria-label=${`Role ${role.name}`}>
    <div class="admin-role-head">
      ${role.is_builtin
        ? html`<h2 class="card__title admin-role-head__name">${role.name}</h2>`
        : html`<input class="input admin-role-head__input" aria-label="Role name" value=${name} maxlength="100" onInput=${(e) => setName(e.target.value)} />`}
      <span class="muted">${role.key}</span>
      ${role.is_builtin ? html`<span class="admin-chip">Built in</span>` : null}
      <span class="admin-toolbar__spacer"></span>
      <span class="muted">${plural(role.assignment_count, "assignment", "assignments")} · ${plural(role.default_grant_count, "default grant", "default grants")}</span>
    </div>
    ${role.is_builtin
      ? null
      : html`<label class="field">
          <span class="field__label">Description</span>
          <input class="input" value=${description} maxlength="1000" onInput=${(e) => setDescription(e.target.value)} />
        </label>`}
    <${PermissionChecks}
      catalog=${catalog}
      selected=${permissions}
      name=${role.name}
      disabled=${role.is_builtin}
      onChange=${setPermissions}
    />
    ${role.is_builtin
      ? null
      : html`<div class="admin-inline">
          <button
            type="button"
            class="btn btn--dark"
            disabled=${!dirty || !name.trim()}
            onClick=${() =>
              call(
                () => api(`admin/roles/${role.id}`, { method: "PATCH", body: { name, description, permissions } }),
                "Role saved.",
              )}
          >Save role</button>
          <button type="button" class="btn btn--ghost btn--danger" onClick=${() => setAsking(true)}>Delete role</button>
        </div>`}
    ${asking
      ? html`<${ConfirmDialog}
          title=${`Delete “${role.name}”?`}
          confirmLabel="Delete role"
          onClose=${() => setAsking(false)}
          onConfirm=${() => call(() => api(`admin/roles/${role.id}`, { method: "DELETE" }), "Role deleted.")}
        >
          <p>A role that is still assigned, or granted by default, cannot be deleted.</p>
        <//>`
      : null}
  </section>`;
}

function NewRole({ catalog, onChanged, toast }) {
  const [name, setName] = useState("");
  const [key, setKey] = useState("");
  const [permissions, setPermissions] = useState(["project.view"]);
  const [error, setError] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    try {
      await api("admin/roles", { method: "POST", body: { key, name: name.trim(), permissions } });
      toast(`Role ${name.trim()} created.`);
      setName("");
      setKey("");
      setPermissions(["project.view"]);
      setError("");
      await onChanged();
    } catch (failure) {
      setError(messageOf(failure));
    }
  };
  return html`<form class="card admin-card" aria-label="New role" onSubmit=${submit}>
    <h2 class="card__title">New role</h2>
    <div class="admin-pair">
      <label class="field">
        <span class="field__label">Name</span>
        <input
          class="input"
          value=${name}
          maxlength="100"
          required
          onInput=${(e) => {
            setName(e.target.value);
            if (!key || key === slug(name)) setKey(slug(e.target.value));
          }}
        />
      </label>
      <label class="field">
        <span class="field__label">Key (lowercase letters, digits, – and _)</span>
        <input class="input" value=${key} pattern="[a-z][a-z0-9_\\-]{1,49}" required onInput=${(e) => setKey(e.target.value)} />
      </label>
    </div>
    <${PermissionChecks} catalog=${catalog} selected=${permissions} name="the new role" disabled=${false} onChange=${setPermissions} />
    ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
    <div><button type="submit" class="btn btn--dark">Create role</button></div>
  </form>`;
}

function slug(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 50);
}

export function RolesPage({ ctx }) {
  const [roles, setRoles] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setRoles(await api("admin/roles"));
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, []);
  useEffect(() => {
    load();
    api("admin/permissions").then(setCatalog).catch(() => setCatalog([]));
  }, [load]);
  if (error) return html`<div class="empty" role="alert">${error}</div>`;
  if (!roles) return html`<div class="muted">Loading…</div>`;
  return html`<div class="admin-stack">
    <p class="muted admin-note">
      A role bundles permissions. People hold roles on a branch of the organisation (and everything
      below it), everywhere, or on their own department.
    </p>
    ${roles.map(
      (role) => html`<${RoleCard}
        key=${`${role.id}:${role.name}:${role.permissions.join()}`}
        role=${role}
        catalog=${catalog}
        onChanged=${load}
        toast=${ctx.toast}
      />`,
    )}
    <${NewRole} catalog=${catalog} onChanged=${load} toast=${ctx.toast} />
  </div>`;
}

// ------------------------------------------------------------------ default access

const AUDIENCES = [
  {
    key: "signed_in",
    title: "Everybody who is signed in",
    note: "Granted to every signed-in person, in addition to their own roles.",
  },
  {
    key: "anonymous",
    title: "Anybody, signed in or not",
    note: "A floor for everyone, visitors included. Leave it empty to require a sign-in (D-013).",
  },
];

function GrantRow({ grant, onRemove }) {
  return html`<li class="admin-assignment">
    <span><b>${grant.role_name}</b> · ${grant.scope_label}</span>
    <button
      type="button"
      class="btn btn--ghost"
      aria-label=${`Remove ${grant.role_name} (${grant.scope_label}) from the defaults`}
      onClick=${() => onRemove(grant)}
    >Remove</button>
  </li>`;
}

function AddGrant({ audience, roles, options, onAdd }) {
  const [picked, setRole] = useState("");
  const [scope, setScope] = useState("global");
  const role = roles.some((r) => r.key === picked) ? picked : (roles[0]?.key ?? "");
  return html`<div class="admin-inline admin-inline--form">
    <label class="field">
      <span class="field__label">Role</span>
      <select class="select" aria-label=${`Role to grant ${audience.title}`} value=${role} onChange=${(e) => setRole(e.target.value)}>
        ${roles.map((r) => html`<option key=${r.key} value=${r.key} selected=${r.key === role}>${r.name}</option>`)}
      </select>
    </label>
    <label class="field">
      <span class="field__label">Where</span>
      <select class="select" aria-label=${`Where to grant ${audience.title}`} value=${scope} onChange=${(e) => setScope(e.target.value)}>
        ${options.map((o) => html`<option key=${o.value} value=${o.value} selected=${o.value === scope}>${o.label}</option>`)}
      </select>
    </label>
    <button type="button" class="btn btn--dark admin-inline__go" disabled=${!role} onClick=${() => onAdd(audience.key, role, scope)}>
      Add
    </button>
  </div>`;
}

export function DefaultAccessPage({ ctx }) {
  const [grants, setGrants] = useState(null);
  const [roles, setRoles] = useState([]);
  const [error, setError] = useState("");
  const options = useMemo(() => scopeOptions(ctx.tree), [ctx.tree]);

  const load = useCallback(async () => {
    try {
      setGrants(await api("admin/default-grants"));
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, []);
  useEffect(() => {
    load();
    api("admin/roles").then(setRoles).catch(() => setRoles([]));
  }, [load]);

  const change = async (request, message) => {
    try {
      setGrants(await request());
      ctx.toast(message);
    } catch (failure) {
      ctx.toast(messageOf(failure), "error");
    }
  };
  const add = (audience, role, scope) =>
    change(
      () => api("admin/default-grants", { method: "POST", body: { audience, role_key: role, ...parseScope(scope) } }),
      "Default access added.",
    );
  const remove = (grant) =>
    change(() => api(`admin/default-grants/${grant.id}`, { method: "DELETE" }), "Default access removed.");

  if (error) return html`<div class="empty" role="alert">${error}</div>`;
  if (!grants) return html`<div class="muted">Loading…</div>`;
  return html`<div class="admin-stack">
    ${AUDIENCES.map((audience) => {
      const mine = grants.filter((g) => g.audience === audience.key);
      return html`<section key=${audience.key} class="card admin-card" aria-label=${audience.title}>
        <h2 class="card__title">${audience.title}</h2>
        <p class="muted admin-note">${audience.note}</p>
        <ul class="admin-assignments">
          ${mine.length === 0 ? html`<li class="muted">Nothing.</li>` : null}
          ${mine.map((g) => html`<${GrantRow} key=${g.id} grant=${g} onRemove=${remove} />`)}
        </ul>
        <${AddGrant} audience=${audience} roles=${roles} options=${options} onAdd=${add} />
      </section>`;
    })}
  </div>`;
}
