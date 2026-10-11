// First run: the organisation tree is empty, so an administrator names it (its root) before anything else.
import { useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { html } from "../html.js";
import { canSetUpOrganisation } from "../lib/admin.js";

export function SetupView({ me, reload, logout, toast }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const allowed = canSetUpOrganisation(me.permissions);

  const create = async (event) => {
    event.preventDefault();
    const text = name.trim();
    if (!text || busy) return;
    setBusy(true);
    setFailure("");
    try {
      await api("admin/org", { method: "POST", body: { name: text } });
      toast("Organisation created. Add departments and people under Administration.");
      await reload();
    } catch (error) {
      setFailure(messageOf(error));
      setBusy(false);
    }
  };

  return html`<main class="setup" id="content">
    <span class="eyebrow">MoMaTo</span>
    <h1 class="setup__title">${allowed ? "Set up your organisation" : "Not set up yet"}</h1>
    ${allowed
      ? html`<form class="card setup__card" onSubmit=${create}>
          <p class="muted setup__note">
            MoMaTo starts empty. Name the organisation: it becomes the top of the tree that
            projects, people and rights hang from. You add departments and people next.
          </p>
          <label class="field">
            <span class="field__label">Name of the organisation</span>
            <input
              class="input"
              value=${name}
              maxlength="200"
              required
              autofocus
              autocomplete="organization"
              onInput=${(e) => setName(e.target.value)}
            />
          </label>
          ${failure ? html`<p class="field__error" role="alert">${failure}</p>` : null}
          <div class="setup__actions">
            <button type="submit" class="btn btn--dark" disabled=${busy || !name.trim()}>
              Create the organisation
            </button>
            <button type="button" class="btn btn--ghost" onClick=${logout}>Sign out</button>
          </div>
        </form>`
      : html`<div class="card setup__card">
          <p class="muted setup__note">
            MoMaTo has no organisation yet. An administrator has to create it first; sign in
            again afterwards.
          </p>
          <div class="setup__actions">
            <button type="button" class="btn btn--ghost" onClick=${logout}>Sign out</button>
          </div>
        </div>`}
  </main>`;
}
