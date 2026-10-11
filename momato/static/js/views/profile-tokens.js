// Profile › API tokens: create one (shown once), see what it was used for, revoke it (TOK-1, TOK-4).
import { useCallback, useEffect, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { ConfirmDialog, Dialog } from "../components/dialogs.js";
import { html } from "../html.js";
import { formatDate } from "../lib/format.js";
import { DEFAULT_EXPIRY, EXPIRY_CHOICES, SCOPES, envCommands, expiryText, lastUsedText, scopeLabel } from "../lib/tokens.js";

const GUIDE_FILE = "momato-agent-guide.md";

function GuideLink() {
  return html`<a class="btn" href="api/agent-guide" download=${GUIDE_FILE}>Download the agent guide</a>`;
}

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      window.prompt("Copy this:", text);
    }
  };
  return html`<button type="button" class="btn" aria-label=${label} onClick=${copy}>${copied ? "Copied" : "Copy"}</button>`;
}

function NewTokenDialog({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [scope, setScope] = useState("read");
  const [expires, setExpires] = useState(String(DEFAULT_EXPIRY));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const created = await api("auth/tokens", {
        method: "POST",
        body: { name: name.trim(), scope, expires_in_days: expires === "" ? null : Number(expires) },
      });
      onCreated(created);
    } catch (failure) {
      setError(messageOf(failure));
      setBusy(false);
    }
  };

  return html`<${Dialog} title="New API token" onClose=${onClose}>
    <form class="form" onSubmit=${submit}>
      <label class="field">
        <span class="field__label">Name</span>
        <input
          class="input"
          value=${name}
          required
          maxlength="100"
          placeholder="Claude Code on my laptop"
          onInput=${(e) => setName(e.target.value)}
        />
        <span class="field__hint">Shown next to everything the agent writes ("via …"): name the agent or the script.</span>
      </label>
      <fieldset class="token-scopes">
        <legend class="field__label">Access</legend>
        ${SCOPES.map(
          (s) => html`<label key=${s.value} class="check-row token-scope">
            <input type="radio" name="scope" checked=${scope === s.value} onChange=${() => setScope(s.value)} />
            <span><b>${s.label}</b><span class="muted"> ${s.hint}</span></span>
          </label>`,
        )}
      </fieldset>
      <label class="field">
        <span class="field__label">Expires after</span>
        <select class="select" value=${expires} onChange=${(e) => setExpires(e.target.value)}>
          ${EXPIRY_CHOICES.map((c) => html`<option key=${c.label} value=${c.days ?? ""} selected=${String(c.days ?? "") === expires}>${c.label}</option>`)}
        </select>
      </label>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions">
        <button type="button" class="btn btn--ghost" onClick=${onClose}>Cancel</button>
        <button type="submit" class="btn btn--dark" disabled=${busy || !name.trim()}>Create token</button>
      </div>
    </form>
  <//>`;
}

/** The new token, once: copy it, put it where the agent looks, hand over the guide. */
function TokenCreatedDialog({ created, onClose }) {
  return html`<${Dialog} title="Your new token" onClose=${onClose}>
    <div class="form">
      <p>
        Copy it now: it is not shown again. Anyone who has it can act as you
        (${scopeLabel(created.token.scope).toLowerCase()}) until it expires or you revoke it.
      </p>
      <div class="admin-secret">
        <code class="admin-secret__value" data-testid="token-secret">${created.secret}</code>
        <div class="admin-secret__actions"><${CopyButton} text=${created.secret} label="Copy the token" /></div>
      </div>
      <p>
        Store it in the <code>MOMATO_TOKEN</code> environment variable on the computer where the agent
        runs, rather than pasting it into a chat:
      </p>
      ${envCommands(created.secret).map(
        (c) => html`<div key=${c.shell} class="token-command">
          <span class="field__label">${c.shell}</span>
          <div class="admin-inline">
            <code class="token-command__code">${c.command}</code>
            <${CopyButton} text=${c.command} label=${`Copy the command for ${c.shell}`} />
          </div>
        </div>`,
      )}
      <p>Then give the agent the guide. It explains the API and how to use the token, and holds no token itself.</p>
      <div class="dialog__actions">
        <${GuideLink} />
        <button type="button" class="btn btn--dark" onClick=${onClose}>Done</button>
      </div>
    </div>
  <//>`;
}

export function TokensCard({ ctx }) {
  const { toast } = ctx;
  const [tokens, setTokens] = useState(null);
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState(null);
  const [revoking, setRevoking] = useState(null);

  const load = useCallback(async () => {
    try {
      setTokens(await api("auth/tokens"));
    } catch (failure) {
      toast(messageOf(failure), "error");
      setTokens([]);
    }
  }, [toast]);
  useEffect(() => {
    load();
  }, [load]);

  const revoke = async () => {
    const token = revoking;
    try {
      await api(`auth/tokens/${token.id}`, { method: "DELETE" });
      toast(`${token.name} revoked.`);
      await load();
    } catch (failure) {
      toast(messageOf(failure), "error");
    }
  };

  return html`<section class="card admin-card" aria-label="API tokens">
    <div class="admin-toolbar">
      <h2 class="card__title">API tokens</h2>
      <span class="admin-toolbar__spacer"></span>
      <${GuideLink} />
      <button type="button" class="btn btn--dark" onClick=${() => setCreating(true)}>New token</button>
    </div>
    <p class="muted admin-note">
      A token lets an AI agent or a script work in MoMaTo as you, with your rights (never administration).
      What it writes shows as yours, marked "via" the token's name.
    </p>
    ${tokens === null ? html`<div class="muted">Loading…</div>` : null}
    ${tokens && tokens.length === 0 ? html`<div class="empty">No tokens yet.</div>` : null}
    ${tokens && tokens.length
      ? html`<div class="admin-scroll">
          <table class="admin-table">
            <thead>
              <tr><th>Name</th><th>Access</th><th>Created</th><th>Expires</th><th>Last used</th><th><span class="visually-hidden">Revoke</span></th></tr>
            </thead>
            <tbody>
              ${tokens.map(
                (t) => html`<tr key=${t.id}>
                  <td><b>${t.name}</b><br /><span class="muted">${t.prefix}…</span></td>
                  <td>${scopeLabel(t.scope)}</td>
                  <td>${formatDate(t.created_at.slice(0, 10))}</td>
                  <td>${expiryText(t)}</td>
                  <td title=${t.last_used_ip ? `From ${t.last_used_ip}` : undefined}>${lastUsedText(t)}</td>
                  <td>
                    <button type="button" class="btn btn--ghost btn--danger" onClick=${() => setRevoking(t)}>
                      ${t.expired ? "Remove" : "Revoke"}
                    </button>
                  </td>
                </tr>`,
              )}
            </tbody>
          </table>
        </div>`
      : null}
    ${creating
      ? html`<${NewTokenDialog}
          onClose=${() => setCreating(false)}
          onCreated=${(result) => {
            setCreating(false);
            setCreated(result);
            load();
          }}
        />`
      : null}
    ${created ? html`<${TokenCreatedDialog} created=${created} onClose=${() => setCreated(null)} />` : null}
    ${revoking
      ? html`<${ConfirmDialog}
          title=${`Revoke “${revoking.name}”?`}
          confirmLabel=${revoking.expired ? "Remove" : "Revoke"}
          onClose=${() => setRevoking(null)}
          onConfirm=${revoke}
        >
          <p>Whatever uses this token stops working at its next request. What it wrote stays.</p>
        <//>`
      : null}
  </section>`;
}
