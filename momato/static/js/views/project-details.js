// The All details tab: the profile's cards of label / value rows, editable in place (DT-1 – DT-3).
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { api, messageOf } from "../api.js";
import { editableNodes } from "../components/dialogs.js";
import { InlineEdit, PersonSearch } from "../components/inline.js";
import { html } from "../html.js";
import {
  displayValue, editorKind, editorText, isEmpty, parseInput, referencedProjects, sameValue,
} from "../lib/fields.js";

/** A person or project value picked with a server-side search, inside a popover. */
function PickerRow({ field, value, lookup, editable, onCommit }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState([]);
  const search = useRef(null);
  const shown = displayValue(field, value, lookup) || "–";
  useEffect(() => {
    if (open) search.current?.focus();
  }, [open]);
  useEffect(() => {
    if (!open || field.type !== "project") return undefined;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      api("search/projects", { params: { q: query } })
        .then((found) => !cancelled && setHits(found))
        .catch(() => !cancelled && setHits([]));
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query]);

  if (!editable) return html`<span>${shown}</span>`;
  return html`<span class="popover-anchor">
    <button type="button" class="inline-edit" aria-label=${`${field.label}: ${shown}. Edit`} onClick=${() => setOpen(true)}>${shown}</button>
    ${open && field.type === "person"
      ? html`<${PersonSearch}
          title=${`Choose ${field.label.toLowerCase()}`}
          onClose=${() => setOpen(false)}
          onPick=${(person) => {
            setOpen(false);
            onCommit(person.id, person);
          }}
        />`
      : null}
    ${open && field.type === "project"
      ? html`<div class="popover popover--below person-search" role="dialog" aria-label=${`Choose ${field.label.toLowerCase()}`}>
          <input
            class="input"
            aria-label=${`Find ${field.label.toLowerCase()}`}
            placeholder="Number or name"
            value=${query}
            onInput=${(e) => setQuery(e.target.value)}
            onKeyDown=${(e) => e.key === "Escape" && setOpen(false)}
            ref=${search}
          />
          <div role="listbox" aria-label="Projects">
            ${hits.length === 0 ? html`<div class="empty" role="option" aria-selected="false">No project found.</div>` : null}
            ${hits.map(
              (hit) => html`<button
                key=${hit.number}
                type="button"
                role="option"
                aria-selected="false"
                class="menu-item"
                onClick=${() => {
                  setOpen(false);
                  onCommit(hit.number, hit);
                }}
              >
                <span class="menu-item__name">#${hit.number} ${hit.name}</span>
              </button>`,
            )}
          </div>
          ${value !== null && value !== undefined
            ? html`<button type="button" class="link-button" onClick=${() => { setOpen(false); onCommit(null, null); }}>Clear</button>`
            : null}
        </div>`
      : null}
  </span>`;
}

