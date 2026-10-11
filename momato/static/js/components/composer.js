// The Markdown composer of remarks: Write / Preview, a formatting toolbar, images by button, paste
// or drop, the Done / Next steps template, Ctrl+Enter to send (RM-1, RM-2).
import { useLayoutEffect, useRef, useState } from "preact/hooks";

import { api, messageOf, upload } from "../api.js";
import { html } from "../html.js";
import { insertBlock, lineEnd, prefixLines, removeFragment, withTemplate, wrap } from "../lib/editor.js";
import { Avatar } from "./ui.js";

const TOOLS = [
  { key: "bold", label: "Bold", content: () => html`<b>B</b>` },
  { key: "italic", label: "Italic", content: () => html`<i class="serif">I</i>` },
  { key: "list", label: "Bulleted list", content: () => html`<span aria-hidden="true">•≡</span>` },
  { key: "code", label: "Code", content: () => html`<span aria-hidden="true">${"</>"}</span>` },
  { key: "link", label: "Link", content: () => html`<span aria-hidden="true">↗</span>` },
];

const ACCEPT = "image/png,image/jpeg,image/gif,image/webp";

/**
 * `uploadPath` is where images go ("projects/4102/attachments"; null: no images, as in replies).
 * `onSubmit(text)` rejects to keep the text. `draftKey` keeps an unsent draft for the session.
 */
