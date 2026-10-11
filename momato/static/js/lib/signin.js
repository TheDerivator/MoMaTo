// Single sign-on decisions (AUTH-3): when Windows sign-in is tried by itself, which failures are
// worth a message, and the way back to the page a redirect sign-in started from. Pure.

/** The server's 401 that the browser did not answer (or that Windows refused): nobody was named. */
const UNANSWERED = "windows_sign_in_required";

/** Only for visitors who are not signed in, only when the server asks for it, once per tab. */
export function shouldTryWindowsSignIn(me, alreadyTried) {
  return Boolean(me?.is_anonymous && me.login?.windows?.automatic && !alreadyTried);
}

/**
 * An attempt nobody asked for fails silently, unless Windows did say who it is and MoMaTo refused
 * that person (no account, suspended): they should know why they are not signed in.
 */
export function isWindowsRefusal(error) {
  return (error?.status === 401 || error?.status === 403) && error.code !== UNANSWERED;
}

/** What to tell someone who pressed "Sign in with Windows" and it failed. */
export function windowsSignInMessage(error) {
  if (error?.code === UNANSWERED) {
    return "Windows sign-in did not work in this browser. Use a MoMaTo account, or ask your administrator.";
  }
  return error?.message ?? String(error);
}

/** The address a "Sign in with …" button leads to, returning to `next` (a path on this site). */
export function ssoStartUrl(provider, next, base) {
  return `${base}api/auth/sso/${encodeURIComponent(provider)}/start?next=${encodeURIComponent(next)}`;
}

/** The refusal an SSO round trip brought back in `?sso_error=…`, and the address without it. */
export function takeSsoError(search, pathname) {
  const params = new URLSearchParams(search);
  const message = params.get("sso_error");
  if (!message) return { message: "", tidy: null };
  params.delete("sso_error");
  const rest = params.toString();
  return { message, tidy: rest ? `${pathname}?${rest}` : pathname };
}
