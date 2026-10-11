// Administration: the frame with its sections (ADM-1 – ADM-6); each section is a view of its own.
import { html } from "../html.js";
import { adminSections, chosenSection } from "../lib/admin.js";
import { buildUrl } from "../lib/routes.js";
import { Link } from "../router.js";
import { AuditLog } from "./admin-audit.js";
import { OrgEditor } from "./admin-org.js";
import { PeopleList, PersonPage } from "./admin-people.js";
import { DefaultAccessPage, RolesPage } from "./admin-roles.js";
import { SsoPage } from "./admin-sso.js";

const SUBTITLES = {
  org: "The organisation tree: branches, and which of them are departments.",
  people: "Who works here: their data, availability, sign-in and access.",
  roles: "Roles bundle permissions; assign them from a person's page.",
  access: "What everybody holds without being given it.",
  sso: "Providers people sign in with, and the roles their groups hold.",
  audit: "Sign-ins and changes to people, rights and the organisation, newest first.",
};

export function AdminView({ ctx }) {
  const { route, me } = ctx;
  const sections = adminSections(me.permissions);
  const section = chosenSection(sections, route.section);
  if (!section) {
    return html`<div class="page admin-page">
      <div class="card plan-empty">
        <h2 class="plan-empty__title">No administration rights</h2>
        <p class="muted">Ask an administrator if you need to change the organisation, people or rights.</p>
      </div>
    </div>`;
  }
  const onPerson = section.key === "people" && route.id !== null;
  return html`<div class="page admin-page">
    <div class="admin-header">
      <span class="eyebrow">Administration</span>
      <h1 class="admin-title">${section.label}</h1>
      <p class="muted admin-subtitle">${SUBTITLES[section.key]}</p>
    </div>
    <nav class="segmented admin-tabs" aria-label="Administration sections">
      ${sections.map(
        (s) => html`<${Link}
          key=${s.key}
          class="admin-tab"
          href=${buildUrl({ view: "admin", section: s.key, id: null })}
          aria-current=${s.key === section.key ? "page" : undefined}
        >${s.label}<//>`,
      )}
    </nav>
    ${section.key === "org" ? html`<${OrgEditor} ctx=${ctx} />` : null}
    ${section.key === "people" && !onPerson ? html`<${PeopleList} ctx=${ctx} />` : null}
    ${onPerson ? html`<${PersonPage} ctx=${ctx} id=${route.id} />` : null}
    ${section.key === "roles" ? html`<${RolesPage} ctx=${ctx} />` : null}
    ${section.key === "access" ? html`<${DefaultAccessPage} ctx=${ctx} />` : null}
    ${section.key === "sso" ? html`<${SsoPage} ctx=${ctx} />` : null}
    ${section.key === "audit" ? html`<${AuditLog} ctx=${ctx} />` : null}
  </div>`;
}
