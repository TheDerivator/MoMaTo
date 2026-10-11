// The Overview tab: goal, where we are, latest remark, people and dates, days (OV-1 – OV-5).
import { useEffect, useState } from "preact/hooks";

import { api } from "../api.js";
import { ConfirmDialog, editableNodes } from "../components/dialogs.js";
import { InlineEdit, PersonSearch } from "../components/inline.js";
import { Avatar } from "../components/ui.js";
import { html } from "../html.js";
import { formatDate, formatDays, relativeDate } from "../lib/format.js";
import { dayOf } from "../lib/logbook.js";
import { Link, navigate } from "../router.js";

const TASK_HUES = { done: 155, running: 285, planned: 235 };

function Card({ title, children, className = "" }) {
  return html`<section class=${`card ${className}`}>
    <h2 class="card__title">${title}</h2>
    ${children}
  </section>`;
}

function plainDays(days) {
  return formatDays(days).replace(/ d$/, "");
}

// ------------------------------------------------------------------ left column

function GoalCard({ project, edit }) {
  return html`<${Card} title="Goal">
    <p class="goal">
      <${InlineEdit}
        kind="textarea"
        value=${project.goal}
        editable=${project.can_edit}
        label="Goal"
        className="goal__text"
        empty=${project.can_edit ? "Add a goal" : "No goal yet."}
        maxLength=${20000}
        onCommit=${(text) => {
          const goal = text.trim();
          if (goal !== project.goal) edit({ goal }, { goal });
        }}
      />
    </p>
  <//>`;
}

function WhereWeAre({ project }) {
  return html`<${Card} title="Where we are">
    <div class="where__head"><span class="where__timeline">${project.timeline_text}</span></div>
    ${project.tasks.length === 0
      ? html`<p class="muted">No tasks yet. They appear here as the plan is made.</p>`
      : html`<ul class="phases">
          ${project.tasks.map(
            (task) => html`<li key=${task.id} class="phase">
              <span class="phase__bar" style=${{ "--hue": TASK_HUES[task.status] ?? 285 }}>
                <span class="phase__fill" style=${{ width: `${task.progress}%` }}></span>
              </span>
              <span class="phase__name" title=${task.name}>${task.name}</span>
              <span class="phase__status">${task.status_text}</span>
            </li>`,
          )}
        </ul>`}
  <//>`;
}

function LatestRemark({ ctx, project, tabUrl }) {
  const [latest, setLatest] = useState(undefined); // undefined: loading, null: none
  useEffect(() => {
    let cancelled = false;
    api(`projects/${project.number}/remarks`, { params: { limit: 1 } })
      .then((body) => !cancelled && setLatest(body.items.find((r) => !r.deleted) ?? null))
      .catch(() => !cancelled && setLatest(null));
    return () => {
      cancelled = true;
    };
  }, [project.number, project.remark_count]);
  if (!latest) return null;
  const open = (event) => {
    if (event.target.closest("a")) return;
    navigate(tabUrl("remarks"));
  };
  return html`<section class="card card--link latest" onClick=${open}>
    <div class="card__head">
      <h2 class="card__title">Latest remark</h2>
      <${Link} class="card__link" href=${tabUrl("remarks")}>Open remarks →<//>
    </div>
    <div class="latest__body">
      <${Avatar} person=${latest.author} size=${34} />
      <div class="latest__text">
        <div class="remark__who">
          <b>${latest.author.name}</b>
          <span class="remark__when">${relativeDate(dayOf(latest.created_at), ctx.boot.today)}</span>
        </div>
        <div class="md latest__clamp" dangerouslySetInnerHTML=${{ __html: latest.html }}></div>
      </div>
    </div>
  </section>`;
}

// ------------------------------------------------------------------ right column

function Detail({ label, children }) {
  return html`<div class="facts__item">
    <span class="facts__label">${label}</span>
    <span class="facts__value">${children}</span>
  </div>`;
}