function Row({ field, project, ctx, lookup, rememberPerson, rememberProject, edit }) {
  const editor = project.can_edit;
  const { boot, me, tree } = ctx;

  // Core rows: number is fixed; department and priority are the project's own fields.
  if (field.core === "number") {
    return html`<span class="details__value">#${project.number}</span>`;
  }
  if (field.core === "department") {
    const nodes = editor ? editableNodes(me, tree) : [];
    return html`<${InlineEdit}
      kind="select"
      value=${project.org_node_id}
      display=${project.org_node_name}
      options=${nodes.map((n) => ({ value: n.id, label: n.name }))}
      editable=${editor && nodes.length > 1}
      label=${field.label}
      className="details__value"
      onCommit=${(text) => {
        const id = Number(text);
        const node = nodes.find((n) => n.id === id);
        if (node && id !== project.org_node_id) edit({ org_node_id: id }, { org_node_id: id, org_node_name: node.name });
      }}
    />`;
  }
  if (field.core === "priority") {
    const options = boot.priorities.map((p) => ({ value: p.key, label: p.label }));
    return html`<${InlineEdit}
      kind="select"
      value=${project.priority}
      display=${options.find((o) => o.value === project.priority)?.label ?? project.priority}
      options=${options}
      editable=${editor}
      label=${field.label}
      className="details__value"
      onCommit=${(text) => text && text !== project.priority && edit({ priority: text }, { priority: text })}
    />`;
  }

  const value = project.details[field.key];
  const save = (next, preview) => {
    if (sameValue(next, value)) return;
    edit({ details: { [field.key]: next } }, { details: { ...project.details, [field.key]: next } });
    if (preview && field.type === "person") rememberPerson(preview);
    if (preview && field.type === "project") rememberProject(preview);
  };
  const kind = editorKind(field);

  if (kind === "person" || kind === "project") {
    return html`<span class="details__value">
      <${PickerRow} field=${field} value=${value} lookup=${lookup} editable=${editor} onCommit=${save} />
    </span>`;
  }
  if (kind === "yesno" || kind === "choice") {
    const options =
      kind === "yesno"
        ? [{ value: "", label: "–" }, { value: "yes", label: "Yes" }, { value: "no", label: "No" }]
        : [{ value: "", label: "–" }, ...field.choices.map((c) => ({ value: c, label: c }))];
    const current = kind === "yesno" ? (value === true ? "yes" : value === false ? "no" : "") : (value ?? "");
    return html`<${InlineEdit}
      kind="select"
      value=${current}
      display=${displayValue(field, value) || "–"}
      options=${options}
      editable=${editor}
      label=${field.label}
      className="details__value"
      onCommit=${(text) => {
        if (kind === "yesno") save(text === "" ? null : text === "yes");
        else save(text === "" ? null : text);
      }}
    />`;
  }
  const inlineKind = kind === "textarea" ? "textarea" : kind === "date" ? "date" : "text";
  return html`<${InlineEdit}
    kind=${inlineKind}
    value=${editorText(field, value)}
    display=${displayValue(field, value, lookup) || "–"}
    editable=${editor}
    label=${field.label}
    className=${`details__value${kind === "textarea" ? " details__value--long" : ""}`}
    onCommit=${(text) => {
      const parsed = parseInput(field, text);
      if (parsed.error) ctx.toast(`${field.label}: ${parsed.error}`, "error");
      else save(parsed.value);
    }}
  />`;
}

export function ProjectDetails({ ctx, project, edit }) {
  const cards = ctx.boot.profile.cards;
  const [people, setPeople] = useState(() => new Map(ctx.boot.people.map((p) => [p.id, p])));
  const [projects, setProjects] = useState(() => new Map());
  const wanted = useMemo(() => referencedProjects(cards, project.details), [cards, project.details]);

  useEffect(() => {
    let cancelled = false;
    for (const number of wanted) {
      if (projects.has(number)) continue;
      api(`projects/${number}`)
        .then((found) => !cancelled && setProjects((current) => new Map(current).set(number, found)))
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
  }, [wanted.join(",")]);

  const lookup = { people, projects };
  const rememberPerson = (person) => setPeople((current) => new Map(current).set(person.id, person));
  const rememberProject = (hit) =>
    setProjects((current) => new Map(current).set(hit.number, { number: hit.number, name: hit.name }));

  return html`<div class="details">
    ${cards.map(
      (card) => html`<section key=${card.key} class="card">
        <h2 class="card__title">${card.title}</h2>
        <dl class="details__rows">
          ${card.fields.map(
            (field) => html`<div key=${field.key} class="details__row">
              <dt class="details__label">${field.label}</dt>
              <dd class="details__dd">
                <${Row}
                  field=${field}
                  project=${project}
                  ctx=${ctx}
                  lookup=${lookup}
                  rememberPerson=${rememberPerson}
                  rememberProject=${rememberProject}
                  edit=${edit}
                />
              </dd>
            </div>`,
          )}
        </dl>
      </section>`,
    )}
  </div>`;
}
