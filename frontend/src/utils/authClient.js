export function csrfTokenFromCookie() {
  const tokenPart = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("csrftoken="));

  return tokenPart ? decodeURIComponent(tokenPart.slice("csrftoken=".length)) : "";
}

export function authSignInEndpoint({ useCurrentPathAsNext = false } = {}) {
  const next = new URLSearchParams(window.location.search).get("next");
  if (next) {
    return `/auth/sign-in?next=${encodeURIComponent(next)}`;
  }

  if (!useCurrentPathAsNext) {
    return "/auth/sign-in";
  }

  const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  return `/auth/sign-in?next=${encodeURIComponent(currentPath)}`;
}

export function getPostAuthRedirect(handle, { useCurrentPathAsFallback = false } = {}) {
  const safeHandle = String(handle || "").trim();
  const defaultRedirect = useCurrentPathAsFallback
    ? `${window.location.pathname}${window.location.search}${window.location.hash}`
    : safeHandle
      ? `/${safeHandle}/`
      : "/";
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");

  if (!next) {
    return defaultRedirect;
  }

  try {
    const nextUrl = new URL(next, window.location.origin);
    if (nextUrl.origin !== window.location.origin) {
      return defaultRedirect;
    }

    return `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`;
  } catch {
    return defaultRedirect;
  }
}
