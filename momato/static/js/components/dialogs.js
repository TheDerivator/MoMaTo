// Dialogs and sheets: sign in, appearance, new project (AUTH-1, APP-1, PL-8).
import { useEffect, useId, useLayoutEffect, useRef, useState } from "preact/hooks";

import { ApiError, api, messageOf } from "../api.js";
import { html } from "../html.js";
import { LOOKS } from "../lib/appearance.js";
import { ssoStartUrl, windowsSignInMessage } from "../lib/signin.js";
import { windowsSignIn } from "../windows-signin.js";
import { Link } from "../router.js";
import { useDismiss } from "./ui.js";

const openDialogs = []; // the dialogs on screen, the last one on top

/** Keep Tab inside the topmost dialog and close it on Escape, wherever the focus is. */
function useDialogKeys(ref, onClose) {
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    openDialogs.push(node);
    const focusable = () =>
      [...node.querySelectorAll("button, input, select, textarea, a[href]")].filter(
        (el) => !el.disabled && el.offsetParent !== null,
      );
    const onKey = (event) => {
      if (openDialogs[openDialogs.length - 1] !== node) return;
      if (event.key === "Escape" && onClose) {
        event.stopPropagation();
        onClose();
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      openDialogs.splice(openDialogs.indexOf(node), 1);
    };
  }, [ref, onClose]);
}

export function Dialog({ title, onClose, children, label }) {
  const ref = useRef(null);
  const titleId = useId();
  useDialogKeys(ref, onClose);
  useLayoutEffect(() => {
    const first = ref.current?.querySelector("input, select, textarea, button");
    first?.focus();
  }, []);
  return html`<div class="backdrop" onMouseDown=${(e) => e.target === e.currentTarget && onClose?.()}>
    <div ref=${ref} class="dialog" role="dialog" aria-modal="true" aria-labelledby=${titleId} aria-label=${label}>
      <h2 class="dialog__title" id=${titleId}>${title}</h2>
      ${children}
    </div>
  </div>`;
}

// ------------------------------------------------------------------ sign in

/** "Sign in with Microsoft" etc. (a redirect that returns to this page) and "with Windows". */
function SsoButtons({ login, busy, onWindows }) {
  const providers = login?.providers ?? [];
  if (!providers.length && !login?.windows) return null;
  const next = location.pathname + location.search;
  return html`<div class="sso-buttons">
    ${login.windows
      ? html`<button type="button" class="btn" disabled=${busy} onClick=${onWindows}>Sign in with Windows</button>`
      : null}
    ${providers.map(
      (p) => html`<a
        key=${p.name}
        class="btn"
        href=${ssoStartUrl(p.name, next, document.baseURI.replace(/[^/]*$/, ""))}
        >Sign in with ${p.display_name}</a
      >`,
    )}
    <p class="muted sso-buttons__or">or with a MoMaTo account</p>
  </div>`;
}

/**
 * `login` is the server's sign-in options (SSO providers, Windows); `notice` a reason the last
 * sign-in did not work (what an SSO round trip brought back).
 */
export function LoginDialog({ onSignedIn, onClose, login = null, notice = "" }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(notice);
  const [busy, setBusy] = useState(false);

  const viaWindows = async () => {
    setBusy(true);
    setError("");
    try {
      await windowsSignIn();
      onSignedIn();
    } catch (failure) {
      setError(windowsSignInMessage(failure));
      setBusy(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("auth/login", { method: "POST", body: { username, password } });
      onSignedIn();
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status === 429
          ? "Too many attempts. Try again in a few minutes."
          : failure instanceof ApiError && failure.status === 401
            ? "Unknown username or wrong password."
            : messageOf(failure),
      );
      setBusy(false);
    }
  };

  return html`<${Dialog} title="Log in" onClose=${onClose}>
    <form class="form" onSubmit=${submit}>
      <${SsoButtons} login=${login} busy=${busy} onWindows=${viaWindows} />
      <label class="field">
        <span class="field__label">Username</span>
        <input class="input" value=${username} onInput=${(e) => setUsername(e.target.value)} autocomplete="username" required />
      </label>
      <label class="field">
        <span class="field__label">Password</span>
        <input
          class="input"
          type="password"
          value=${password}
          onInput=${(e) => setPassword(e.target.value)}
          autocomplete="current-password"
          required
        />
      </label>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions">
        <button class="btn btn--dark" type="submit" disabled=${busy}>Log in</button>
      </div>
    </form>
  <//>`;
}