export function Composer({
  person,
  uploadPath,
  initial = "",
  submitLabel = "Post remark",
  placeholder = "Share an update. Tip: Done / Next steps keeps it scannable.",
  label = "Write a remark",
  template = true,
  draftKey = null,
  onSubmit,
  onCancel,
  onError,
  inline = false,
}) {
  const [text, setText] = useState(() => initial || readDraft(draftKey));
  const [mode, setMode] = useState("write");
  const [preview, setPreview] = useState("");
  const [files, setFiles] = useState([]); // uploaded: { id, filename, markdown }
  const [uploading, setUploading] = useState(0);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [problem, setProblem] = useState("");
  const area = useRef(null);
  const picker = useRef(null);

  useLayoutEffect(() => writeDraft(draftKey, text), [text]);
  // An editor opened in a card takes the focus; the composer at the top of the page does not.
  useLayoutEffect(() => {
    if (inline) area.current?.focus();
  }, []);

  const apply = ({ text: next, start, end }) => {
    setText(next);
    requestAnimationFrame(() => {
      const el = area.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    });
  };
  const selection = () => {
    const el = area.current;
    return el ? [el.selectionStart, el.selectionEnd] : [text.length, text.length];
  };
  const format = (kind) => {
    const [start, end] = selection();
    if (kind === "bold") apply(wrap(text, start, end, "**", "**", "bold text"));
    if (kind === "italic") apply(wrap(text, start, end, "_", "_", "italic text"));
    if (kind === "code") apply(wrap(text, start, end, "`", "`", "code"));
    if (kind === "link") apply(wrap(text, start, end, "[", "](https://)", "link text"));
    if (kind === "list") apply(prefixLines(text, start, end, "- "));
  };

  const uploadFiles = async (list) => {
    if (!uploadPath) return;
    const images = [...list].filter((f) => f.type.startsWith("image/"));
    for (const file of images) {
      setUploading((n) => n + 1);
      try {
        const uploaded = await upload(uploadPath, file, file.name || "pasted-image.png");
        setFiles((current) => [...current, uploaded]);
        // On its own line after the caret's line, so it never splits formatted text.
        setText((current) => {
          const caret = Math.min(area.current?.selectionEnd ?? current.length, current.length);
          return insertBlock(current, lineEnd(current, caret), uploaded.markdown).text;
        });
      } catch (failure) {
        setProblem(messageOf(failure));
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  const showPreview = async () => {
    setMode("preview");
    try {
      setPreview((await api("markdown/preview", { method: "POST", body: { body_md: text } })).html);
    } catch (failure) {
      setPreview("");
      setProblem(messageOf(failure));
    }
  };

  const submit = async (event) => {
    event?.preventDefault();
    if (!text.trim() || busy || uploading) return;
    setBusy(true);
    setProblem("");
    try {
      await onSubmit(text);
      setText("");
      writeDraft(draftKey, "");
      setFiles([]);
      setMode("write");
    } catch (failure) {
      setProblem(messageOf(failure));
      onError?.(failure);
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) submit(event);
    if (event.key === "Escape" && onCancel) {
      event.stopPropagation();
      onCancel();
    }
  };

  return html`<form class=${`composer${inline ? " composer--inline" : ""}`} onSubmit=${submit}>
    ${person && !inline ? html`<${Avatar} person=${person} size=${34} />` : null}
    <div class="composer__main">
      <div
        class=${`composer__box${dragOver ? " composer__box--dragover" : ""}`}
        onDragOver=${(e) => {
          if (!uploadPath) return;
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave=${() => setDragOver(false)}
        onDrop=${(e) => {
          setDragOver(false);
          if (uploadPath && e.dataTransfer?.files?.length) {
            e.preventDefault();
            uploadFiles(e.dataTransfer.files);
          }
        }}
      >
        <div class="composer__toolbar">
          <div class="composer__modes" role="group" aria-label="Editor mode">
            <button type="button" aria-pressed=${mode === "write" ? "true" : "false"} onClick=${() => setMode("write")}>Write</button>
            <button type="button" aria-pressed=${mode === "preview" ? "true" : "false"} onClick=${showPreview}>Preview</button>
          </div>
          ${TOOLS.map(
            (tool) => html`<button
              key=${tool.key}
              type="button"
              class="composer__tool"
              aria-label=${tool.label}
              title=${tool.label}
              disabled=${mode !== "write"}
              onClick=${() => format(tool.key)}
            >
              ${tool.content()}
            </button>`,
          )}
          ${uploadPath
            ? html`<button
                  type="button"
                  class="composer__tool"
                  aria-label="Attach image"
                  title="Attach image"
                  onClick=${() => picker.current?.click()}
                >
                  <span aria-hidden="true">▣</span>
                </button>
                <input
                  ref=${picker}
                  type="file"
                  accept=${ACCEPT}
                  multiple
                  hidden
                  aria-label="Choose images"
                  onChange=${(e) => {
                    uploadFiles(e.currentTarget.files);
                    e.currentTarget.value = "";
                  }}
                />`
            : null}
        </div>
        ${mode === "write"
          ? html`<textarea
              ref=${area}
              class="composer__text"
              rows=${inline ? 3 : 4}
              aria-label=${label}
              placeholder=${placeholder}
              value=${text}
              onInput=${(e) => setText(e.currentTarget.value)}
              onKeyDown=${onKeyDown}
              onPaste=${(e) => {
                const pasted = e.clipboardData?.files;
                if (uploadPath && pasted && pasted.length) {
                  e.preventDefault();
                  uploadFiles(pasted);
                }
              }}
            ></textarea>`
          : html`<div
              class="composer__preview md"
              dangerouslySetInnerHTML=${{ __html: preview || "<p><em>Nothing to preview.</em></p>" }}
            ></div>`}
        ${files.length > 0 || uploading > 0
          ? html`<div class="composer__files">
              ${files.map(
                (f) => html`<span key=${f.id} class="file-chip">
                  ${f.filename}
                  <button
                    type="button"
                    aria-label=${`Remove ${f.filename}`}
                    onClick=${() => {
                      setFiles(files.filter((x) => x.id !== f.id));
                      setText(removeFragment(text, f.markdown));
                    }}
                  >
                    ×
                  </button>
                </span>`,
              )}
              ${uploading > 0 ? html`<span class="file-chip">Uploading…</span>` : null}
            </div>`
          : null}
      </div>
      ${problem ? html`<div class="field__error" role="alert">${problem}</div>` : null}
      <div class="composer__foot">
        ${template
          ? html`<button type="button" class="chip-button" onClick=${() => apply(withTemplate(text))}>
              Done / Next steps template
            </button>`
          : null}
        <span class="composer__hint">Markdown · Ctrl+Enter to send</span>
        <span class="composer__spacer"></span>
        ${onCancel ? html`<button type="button" class="btn btn--ghost" onClick=${onCancel}>Cancel</button>` : null}
        <button type="submit" class="btn btn--accent" disabled=${busy || uploading > 0 || !text.trim()}>
          ${submitLabel}
        </button>
      </div>
    </div>
  </form>`;
}

function readDraft(key) {
  if (!key) return "";
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeDraft(key, text) {
  if (!key) return;
  try {
    if (text) sessionStorage.setItem(key, text);
    else sessionStorage.removeItem(key);
  } catch {
    // blocked storage: the draft just does not survive a reload
  }
}