function PeopleCard({ ctx, project, edit, act }) {
  const [picking, setPicking] = useState(null); // "coordinator" | "member"
  const [removing, setRemoving] = useState(null);
  const { boot, me, tree } = ctx;
  const editor = project.can_edit;
  const nodes = editor ? editableNodes(me, tree) : [];
  const memberIds = project.members.map((m) => m.id);
  const coordinator = project.coordinator;

  const priorityOptions = boot.priorities.map((p) => ({ value: p.key, label: p.label }));
  return html`<section class="card">
    <div class="people__block">
      <h2 class="card__title">Coordinator</h2>
      <div class="popover-anchor">
        <div class="person-row">
          <${Avatar} person=${coordinator} size=${42} />
          <div class="person-row__text">
            <span class="person-row__name">${coordinator.name}</span>
            <span class="muted">${coordinator.job_title ?? ""}</span>
          </div>
          ${editor
            ? html`<button type="button" class="link-button" onClick=${() => setPicking("coordinator")}>Change</button>`
            : null}
        </div>
        ${picking === "coordinator"
          ? html`<${PersonSearch}
              title="New coordinator"
              onClose=${() => setPicking(null)}
              onPick=${(person) => {
                setPicking(null);
                if (person.id !== coordinator.id) edit({ coordinator_id: person.id }, { coordinator: person });
              }}
            />`
          : null}
      </div>
    </div>

    <div class="people__block">
      <h2 class="card__title">People involved</h2>
      <div class="chips">
        ${project.members.map((person) => {
          const isCoordinator = person.id === coordinator.id;
          return html`<span key=${person.id} class="person-chip">
            <${Avatar} person=${person} size=${26} />
            <span>${person.name}</span>
            ${editor && !isCoordinator
              ? html`<button
                  type="button"
                  class="person-chip__remove"
                  aria-label=${`Remove ${person.name}`}
                  onClick=${() => setRemoving(person)}
                >
                  ×
                </button>`
              : null}
          </span>`;
        })}
        ${editor
          ? html`<span class="popover-anchor">
              <button type="button" class="chip-button" onClick=${() => setPicking("member")}>+ Add person</button>
              ${picking === "member"
                ? html`<${PersonSearch}
                    title="Add a person"
                    exclude=${memberIds}
                    onClose=${() => setPicking(null)}
                    onPick=${(person) => {
                      setPicking(null);
                      act("members", "POST", {
                        body: { user_id: person.id },
                        preview: { members: [...project.members, person] },
                      });
                    }}
                  />`
                : null}
            </span>`
          : null}
      </div>
    </div>

    <div class="facts">
      <${Detail} label="Start">
        <${InlineEdit}
          kind="date"
          value=${project.start_date}
          display=${formatDate(project.start_date)}
          editable=${editor}
          label="Start date"
          onCommit=${(text) => {
            if (text && text !== project.start_date) edit({ start_date: text }, { start_date: text });
          }}
        />
      <//>
      <${Detail} label="End">
        <${InlineEdit}
          kind="date"
          value=${project.end_date}
          display=${formatDate(project.end_date)}
          editable=${editor}
          label="End date"
          onCommit=${(text) => {
            if (text && text !== project.end_date) edit({ end_date: text }, { end_date: text });
          }}
        />
      <//>
      <${Detail} label="Department">
        <${InlineEdit}
          kind="select"
          value=${project.org_node_id}
          display=${project.org_node_name}
          options=${nodes.map((n) => ({ value: n.id, label: n.name }))}
          editable=${editor && nodes.length > 1}
          label="Department"
          onCommit=${(text) => {
            const id = Number(text);
            const node = nodes.find((n) => n.id === id);
            if (node && id !== project.org_node_id) {
              edit({ org_node_id: id }, { org_node_id: id, org_node_name: node.name });
            }
          }}
        />
      <//>
      <${Detail} label="Priority">
        <${InlineEdit}
          kind="select"
          value=${project.priority}
          display=${priorityOptions.find((o) => o.value === project.priority)?.label ?? project.priority}
          options=${priorityOptions}
          editable=${editor}
          label="Priority"
          onCommit=${(text) => {
            if (text && text !== project.priority) edit({ priority: text }, { priority: text });
          }}
        />
      <//>
    </div>

    ${removing
      ? html`<${ConfirmDialog}
          title=${`Remove ${removing.name}?`}
          confirmLabel="Remove"
          onClose=${() => setRemoving(null)}
          onConfirm=${() =>
            act(`members/${removing.id}`, "DELETE", {
              preview: { members: project.members.filter((m) => m.id !== removing.id) },
            })}
        >
          <p>
            ${removing.name} leaves this project and their planned days on it are removed. Hours they
            booked stay on the project.
          </p>
        <//>`
      : null}
  </section>`;
}

function DaysCard({ project, tabUrl }) {
  const { days } = project;
  return html`<${Card} title="Days">
    <div class="days__figure">
      <span class="days__number">${plainDays(days.logged)}</span>
      <span class="muted">of ${plainDays(days.planned)} planned days logged</span>
    </div>
    <div class="meter">
      <div class="meter__fill" style=${{ width: `${Math.min(100, days.logged_percent)}%` }}></div>
      <div class="meter__tick" style=${{ left: `${Math.min(100, days.expected_percent)}%` }}></div>
    </div>
    <span class="muted days__note">
      The black tick marks where the plan expects us today (${plainDays(days.expected)} d).
    </span>
    <${Link} class="card__link" href=${tabUrl("people")}>Per person →<//>
  <//>`;
}

export function ProjectOverview({ ctx, project, edit, act, tabUrl }) {
  return html`<div class="overview">
    <div class="overview__column">
      <${GoalCard} project=${project} edit=${edit} />
      <${WhereWeAre} project=${project} />
      <${LatestRemark} ctx=${ctx} project=${project} tabUrl=${tabUrl} />
    </div>
    <div class="overview__column">
      <${PeopleCard} ctx=${ctx} project=${project} edit=${edit} act=${act} />
      <${DaysCard} project=${project} tabUrl=${tabUrl} />
      <${Link} class="card__link card__link--lone" href=${tabUrl("details")}>All details →<//>
    </div>
  </div>`;
}
