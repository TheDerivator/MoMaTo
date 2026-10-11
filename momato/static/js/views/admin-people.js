// Administration › People: the list, and one page per person with their data, availability,
// sign-in and access (ADM-2 – ADM-5).
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { ConfirmDialog, Dialog } from "../components/dialogs.js";
import { Avatar } from "../components/ui.js";
import { html } from "../html.js";
import {
  STATUS_LABELS, WEEKDAYS, daysText, hoursField, parseScope, patternFromTexts, patternSummary,
  scopeOptions, suggestUsername,
} from "../lib/admin.js";
import { plural } from "../lib/format.js";
import { buildUrl } from "../lib/routes.js";
import { expiryText, lastUsedText, scopeLabel } from "../lib/tokens.js";
import { pathTo, treeRows } from "../lib/tree.js";
import { Link, navigate } from "../router.js";

const HUES = [285, 155, 235, 60, 330, 20, 195, 105];

function placeOf(tree, nodeId) {
  if (nodeId === null || nodeId === undefined) return "–";
  const names = pathTo(tree, nodeId).slice(1).map((n) => n.name);
  return names.length ? names.join(" › ") : tree.root.name;
}

function NodeSelect({ tree, value, onChange, label }) {
  const rows = useMemo(() => treeRows(tree, new Set(), {}), [tree]);
  return html`<label class="field">
    <span class="field__label">${label}</span>
    <select class="select" value=${value ?? ""} onChange=${(e) => onChange(Number(e.target.value))} required>
      ${rows.map(
        (r) => html`<option key=${r.id} value=${r.id} selected=${r.id === value}>${"– ".repeat(r.depth)}${r.name}</option>`,
      )}
    </select>
  </label>`;
}

function PatternFields({ texts, onChange }) {
  return html`<fieldset class="admin-pattern">
    <legend class="field__label">Working hours per day</legend>
    <div class="admin-pattern__days">
      ${WEEKDAYS.map(
        (day, i) => html`<label key=${day} class="admin-pattern__day">
          <span>${day}</span>
          <input
            class="input"
            inputmode="decimal"
            aria-label=${`Hours on ${day}`}
            value=${texts[i]}
            onInput=${(e) => onChange(texts.map((t, j) => (j === i ? e.target.value : t)))}
          />
        </label>`,
      )}
    </div>
  </fieldset>`;
}

function HuePicker({ value, onChange }) {
  return html`<div class="field" role="radiogroup" aria-label="Colour">
    <span class="field__label">Colour</span>
    <div class="swatches">
      ${HUES.map(
        (h) => html`<button
          key=${h}
          type="button"
          role="radio"
          aria-checked=${h === value ? "true" : "false"}
          aria-label=${`Hue ${h}`}
          class=${`swatch-button${h === value ? " swatch-button--on" : ""}`}
          style=${{ "--hue": h }}
          onClick=${() => onChange(h)}
        ></button>`,
      )}
    </div>
  </div>`;
}

// ------------------------------------------------------------------ a new person

function NewPersonDialog({ ctx, onClose }) {
  const { tree, toast } = ctx;
  const defaultNode = ctx.myPerson?.org_node_id ?? tree.root.id;
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [node, setNode] = useState(defaultNode);
  const [hue, setHue] = useState(HUES[0]);
  const [texts, setTexts] = useState(["8", "8", "8", "8", "8"]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    const minutes = patternFromTexts(texts);
    if (!minutes) return setError("Each day is a number of hours between 0 and 12.");
    setBusy(true);
    try {
      const created = await api("admin/people", {
        method: "POST",
        body: { name: name.trim(), job_title: title.trim() || null, org_node_id: node, hue, work_minutes: minutes },
      });
      await ctx.reload();
      toast(`Added ${created.name}.`);
      navigate(buildUrl({ view: "admin", section: "people", id: created.id }));
    } catch (failure) {
      setError(messageOf(failure));
      setBusy(false);
    }
  };

  return html`<${Dialog} title="New person" onClose=${onClose}>
    <form class="form" onSubmit=${submit}>
      <label class="field">
        <span class="field__label">Name</span>
        <input class="input" value=${name} maxlength="200" required onInput=${(e) => setName(e.target.value)} />
      </label>
      <label class="field">
        <span class="field__label">Job title</span>
        <input class="input" value=${title} maxlength="100" onInput=${(e) => setTitle(e.target.value)} />
      </label>
      <${NodeSelect} tree=${tree} value=${node} onChange=${setNode} label="Place in the organisation" />
      <${HuePicker} value=${hue} onChange=${setHue} />
      <${PatternFields} texts=${texts} onChange=${setTexts} />
      <p class="field__hint">Sign-in is prepared afterwards, on the person's page.</p>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" onClick=${onClose}>Cancel</button>
        <button class="btn btn--dark" type="submit" disabled=${busy}>Add person</button>
      </div>
    </form>
  <//>`;
}

