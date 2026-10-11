// The Remarks tab: composer, remark cards newest first, replies, edit with history, delete
// (RM-1 – RM-5). Rendering is done on the server; the HTML it returns is sanitized.
import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { Composer } from "../components/composer.js";
import { ConfirmDialog } from "../components/dialogs.js";
import { Avatar, ViaBadge } from "../components/ui.js";
import { html } from "../html.js";
import { formatDate, relativeDate } from "../lib/format.js";
import { dayOf, timeOf } from "../lib/logbook.js";
import { nameVia } from "../lib/tokens.js";

function When({ at, today }) {
  const day = dayOf(at);
  return html`<time class="remark__when" datetime=${at} title=${`${formatDate(day)}, ${timeOf(at)}`}>
    ${relativeDate(day, today)}
  </time>`;
}

function History({ remark, today }) {
  const [versions, setVersions] = useState(null);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    api(`remarks/${remark.id}/history`)
      .then(setVersions)
      .catch((failure) => setProblem(messageOf(failure)));
  }, [remark.id, remark.versions]);
  if (problem) return html`<div class="field__error" role="alert">${problem}</div>`;
  if (!versions) return html`<div class="muted">Loading…</div>`;
  return html`<ol class="history" aria-label="Versions of this remark">
    ${versions.map(
      (version, index) => html`<li key=${version.rev} class="history__item">
        <div class="history__head">
          <b>${index === versions.length - 1 ? "Current" : `Version ${version.rev}`}</b>
          <span class="muted">${nameVia(version.written_by, version.via)}, ${formatDate(dayOf(version.written_at))} ${timeOf(version.written_at)}</span>
        </div>
        <div class="md" dangerouslySetInnerHTML=${{ __html: version.html }}></div>
      </li>`,
    )}
  </ol>`;
}

function ReplyBox({ onSend, onCancel }) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState("");
  const input = useRef(null);
  useEffect(() => input.current?.focus(), []);
  const send = async () => {
    if (!text.trim()) return;
    try {
      await onSend(text);
    } catch (failure) {
      setProblem(messageOf(failure));
    }
  };
  return html`<div class="reply-box">
    <textarea
      class="reply-box__input"
      rows="2"
      aria-label="Write a reply"
      placeholder="Write a reply and press Enter"
      value=${text}
      onInput=${(e) => setText(e.currentTarget.value)}
      onKeyDown=${(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          send();
        } else if (e.key === "Escape") {
          e.stopPropagation();
          onCancel();
        }
      }}
      ref=${input}
    ></textarea>
    ${problem ? html`<div class="field__error" role="alert">${problem}</div>` : null}
  </div>`;
}

