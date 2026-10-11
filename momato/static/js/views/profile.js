// Profile: one's own data and availability (read only) and a new password (ADM-8, AUTH-1).
import { useEffect, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { Avatar } from "../components/ui.js";
import { html } from "../html.js";
import { daysText, patternSummary } from "../lib/admin.js";
import { TokensCard } from "./profile-tokens.js";

function ChangePassword({ ctx }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (next !== again) return setError("The two new passwords are not the same.");
    setBusy(true);
    try {
      await api("auth/password", { method: "POST", body: { current_password: current, new_password: next } });
      setCurrent("");
      setNext("");
      setAgain("");
      setError("");
      ctx.toast("Password changed. Your other sessions are signed out.");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  };
  return html`<section class="card admin-card" aria-label="Change password">
    <h2 class="card__title">Change password</h2>
    <form class="form admin-form" onSubmit=${submit}>
      <label class="field">
        <span class="field__label">Current password</span>
        <input class="input" type="password" autocomplete="current-password" value=${current} required onInput=${(e) => setCurrent(e.target.value)} />
      </label>
      <label class="field">
        <span class="field__label">New password (at least 10 characters)</span>
        <input class="input" type="password" autocomplete="new-password" value=${next} required onInput=${(e) => setNext(e.target.value)} />
      </label>
      <label class="field">
        <span class="field__label">New password again</span>
        <input class="input" type="password" autocomplete="new-password" value=${again} required onInput=${(e) => setAgain(e.target.value)} />
      </label>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div><button class="btn btn--dark" type="submit" disabled=${busy}>Change password</button></div>
    </form>
  </section>`;
}

export function ProfileView({ ctx }) {
  const [account, setAccount] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("account")
      .then(setAccount)
      .catch((failure) => setError(messageOf(failure)));
  }, [ctx.boot.people]);

  if (error) return html`<div class="page admin-page"><div class="empty" role="alert">${error}</div></div>`;
  if (!account) return html`<div class="page admin-page"><div class="muted">Loading…</div></div>`;
  return html`<div class="page admin-page">
    <div class="admin-header">
      <span class="eyebrow">Profile</span>
      <div class="admin-person-head">
        <${Avatar} person=${{ name: account.name, hue: account.hue }} size=${48} />
        <div>
          <h1 class="admin-title">${account.name}</h1>
          <span class="muted">${account.job_title ?? "No job title"}</span>
        </div>
      </div>
    </div>
    <div class="admin-person-grid">
      <section class="card admin-card" aria-label="About you">
        <h2 class="card__title">About you</h2>
        <dl class="admin-facts">
          <dt>Place</dt><dd>${account.org_path.length ? account.org_path.join(" › ") : "–"}</dd>
          <dt>Department</dt><dd>${account.department ?? "–"}</dd>
          <dt>Working time</dt><dd>${patternSummary(account.work_minutes)}</dd>
          <dt>Username</dt><dd>${account.username ?? "–"}</dd>
          <dt>Email</dt><dd>${account.email ?? "–"}</dd>
        </dl>
        <p class="muted admin-note">An administrator keeps these up to date.</p>
      </section>
      <section class="card admin-card" aria-label="Availability">
        <h2 class="card__title">Availability for planning</h2>
        <table class="admin-table admin-table--compact">
          <thead><tr><th>Year</th><th>Planned with</th></tr></thead>
          <tbody>
            ${account.availability.map(
              (a) => html`<tr key=${a.year}>
                <td>${a.year}</td>
                <td><b>${daysText(a.days)} d</b>${a.override_days !== null ? html` <span class="muted">(set by an administrator)</span>` : null}</td>
              </tr>`,
            )}
          </tbody>
        </table>
      </section>
      ${account.password_sign_in ? html`<${ChangePassword} ctx=${ctx} />` : null}
      <${TokensCard} ctx=${ctx} />
    </div>
  </div>`;
}