/** The password change a person must make before anything else (AUTH-1). */
export function PasswordDialog({ onChanged, onLogout }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    try {
      await api("auth/password", { method: "POST", body: { current_password: current, new_password: next } });
      onChanged();
    } catch (failure) {
      setError(messageOf(failure));
    }
  };
  return html`<${Dialog} title="Choose a new password">
    <form class="form" onSubmit=${submit}>
      <p class="muted">You need to set a new password before you continue.</p>
      <label class="field">
        <span class="field__label">Current password</span>
        <input class="input" type="password" value=${current} onInput=${(e) => setCurrent(e.target.value)} autocomplete="current-password" required />
      </label>
      <label class="field">
        <span class="field__label">New password (at least 10 characters)</span>
        <input class="input" type="password" value=${next} onInput=${(e) => setNext(e.target.value)} autocomplete="new-password" required />
      </label>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" onClick=${onLogout}>Log out</button>
        <button class="btn btn--dark" type="submit">Change password</button>
      </div>
    </form>
  <//>`;
}

// ------------------------------------------------------------------ appearance (APP-1)

export function AppearanceSheet({ ctx, onClose }) {
  const { appearance, setAppearance, resolvedMode, me, logout } = ctx;
  const ref = useRef(null);
  useDismiss(ref, true, onClose);
  const mode = appearance.mode ?? resolvedMode;
  const labels = { playful: "Playful", boring: "Boring" };
  const administers = ["org.manage", "users.manage"].some((p) => me.permissions[p]?.everywhere);
  return html`<div ref=${ref} class="sheet" role="dialog" aria-label="Appearance">
    <span class="sheet__title">Appearance</span>
    <div class="sheet__group">
      <span class="eyebrow">Mode</span>
      <div class="segmented" role="group" aria-label="Mode">
        ${["light", "dark"].map(
          (value) => html`<button
            key=${value}
            aria-pressed=${mode === value ? "true" : "false"}
            onClick=${() => setAppearance({ ...appearance, mode: value })}
          >
            ${value === "light" ? "Light" : "Dark"}
          </button>`,
        )}
      </div>
    </div>
    <div class="sheet__group">
      <span class="eyebrow">Style</span>
      <div class="segmented" role="group" aria-label="Style">
        ${LOOKS.map(
          (value) => html`<button
            key=${value}
            aria-pressed=${appearance.look === value ? "true" : "false"}
            onClick=${() => setAppearance({ ...appearance, look: value })}
          >
            ${labels[value]}
          </button>`,
        )}
      </div>
      <span class="sheet__note"
        >Playful: soft colours, rounded shapes. Boring: muted palette, tighter corners, one plain typeface.</span
      >
    </div>
    <label class="switch-row">
      <input
        type="checkbox"
        checked=${appearance.celebrate}
        onChange=${(e) => setAppearance({ ...appearance, celebrate: e.target.checked })}
      />
      Celebrate submitted weeks
    </label>
    ${me.is_anonymous
      ? html`<button class="btn btn--dark" onClick=${() => { onClose(); ctx.openLogin(); }}>Log in</button>`
      : html`
          <${Link} class="sheet__link" href="profile" onNavigate=${onClose}>Profile<//>
          ${administers
            ? html`<${Link} class="sheet__link" href="admin" onNavigate=${onClose}>Administration<//>`
            : null}
          ${me.signed_in_by
            ? html`<span class="sheet__note">Signed in by ${me.signed_in_by}.</span>`
            : html`<button class="btn" onClick=${logout}>Log out</button>`}
        `}
  </div>`;
}

// ------------------------------------------------------------------ person picker

/** Choose a person with a server-side search (SH-12). */
export function PersonPicker({ label, value, onChange, required = false }) {
  const [text, setText] = useState(value?.name ?? "");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const listId = useId();
  const inputId = useId();
  const timer = useRef(0);

  useEffect(() => setText(value?.name ?? ""), [value?.id]);

  const search = (query) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      try {
        setResults(await api("search/people", { params: { q: query } }));
        setOpen(true);
      } catch {
        setResults([]);
      }
    }, 150);
  };

  return html`<div class="field picker">
    <label class="field__label" for=${inputId}>${label}</label>
    <input
      id=${inputId}
      class="input"
      role="combobox"
      aria-expanded=${open ? "true" : "false"}
      aria-controls=${listId}
      aria-autocomplete="list"
      value=${text}
      required=${required && !value}
      onFocus=${() => search(text === value?.name ? "" : text)}
      onInput=${(e) => {
        setText(e.target.value);
        onChange(null);
        search(e.target.value);
      }}
      onKeyDown=${(e) => e.key === "Escape" && open && (e.stopPropagation(), setOpen(false))}
    />
    ${open
      ? html`<div class="picker__results" id=${listId} role="listbox" aria-label=${`${label} results`}>
          ${results.length === 0 ? html`<div class="empty" role="option" aria-selected="false">No one found.</div>` : null}
          ${results.map(
            (p) => html`<button
              type="button"
              role="option"
              aria-selected="false"
              class="menu-item"
              key=${p.id}
              onClick=${() => {
                onChange(p);
                setText(p.name);
                setOpen(false);
              }}
            >
              <span class="menu-item__name">${p.name}</span>
              <span class="menu-item__count">${p.job_title ?? ""}</span>
            </button>`,
          )}
        </div>`
      : null}
  </div>`;
}