// ------------------------------------------------------------------ the list

function StatusChip({ status }) {
  return html`<span class=${`admin-status admin-status--${status}`}>${STATUS_LABELS[status]}</span>`;
}

export function PeopleList({ ctx }) {
  const { tree, me } = ctx;
  const [people, setPeople] = useState(null);
  const [error, setError] = useState("");
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [showGone, setShowGone] = useState(false);
  const [adding, setAdding] = useState(false);
  const timer = useRef(0);
  const manageOrg = me.permissions["org.manage"].everywhere;

  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setQuery(text.trim()), 200);
    return () => window.clearTimeout(timer.current);
  }, [text]);

  useEffect(() => {
    let cancelled = false;
    api("admin/people", { params: { q: query || undefined } })
      .then((found) => {
        if (!cancelled) {
          setPeople(found);
          setError("");
        }
      })
      .catch((failure) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [query, ctx.boot.people]);

  const shown = (people ?? []).filter((p) => showGone || p.status !== "deactivated");
  return html`<section class="card admin-card" aria-label="People">
    <div class="admin-toolbar">
      <label class="field admin-toolbar__field">
        <span class="field__label">Find</span>
        <input class="input" type="search" placeholder="Name, username or email" value=${text} onInput=${(e) => setText(e.target.value)} />
      </label>
      <label class="check-row">
        <input type="checkbox" checked=${showGone} onChange=${(e) => setShowGone(e.target.checked)} />
        Show deactivated people
      </label>
      <span class="admin-toolbar__spacer"></span>
      <span class="muted" aria-live="polite">${plural(shown.length, "person", "people")}</span>
      ${manageOrg ? html`<button type="button" class="btn btn--dark" onClick=${() => setAdding(true)}>+ New person</button>` : null}
    </div>
    ${error ? html`<div class="empty" role="alert">${error}</div>` : null}
    ${people === null && !error ? html`<div class="muted">Loading…</div>` : null}
    ${people && shown.length === 0 ? html`<div class="empty">Nobody matches.</div>` : null}
    ${shown.length
      ? html`<div class="admin-scroll">
          <table class="admin-table">
            <thead>
              <tr><th>Person</th><th>Place</th><th>Working time</th><th>Status</th><th>Sign-in</th><th>Access</th></tr>
            </thead>
            <tbody>
              ${shown.map(
                (p) => html`<tr key=${p.id}>
                  <td>
                    <div class="admin-person">
                      <${Avatar} person=${{ name: p.name, hue: p.hue }} size=${28} />
                      <div class="admin-person__text">
                        <${Link} class="admin-person__name" href=${buildUrl({ view: "admin", section: "people", id: p.id })}>${p.name}<//>
                        <span class="muted">${p.job_title ?? ""}</span>
                      </div>
                    </div>
                  </td>
                  <td>${placeOf(tree, p.org_node_id)}</td>
                  <td>${patternSummary(p.work_minutes).split(" (")[0]}</td>
                  <td><${StatusChip} status=${p.status} /></td>
                  <td>${p.username ?? html`<span class="muted">–</span>`}</td>
                  <td>
                    <span class="admin-chips">
                      ${p.assignments.map((a) => html`<span key=${a.id} class="admin-chip">${a.role_name} · ${a.scope_label}</span>`)}
                    </span>
                  </td>
                </tr>`,
              )}
            </tbody>
          </table>
        </div>`
      : null}
    ${adding ? html`<${NewPersonDialog} ctx=${ctx} onClose=${() => setAdding(false)} />` : null}
  </section>`;
}

// ------------------------------------------------------------------ one person

function SecretBox({ password, onDone }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return html`<div class="admin-secret" role="status">
    <span class="field__label">New password (shown once)</span>
    <code class="admin-secret__value">${password}</code>
    <div class="admin-secret__actions">
      <button type="button" class="btn" onClick=${copy}>${copied ? "Copied" : "Copy"}</button>
      <button type="button" class="btn btn--ghost" onClick=${onDone}>Done</button>
    </div>
    <p class="field__hint">Pass it on in person or by a safe channel. It must be changed at the first sign-in.</p>
  </div>`;
}

function Details({ ctx, person, run, canEdit }) {
  const { tree } = ctx;
  const [name, setName] = useState(person.name);
  const [title, setTitle] = useState(person.job_title ?? "");
  const [node, setNode] = useState(person.org_node_id);
  const [hue, setHue] = useState(person.hue);
  const [texts, setTexts] = useState(person.work_minutes.map(hoursField));
  const [error, setError] = useState("");

  if (!canEdit) {
    return html`<section class="card admin-card" aria-label="Details">
      <h2 class="card__title">Details</h2>
      <dl class="admin-facts">
        <dt>Place</dt><dd>${placeOf(tree, person.org_node_id)}</dd>
        <dt>Job title</dt><dd>${person.job_title ?? "–"}</dd>
        <dt>Working time</dt><dd>${patternSummary(person.work_minutes)}</dd>
      </dl>
    </section>`;
  }
  const save = async (event) => {
    event.preventDefault();
    const minutes = patternFromTexts(texts);
    if (!minutes) return setError("Each day is a number of hours between 0 and 12.");
    setError("");
    await run(
      () =>
        api(`admin/people/${person.id}`, {
          method: "PATCH",
          body: { name: name.trim(), job_title: title.trim() || null, org_node_id: node, hue, work_minutes: minutes },
        }),
      "Saved.",
    );
  };
  return html`<section class="card admin-card" aria-label="Details">
    <h2 class="card__title">Details</h2>
    <form class="form admin-form" onSubmit=${save}>
      <label class="field">
        <span class="field__label">Name</span>
        <input class="input" value=${name} maxlength="200" required onInput=${(e) => setName(e.target.value)} />
      </label>
      <label class="field">
        <span class="field__label">Job title</span>
        <input class="input" value=${title} maxlength="100" onInput=${(e) => setTitle(e.target.value)} />
      </label>
      <${NodeSelect} tree=${tree} value=${node} onChange=${setNode} label="Place in the organisation" />
      <${HuePicker} value=${hue} onChange=${setHue} />
      <${PatternFields} texts=${texts} onChange=${setTexts} />
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div><button class="btn btn--dark" type="submit">Save details</button></div>
    </form>
  </section>`;
}

function Availability({ person, run, canEdit }) {
  const [drafts, setDrafts] = useState({});
  const [year, setYear] = useState("");
  const [days, setDays] = useState("");
  const base = `admin/people/${person.id}/availability`;
  const set = (y, text) => {
    const value = Number(String(text).replace(",", "."));
    if (!Number.isFinite(value) || value < 0 || value > 366) return;
    run(() => api(`${base}/${y}`, { method: "PUT", body: { days: String(value) } }), `Availability of ${y} set.`);
  };
  return html`<section class="card admin-card" aria-label="Availability">
    <h2 class="card__title">Availability for planning</h2>
    <p class="muted admin-note">
      Days a year this person can be planned. Without an override it is the standard number of days
      times their working time.
    </p>
    <table class="admin-table admin-table--compact">
      <thead><tr><th>Year</th><th>Standard</th><th>Planned with</th>${canEdit ? html`<th>Override</th>` : null}</tr></thead>
      <tbody>
        ${person.availability.map(
          (a) => html`<tr key=${a.year}>
            <td>${a.year}</td>
            <td>${daysText(a.default_days)} d</td>
            <td><b>${daysText(a.days)} d</b>${a.override_days !== null ? html` <span class="muted">(override)</span>` : null}</td>
            ${canEdit
              ? html`<td>
                  <span class="admin-inline">
                    <input
                      class="input admin-inline__input"
                      inputmode="decimal"
                      aria-label=${`Days available in ${a.year}`}
                      placeholder=${daysText(a.default_days)}
                      value=${drafts[a.year] ?? ""}
                      onInput=${(e) => setDrafts({ ...drafts, [a.year]: e.target.value })}
                    />
                    <button type="button" class="btn" disabled=${!drafts[a.year]} onClick=${() => set(a.year, drafts[a.year])}>Set</button>
                    ${a.override_days !== null
                      ? html`<button
                          type="button"
                          class="btn btn--ghost"
                          aria-label=${`Clear the override of ${a.year}`}
                          onClick=${() => run(() => api(`${base}/${a.year}`, { method: "DELETE" }), `Override of ${a.year} cleared.`)}
                        >Clear</button>`
                      : null}
                  </span>
                </td>`
              : null}
          </tr>`,
        )}
      </tbody>
    </table>
    ${canEdit
      ? html`<form
          class="admin-inline admin-inline--form"
          onSubmit=${(e) => {
            e.preventDefault();
            set(Number(year), days);
            setYear("");
            setDays("");
          }}
        >
          <input class="input admin-inline__input" inputmode="numeric" aria-label="Another year" placeholder="Year" value=${year} onInput=${(e) => setYear(e.target.value)} />
          <input class="input admin-inline__input" inputmode="decimal" aria-label="Days for that year" placeholder="Days" value=${days} onInput=${(e) => setDays(e.target.value)} />
          <button type="submit" class="btn" disabled=${!/^\d{4}$/.test(year) || !days}>Add override</button>
        </form>`
      : null}
  </section>`;
}

function SignIn({ ctx, person, run }) {
  const [username, setUsername] = useState(person.username ?? "");
  const [email, setEmail] = useState(person.email ?? "");
  const [choose, setChoose] = useState(false);
  const [password, setPassword] = useState("");
  const [secret, setSecret] = useState(null);
  const [asking, setAsking] = useState(null);
  const base = `admin/people/${person.id}`;
  const suspended = person.status === "suspended";

  const save = (event) => {
    event.preventDefault();
    run(
      () =>
        api(`${base}/sign-in`, {
          method: "PATCH",
          body: { username: username.trim() || null, email: email.trim() || null },
        }),
      "Sign-in saved.",
    );
  };
  const setPasswordNow = async () => {
    const result = await run(
      async () => {
        const out = await api(`${base}/password`, { method: "POST", body: choose ? { password } : {} });
        if (out.generated_password) setSecret(out.generated_password);
        setPassword("");
        return api(base);
      },
      "Password set. It must be changed at the next sign-in.",
    );
    return result;
  };
  return html`<section class="card admin-card" aria-label="Sign-in">
    <h2 class="card__title">Sign-in</h2>
    <form class="form admin-form" onSubmit=${save}>
      <div class="admin-pair">
        <label class="field">
          <span class="field__label">Username</span>
          <input class="input" value=${username} maxlength="100" autocomplete="off" onInput=${(e) => setUsername(e.target.value)} />
        </label>
        <button type="button" class="btn btn--ghost admin-pair__button" onClick=${() => setUsername(suggestUsername(person.name))}>
          Suggest
        </button>
      </div>
      <label class="field">
        <span class="field__label">Email (single sign-on matches people on it)</span>
        <input class="input" type="email" value=${email} maxlength="254" autocomplete="off" onInput=${(e) => setEmail(e.target.value)} />
      </label>
      <div><button class="btn btn--dark" type="submit">Save sign-in</button></div>
    </form>
    ${person.identities?.length
      ? html`<div class="admin-block">
          <span class="field__label">Single sign-on</span>
          <ul class="admin-assignments">
            ${person.identities.map(
              (i) => html`<li key=${i.provider} class="admin-assignment">
                <span><b>${i.provider}</b>${i.last_seen_at ? ` · last seen ${i.last_seen_at.slice(0, 10)}` : ""}${i.groups.length ? ` · groups: ${i.groups.join(", ")}` : ""}</span>
              </li>`,
            )}
          </ul>
        </div>`
      : null}

    <div class="admin-block">
      <span class="field__label">Password</span>
      <p class="muted admin-note">
        ${person.has_password ? "Has a password." : "No password yet."}
        ${person.must_change_password ? " It must be changed at the next sign-in." : ""}
        ${person.last_login_at ? ` Last signed in ${person.last_login_at.slice(0, 10)}.` : ""}
      </p>
      <label class="check-row">
        <input type="checkbox" checked=${choose} onChange=${(e) => setChoose(e.target.checked)} />
        Choose the password myself
      </label>
      ${choose
        ? html`<label class="field">
            <span class="field__label">Password (at least 10 characters)</span>
            <input class="input" type="password" autocomplete="new-password" value=${password} onInput=${(e) => setPassword(e.target.value)} />
          </label>`
        : null}
      <div>
        <button type="button" class="btn" disabled=${!person.username || (choose && password.length < 10)} onClick=${setPasswordNow}>
          ${choose ? "Set password" : "Generate a new password"}
        </button>
        ${!person.username ? html`<span class="field__hint"> Give the person a username first.</span>` : null}
      </div>
      ${secret ? html`<${SecretBox} password=${secret} onDone=${() => setSecret(null)} />` : null}
    </div>

    <div class="admin-block">
      <span class="field__label">Sign-in status</span>
      <p class="muted admin-note">
        ${suspended
          ? "Signing in is suspended: the person cannot sign in, but still counts in planning."
          : "Suspending ends the person's sessions at their next request; they still count in planning."}
      </p>
      <div>
        ${suspended
          ? html`<button type="button" class="btn" onClick=${() => run(() => api(`${base}/status`, { method: "PUT", body: { status: "active" } }), "Sign-in restored.")}>Restore sign-in</button>`
          : html`<button type="button" class="btn btn--danger" disabled=${person.status === "deactivated" || person.id === ctx.me.id} onClick=${() => setAsking("suspend")}>Suspend sign-in</button>`}
      </div>
    </div>
    ${asking === "suspend"
      ? html`<${ConfirmDialog}
          title=${`Suspend ${person.name}?`}
          confirmLabel="Suspend sign-in"
          onClose=${() => setAsking(null)}
          onConfirm=${() => run(() => api(`${base}/status`, { method: "PUT", body: { status: "suspended" } }), "Sign-in suspended.")}
        >
          <p>They are signed out at once and cannot sign in until you restore it.</p>
        <//>`
      : null}
  </section>`;
}

function Access({ ctx, person, run }) {
  const [roles, setRoles] = useState([]);
  const options = useMemo(() => scopeOptions(ctx.tree), [ctx.tree]);
  const [role, setRole] = useState("");
  const [scope, setScope] = useState("global");

  useEffect(() => {
    api("admin/roles").then((found) => {
      setRoles(found);
      setRole((current) => current || found[0]?.key || "");
    });
  }, []);

  const base = `admin/people/${person.id}/assignments`;
  const grant = () =>
    run(() => api(base, { method: "POST", body: { role_key: role, ...parseScope(scope) } }), "Access granted.");
  return html`<section class="card admin-card" aria-label="Access">
    <h2 class="card__title">Access</h2>
    <p class="muted admin-note">
      On top of the default access everyone signed in has. A role applies to a branch and everything below it.
    </p>
    <ul class="admin-assignments">
      ${person.assignments.length === 0 ? html`<li class="muted">No roles of their own.</li>` : null}
      ${person.assignments.map(
        (a) => html`<li key=${a.id} class="admin-assignment">
          <span><b>${a.role_name}</b> · ${a.scope_label}</span>
          <button
            type="button"
            class="btn btn--ghost"
            aria-label=${`Remove ${a.role_name} (${a.scope_label})`}
            onClick=${() => run(() => api(`${base}/${a.id}`, { method: "DELETE" }), "Access removed.")}
          >Remove</button>
        </li>`,
      )}
    </ul>
    <div class="admin-inline admin-inline--form">
      <label class="field">
        <span class="field__label">Role</span>
        <select class="select" value=${role} onChange=${(e) => setRole(e.target.value)}>
          ${roles.map((r) => html`<option key=${r.key} value=${r.key} selected=${r.key === role}>${r.name}</option>`)}
        </select>
      </label>
      <label class="field">
        <span class="field__label">Where</span>
        <select class="select" value=${scope} onChange=${(e) => setScope(e.target.value)}>
          ${options.map((o) => html`<option key=${o.value} value=${o.value} selected=${o.value === scope}>${o.label}</option>`)}
        </select>
      </label>
      <button type="button" class="btn btn--dark admin-inline__go" disabled=${!role} onClick=${grant}>Grant</button>
    </div>
  </section>`;
}

function PersonTokens({ ctx, person }) {
  const [tokens, setTokens] = useState(null);
  const load = useCallback(async () => {
    try {
      setTokens(await api(`admin/people/${person.id}/tokens`));
    } catch {
      setTokens([]);
    }
  }, [person.id]);
  useEffect(() => {
    load();
  }, [load]);
  const revoke = async (token) => {
    try {
      await api(`admin/people/${person.id}/tokens/${token.id}`, { method: "DELETE" });
      ctx.toast(`${token.name} revoked.`);
      await load();
    } catch (failure) {
      ctx.toast(messageOf(failure), "error");
    }
  };
  return html`<section class="card admin-card" aria-label="API tokens">
    <h2 class="card__title">API tokens</h2>
    <p class="muted admin-note">Tokens let an AI agent or a script act as this person. Revoke one that is not needed.</p>
    <ul class="admin-assignments">
      ${tokens === null ? html`<li class="muted">Loading…</li>` : null}
      ${tokens && tokens.length === 0 ? html`<li class="muted">None.</li>` : null}
      ${(tokens ?? []).map(
        (t) => html`<li key=${t.id} class="admin-assignment">
          <span><b>${t.name}</b> · ${scopeLabel(t.scope)} · ${expiryText(t)} · ${lastUsedText(t)}</span>
          <button type="button" class="btn btn--ghost" aria-label=${`Revoke ${t.name}`} onClick=${() => revoke(t)}>Revoke</button>
        </li>`,
      )}
    </ul>
  </section>`;
}

function Lifecycle({ person, run, ctx }) {
  const [asking, setAsking] = useState(false);
  const gone = person.status === "deactivated";
  const base = `admin/people/${person.id}`;
  return html`<section class="card admin-card" aria-label="Employment">
    <h2 class="card__title">${gone ? "Deactivated" : "Leaving"}</h2>
    <p class="muted admin-note">
      ${gone
        ? "This person has left: no sign-in, out of pickers and planning rows. Their projects, time and remarks stay."
        : "A person who has left is deactivated, never deleted: they cannot sign in and leave pickers and planning rows. Their projects, time and remarks stay."}
    </p>
    ${gone
      ? html`<div><button type="button" class="btn" onClick=${() => run(() => api(`${base}/reactivate`, { method: "POST" }), "Reactivated.")}>Reactivate</button></div>`
      : html`<div><button type="button" class="btn btn--danger" disabled=${person.id === ctx.me.id} onClick=${() => setAsking(true)}>Deactivate</button></div>`}
    ${asking
      ? html`<${ConfirmDialog}
          title=${`Deactivate ${person.name}?`}
          confirmLabel="Deactivate"
          onClose=${() => setAsking(false)}
          onConfirm=${() => run(() => api(`${base}/deactivate`, { method: "POST" }), "Deactivated.")}
        >
          <p>They are signed out and leave pickers and planning rows. Their history stays.</p>
        <//>`
      : null}
  </section>`;
}

export function PersonPage({ ctx, id }) {
  const { me, toast } = ctx;
  const [person, setPerson] = useState(null);
  const [error, setError] = useState("");
  const manageOrg = me.permissions["org.manage"].everywhere;
  const manageUsers = me.permissions["users.manage"].everywhere;

  useEffect(() => {
    let cancelled = false;
    setPerson(null);
    api(`admin/people/${id}`)
      .then((found) => !cancelled && setPerson(found))
      .catch((failure) => !cancelled && setError(messageOf(failure)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  /** Run a change; its answer is the person again. Other screens learn of it by a reload. */
  const run = useCallback(
    async (request, message) => {
      try {
        const result = await request();
        if (result && result.id === id) setPerson(result);
        await ctx.reload();
        if (message) toast(message);
        return result;
      } catch (failure) {
        toast(messageOf(failure), "error");
        return null;
      }
    },
    [id, ctx, toast],
  );

  if (error) return html`<div class="empty" role="alert">${error}</div>`;
  if (!person) return html`<div class="muted">Loading…</div>`;
  return html`<div class="admin-person-page">
    <div class="admin-person-head">
      <${Link} class="btn btn--ghost" href=${buildUrl({ view: "admin", section: "people", id: null })}>← People<//>
      <${Avatar} person=${{ name: person.name, hue: person.hue }} size=${40} />
      <div>
        <h2 class="admin-person-head__name">${person.name}</h2>
        <span class="muted">${person.job_title ?? "No job title"} · ${placeOf(ctx.tree, person.org_node_id)}</span>
      </div>
      <${StatusChip} status=${person.status} />
    </div>
    <div class="admin-person-grid">
      <${Details} key=${`d${person.name}${person.hue}${person.org_node_id}${person.work_minutes.join()}`} ctx=${ctx} person=${person} run=${run} canEdit=${manageOrg} />
      <${Availability} person=${person} run=${run} canEdit=${manageOrg} />
      ${manageUsers ? html`<${SignIn} key=${`s${person.username}${person.email}`} ctx=${ctx} person=${person} run=${run} />` : null}
      ${manageUsers ? html`<${Access} ctx=${ctx} person=${person} run=${run} />` : null}
      ${manageUsers ? html`<${PersonTokens} ctx=${ctx} person=${person} />` : null}
      ${manageOrg ? html`<${Lifecycle} ctx=${ctx} person=${person} run=${run} />` : null}
    </div>
  </div>`;
}
