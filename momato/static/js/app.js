// The application root: bootstrap, appearance, routing and the shell around the views.
import { render } from "preact";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";

import { ApiError, api } from "./api.js";
import { AppearanceSheet, LoginDialog, PasswordDialog } from "./components/dialogs.js";
import { MainMenu, TopBar, TreePane } from "./components/shell.js";
import { Lightbox } from "./components/lightbox.js";
import { Toasts } from "./components/ui.js";
import { html } from "./html.js";
import * as appearanceLib from "./lib/appearance.js";
import { buildUrl, usesTree } from "./lib/routes.js";
import { isWindowsRefusal, shouldTryWindowsSignIn, takeSsoError } from "./lib/signin.js";
import { buildTree, subtreeIds } from "./lib/tree.js";
import { currentRoute, navigate, useRoute } from "./router.js";
import { readUi, writeUi } from "./prefs.js";
import { holdWindowsSignIn, windowsSignIn, windowsSignInTried } from "./windows-signin.js";
import { AdminView } from "./views/admin.js";
import { NotFound } from "./views/pages.js";
import { PeopleView } from "./views/people.js";
import { PlansView } from "./views/plans.js";
import { ProfileView } from "./views/profile.js";
import { ProjectView } from "./views/project.js";
import { TimesheetView } from "./views/timesheet.js";
import { ProjectsView } from "./views/projects.js";
import { SetupView } from "./views/setup.js";

function useAppearance() {
  const [appearance, setState] = useState(() => appearanceLib.read(localStorage));
  const [prefersDark, setPrefersDark] = useState(
    () => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false,
  );
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return undefined;
    const onChange = (event) => setPrefersDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  const resolvedMode = appearanceLib.apply(document.documentElement, appearance, prefersDark);
  const setAppearance = useCallback((next) => {
    appearanceLib.write(localStorage, next);
    setState(next);
  }, []);
  return { appearance, setAppearance, resolvedMode };
}

const NARROW = "(max-width: 719px)";