// ------------------------------------------------------------------ new project (PL-8)

export function NewProjectDialog({ ctx, onClose, onCreated }) {
  const { boot, tree, selectedNode, me } = ctx;
  const editable = editableNodes(me, tree);
  const defaultNode = editable.some((n) => n.id === selectedNode) ? selectedNode : editable[0]?.id;
  const [name, setName] = useState("");
  const [node, setNode] = useState(defaultNode);
  const [coordinator, setCoordinator] = useState(
    me.person_id ? { id: me.person_id, name: me.name } : null,
  );
  const [start, setStart] = useState(boot.today);
  const [end, setEnd] = useState(addMonths(boot.today, 6));
  const [status, setStatus] = useState("idea");
  const [goal, setGoal] = useState("");
  const [template, setTemplate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (!coordinator) {
      setError("Choose a coordinator.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const project = await api("projects", {
        method: "POST",
        body: {
          name,
          org_node_id: Number(node),
          coordinator_id: coordinator.id,
          start_date: start,
          end_date: end,
          status,
          goal,
          use_template: template,
        },
      });
      onCreated(project);
    } catch (failure) {
      setError(messageOf(failure));
      setBusy(false);
    }
  };

  return html`<${Dialog} title="New project" onClose=${onClose}>
    <form class="form" onSubmit=${submit}>
      <label class="field">
        <span class="field__label">Name</span>
        <input class="input" value=${name} onInput=${(e) => setName(e.target.value)} required maxlength="200" />
      </label>
      <label class="field">
        <span class="field__label">Organisation node</span>
        <select class="select" value=${node} onChange=${(e) => setNode(e.target.value)} required>
          ${editable.map((n) => html`<option key=${n.id} value=${n.id} selected=${n.id === node}>${" ".repeat(n.depth * 2)}${n.name}</option>`)}
        </select>
      </label>
      <${PersonPicker} label="Coordinator" value=${coordinator} onChange=${setCoordinator} required=${true} />
      <div class="field-row">
        <label class="field">
          <span class="field__label">Start</span>
          <input class="input" type="date" value=${start} onInput=${(e) => setStart(e.target.value)} required />
        </label>
        <label class="field">
          <span class="field__label">End</span>
          <input class="input" type="date" value=${end} onInput=${(e) => setEnd(e.target.value)} required />
        </label>
      </div>
      <label class="field">
        <span class="field__label">Status</span>
        <select class="select" value=${status} onChange=${(e) => setStatus(e.target.value)}>
          ${boot.statuses.map((s) => html`<option key=${s.key} value=${s.key} selected=${s.key === status}>${s.label}</option>`)}
        </select>
      </label>
      <label class="field">
        <span class="field__label">Goal</span>
        <textarea class="textarea" value=${goal} onInput=${(e) => setGoal(e.target.value)}></textarea>
      </label>
      <label class="check-row">
        <input type="checkbox" checked=${template} onChange=${(e) => setTemplate(e.target.checked)} />
        Start with the standard phases
      </label>
      ${error ? html`<div class="field__error" role="alert">${error}</div>` : null}
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" onClick=${onClose}>Cancel</button>
        <button class="btn btn--dark" type="submit" disabled=${busy}>Create project</button>
      </div>
    </form>
  <//>`;
}

/** The nodes where the person may create projects: where `project.edit` reaches (PL-8). */
export function editableNodes(me, tree) {
  const reach = me.permissions["project.edit"];
  const result = [];
  const allowed = (id, inside) => inside || reach.everywhere || reach.node_ids.includes(id);
  const walk = (node, inside) => {
    const ok = allowed(node.id, inside);
    if (ok) result.push(node);
    node.children.forEach((child) => walk(child, ok));
  };
  if (tree.root) walk(tree.root, false);
  return result;
}

// ------------------------------------------------------------------ confirming

/** "Are you sure?" for removals that take other things with them (PD-4, D-032, RM-5). */
export function ConfirmDialog({ title, children, confirmLabel = "Delete", onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
      onClose();
    }
  };
  return html`<${Dialog} title=${title} onClose=${onClose}>
    <div class="form">
      <div class="confirm__text">${children}</div>
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" onClick=${onClose}>Cancel</button>
        <button class="btn btn--dark" type="button" disabled=${busy} onClick=${confirm}>${confirmLabel}</button>
      </div>
    </div>
  <//>`;
}

function addMonths(iso, months) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + months, day));
  return date.toISOString().slice(0, 10);
}