function Reply({ reply, today, onChanged, askDelete }) {
  const [editing, setEditing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const save = async (text) => {
    await api(`remarks/${reply.id}`, { method: "PATCH", body: { body_md: text } });
    setEditing(false);
    await onChanged();
  };
  return html`<div class="reply">
    <${Avatar} person=${reply.author} size=${26} />
    <div class="reply__main">
      <div class="remark__who">
        <b>${reply.author.name}</b>
        <${ViaBadge} via=${reply.via} />
        <${When} at=${reply.created_at} today=${today} />
        ${reply.edited_at
          ? html`<button type="button" class="link-button remark__edited" aria-expanded=${showHistory ? "true" : "false"} onClick=${() => setShowHistory(!showHistory)}>edited</button>`
          : null}
        ${reply.can_edit && !editing
          ? html`<button type="button" class="link-button" onClick=${() => setEditing(true)}>Edit</button>`
          : null}
        ${reply.can_delete && !editing
          ? html`<button type="button" class="link-button" onClick=${() => askDelete(reply)}>Delete</button>`
          : null}
      </div>
      ${editing
        ? html`<${Composer}
            inline=${true}
            uploadPath=${null}
            template=${false}
            initial=${reply.body_md}
            submitLabel="Save"
            label="Edit reply"
            onSubmit=${save}
            onCancel=${() => setEditing(false)}
          />`
        : html`<div class="md" dangerouslySetInnerHTML=${{ __html: reply.html }}></div>`}
      ${showHistory ? html`<${History} remark=${reply} today=${today} />` : null}
    </div>
  </div>`;
}

function RemarkCard({ remark, ctx, canComment, onChanged, askDelete, uploadPath }) {
  const [editing, setEditing] = useState(false);
  const [replying, setReplying] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const today = ctx.boot.today;

  const save = async (text) => {
    await api(`remarks/${remark.id}`, { method: "PATCH", body: { body_md: text } });
    setEditing(false);
    await onChanged();
  };
  const reply = async (text) => {
    await api(`remarks/${remark.id}/replies`, { method: "POST", body: { body_md: text } });
    setReplying(false);
    await onChanged();
  };

  const replies = remark.replies.map(
    (r) => html`<${Reply} key=${r.id} reply=${r} today=${today} onChanged=${onChanged} askDelete=${askDelete} />`,
  );

  if (remark.deleted) {
    return html`<article class="remark remark--deleted" aria-label="Deleted remark">
      <div class="remark__main">
        <p class="muted remark__gone">Remark deleted</p>
        ${replies}
      </div>
    </article>`;
  }

  return html`<article class="remark" aria-label=${`Remark by ${remark.author.name}`}>
    <${Avatar} person=${remark.author} size=${36} />
    <div class="remark__main">
      <div class="remark__who">
        <b>${remark.author.name}</b>
        <${ViaBadge} via=${remark.via} />
        <${When} at=${remark.created_at} today=${today} />
        ${remark.edited_at
          ? html`<button type="button" class="link-button remark__edited" aria-expanded=${showHistory ? "true" : "false"} onClick=${() => setShowHistory(!showHistory)}>edited</button>`
          : null}
        <span class="remark__spacer"></span>
        ${remark.can_edit && !editing
          ? html`<button type="button" class="link-button" onClick=${() => setEditing(true)}>Edit</button>`
          : null}
        ${remark.can_delete && !editing
          ? html`<button type="button" class="link-button" onClick=${() => askDelete(remark)}>Delete</button>`
          : null}
      </div>
      ${editing
        ? html`<${Composer}
            inline=${true}
            uploadPath=${uploadPath}
            initial=${remark.body_md}
            submitLabel="Save"
            label="Edit remark"
            template=${false}
            onSubmit=${save}
            onCancel=${() => setEditing(false)}
          />`
        : html`<div class="md" dangerouslySetInnerHTML=${{ __html: remark.html }}></div>`}
      ${showHistory ? html`<${History} remark=${remark} today=${today} />` : null}
      ${replies}
      ${replying
        ? html`<${ReplyBox} onSend=${reply} onCancel=${() => setReplying(false)} />`
        : canComment
          ? html`<button type="button" class="link-button remark__reply" onClick=${() => setReplying(true)}>Reply</button>`
          : null}
    </div>
  </article>`;
}

export function ProjectRemarks({ ctx, project, refresh }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(null);
  const number = project.number;
  const uploadPath = `projects/${number}/attachments`;

  const load = useCallback(async () => {
    try {
      setData(await api(`projects/${number}/remarks`));
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [number]);
  useEffect(() => {
    setData(null);
    load();
  }, [number]);

  const changed = useCallback(async () => {
    await load();
    refresh();
  }, [load, refresh]);

  const post = async (text) => {
    await api(`projects/${number}/remarks`, { method: "POST", body: { body_md: text } });
    await changed();
  };

  if (error && !data) return html`<div class="empty" role="alert">${error}</div>`;
  if (!data) return html`<div class="muted">Loading…</div>`;

  return html`<div class="remarks">
    ${data.can_comment
      ? html`<${Composer}
          person=${ctx.myPerson ?? { name: ctx.me.name, hue: 285 }}
          uploadPath=${uploadPath}
          draftKey=${`momato-draft-${number}`}
          onSubmit=${post}
        />`
      : html`<p class="muted remarks__note">You can read remarks here. Members and coordinators can post.</p>`}
    ${data.items.length === 0 ? html`<p class="muted">No remarks yet.</p>` : null}
    ${data.items.map(
      (remark) => html`<${RemarkCard}
        key=${remark.id}
        remark=${remark}
        ctx=${ctx}
        canComment=${data.can_comment}
        uploadPath=${uploadPath}
        onChanged=${changed}
        askDelete=${setDeleting}
      />`,
    )}
    ${deleting
      ? html`<${ConfirmDialog}
          title=${deleting.parent_id ? "Delete this reply?" : "Delete this remark?"}
          confirmLabel="Delete"
          onClose=${() => setDeleting(null)}
          onConfirm=${async () => {
            try {
              await api(`remarks/${deleting.id}`, { method: "DELETE" });
              await changed();
            } catch (failure) {
              ctx.toast(messageOf(failure), "error");
            }
          }}
        >
          <p>
            ${deleting.parent_id || deleting.replies.length === 0
              ? "It is removed for everyone."
              : "Its replies stay, under “Remark deleted”."}
          </p>
        <//>`
      : null}
  </div>`;
}