/** Below 720 px both panes are rails (SH-9). */
function useNarrow() {
  const [narrow, setNarrow] = useState(() => window.matchMedia?.(NARROW).matches ?? false);
  useEffect(() => {
    const query = window.matchMedia?.(NARROW);
    if (!query) return undefined;
    const onChange = (event) => setNarrow(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  return narrow;
}

function useToasts() {
  const [toasts, setToasts] = useState([]);
  const counter = useRef(0);
  const toast = useCallback((text, kind = "info") => {
    counter.current += 1;
    const id = counter.current;
    setToasts((current) => [...current, { id, text, kind }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 5000);
  }, []);
  return { toasts, toast };
}

export function App() {
  const [boot, setBoot] = useState(null);
  const [phase, setPhase] = useState("loading"); // loading | ready | anonymous | password | error
  const [bootError, setBootError] = useState("");
  const [login, setLogin] = useState(null); // what a visitor may sign in with (SSO, Windows)
  const [notice, setNotice] = useState(() => takeSsoError(location.search, location.pathname).message);
  const [ui, setUiState] = useState(readUi);
  const [counts, setCounts] = useState({ statuses: {}, nodes: {}, total: 0 });
  const [lastNode, setLastNode] = useState(null);
  const [sheet, setSheet] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [weekCard, setWeekCard] = useState(null); // the current week, kept fresh by the timesheet
  const [overlay, setOverlay] = useState(null); // narrow screens: "tree" | "menu" opened over the page
  const route = useRoute();
  const narrow = useNarrow();
  const { appearance, setAppearance, resolvedMode } = useAppearance();
  const { toasts, toast } = useToasts();

  const setUi = useCallback((next) => {
    writeUi(next);
    setUiState(next);
  }, []);

  const loadBoot = useCallback(async () => {
    try {
      const body = await api("bootstrap");
      setBoot(body);
      setWeekCard(body.week_card);
      setPhase("ready");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setBoot(null);
        const visitor = await api("auth/me").catch(() => null);
        setLogin(visitor?.login ?? null);
        if (shouldTryWindowsSignIn(visitor, windowsSignInTried())) {
          try {
            await windowsSignIn();
            return loadBoot();
          } catch (refusal) {
            if (isWindowsRefusal(refusal)) setNotice(`Windows sign-in: ${refusal.message}`);
          }
        }
        setPhase("anonymous");
      } else if (error instanceof ApiError && error.code === "password_change_required") {
        setPhase("password");
      } else {
        setBootError(error instanceof ApiError ? error.message : "The server could not be reached.");
        setPhase("error");
      }
    }
  }, []);

  useEffect(() => {
    // A failed SSO sign-in comes back as ?sso_error=…: shown once, then the address is tidied.
    const { message, tidy } = takeSsoError(location.search, location.pathname);
    if (message && tidy) history.replaceState(null, "", tidy);
    loadBoot();
  }, [loadBoot]);

  // "/" goes to the projects (SH-8).
  useEffect(() => {
    if (route.view === "redirect") navigate(route.to, { replace: true });
  }, [route.view]);

  // A pane opened over a narrow page closes on navigation, on widening, and with Escape.
  useEffect(() => setOverlay(null), [route, narrow]);
  useLayoutEffect(() => {
    if (!overlay) return undefined;
    const onKey = (event) => event.key === "Escape" && setOverlay(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overlay]);

  useEffect(() => {
    if (usesTree(route)) setLastNode(route.node);
  }, [usesTree(route) ? route.node : undefined, route.view]);

  const tree = useMemo(() => (boot ? buildTree(boot.org) : null), [boot]);
  const statuses = useMemo(() => new Map((boot?.statuses ?? []).map((s) => [s.key, s])), [boot]);
  const filterJson = JSON.stringify(
    route.view === "projects"
      ? [route.node, route.status, route.q, route.name, route.coordinator]
      : null,
  );

  // Server counts for the status chips and the tree (PL-2, SH-3).
  useEffect(() => {
    if (phase !== "ready" || route.view !== "projects") return undefined;
    let cancelled = false;
    api("projects/counts", {
      params: { node: route.node, status: route.status, q: route.q, name: route.name, coordinator: route.coordinator },
    })
      .then((body) => !cancelled && setCounts(body))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [phase, filterJson]);

  useEffect(() => {
    const titles = { projects: "Projects", project: `Project #${route.number}`, plans: "Action plans",
      people: "People planning", timesheet: "My timesheet", profile: "Profile", admin: "Administration" };
    document.title = `${titles[route.view] ?? "MoMaTo"} · MoMaTo`;
  }, [route.view, route.number]);

  const logout = useCallback(async () => {
    await api("auth/logout", { method: "POST" });
    holdWindowsSignIn(); // else it would sign in again at once
    setSheet(false);
    await loadBoot();
  }, [loadBoot]);

  if (phase === "loading") return html`<div class="loading-screen">MoMaTo</div>`;
  if (phase === "error") {
    return html`<div class="loading-screen" role="alert">${bootError}</div>`;
  }
  if (phase === "anonymous") {
    return html`<div class="app">
      <${LoginDialog} login=${login} notice=${notice} onSignedIn=${() => loadBoot()} />
    </div>`;
  }
  if (phase === "password") {
    return html`<div class="app">
      <${PasswordDialog} onChanged=${() => loadBoot()} onLogout=${logout} />
    </div>`;
  }

  // Signing out clears the bootstrap a moment before the phase becomes "anonymous".
  if (!boot || !tree) return html`<div class="loading-screen">MoMaTo</div>`;

  if (!tree.root) {
    // A fresh installation has no organisation: nothing else can exist before its root.
    return html`<div class="app">
      <${SetupView} me=${boot.me} reload=${loadBoot} logout=${logout} toast=${toast} />
      <${Toasts} toasts=${toasts} />
    </div>`;
  }

  const root = tree.root.id;
  const selectedNode = (usesTree(route) ? route.node : lastNode) ?? root;
  const me = boot.me;
  const myPerson = boot.people.find((p) => p.id === me.person_id) ?? null;

  const treeCounts = (() => {
    if (route.view === "people") {
      const result = {};
      for (const id of tree.nodes.keys()) {
        const inside = new Set(subtreeIds(tree, id));
        result[id] = boot.people.filter((p) => p.active && inside.has(p.org_node_id)).length;
      }
      return result;
    }
    if (route.view === "plans") {
      const result = {};
      for (const id of tree.nodes.keys()) {
        const inside = new Set(subtreeIds(tree, id));
        result[id] = boot.plans.filter((p) => inside.has(p.owner_org_node_id)).length;
      }
      return result;
    }
    return counts.nodes ?? {};
  })();

  const ctx = {
    boot,
    me,
    myPerson,
    tree,
    statuses,
    route,
    ui,
    setUi,
    narrow,
    overlay,
    setOverlay,
    selectedNode,
    weekCard,
    setWeekCard,
    appearance,
    setAppearance,
    resolvedMode,
    toast,
    logout,
    reload: loadBoot,
    openLogin: () => setLoginOpen(true),
    toggleAppearance: () => setSheet((open) => !open),
    urlFor: buildUrl,
    // Read the address bar when the (debounced) search fires, not the route of the keystroke.
    goSearch: (text) => {
      const now = currentRoute();
      navigate(
        buildUrl({
          view: "projects",
          node: now.view === "projects" ? now.node : null,
          status: null,
          q: text,
          name: "",
          coordinator: "",
        }),
        { replace: now.view === "projects" },
      );
    },
  };

  let view;
  switch (route.view) {
    case "projects":
      view = html`<${ProjectsView} ctx=${ctx} counts=${counts} />`;
      break;
    case "project":
      view = html`<${ProjectView} ctx=${ctx} />`;
      break;
    case "timesheet":
      view = html`<${TimesheetView} ctx=${ctx} />`;
      break;
    case "people":
      view = html`<${PeopleView} ctx=${ctx} counts=${treeCounts} />`;
      break;
    case "plans":
      view = html`<${PlansView} ctx=${ctx} counts=${treeCounts} />`;
      break;
    case "profile":
      view = html`<${ProfileView} ctx=${ctx} />`;
      break;
    case "admin":
      view = html`<${AdminView} ctx=${ctx} />`;
      break;
    case "redirect":
      view = null;
      break;
    default:
      view = html`<${NotFound} />`;
  }

  return html`<div class="app">
    <a class="skip-link" href="#content">Skip to content</a>
    ${narrow && overlay ? html`<div class="pane-backdrop" onClick=${() => setOverlay(null)}></div>` : null}
    <${TreePane} ctx=${ctx} counts=${treeCounts} />
    <${MainMenu} ctx=${ctx} />
    <div class="main">
      <${TopBar} ctx=${ctx} />
      <main class="content" id="content" tabindex="-1">${view}</main>
    </div>
    ${sheet ? html`<${AppearanceSheet} ctx=${ctx} onClose=${() => setSheet(false)} />` : null}
    ${loginOpen
      ? html`<${LoginDialog} login=${me.login} onClose=${() => setLoginOpen(false)} onSignedIn=${() => { setLoginOpen(false); loadBoot(); }} />`
      : null}
    <${Lightbox} />
    <${Toasts} toasts=${toasts} />
  </div>`;
}

export function mount(container) {
  render(html`<${App} />`, container);
}
