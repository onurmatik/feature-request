import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowBigUpDash,
  FolderOpen,
  Layers,
  MessageCircle,
  Sparkles,
} from "lucide-react";

const DEFAULT_FEATURED_PROJECTS = [
  {
    id: "sample-a",
    owner_handle: "tailwindlabs",
    name: "Tailwind UI Kit",
    slug: "ui-kit",
    tagline: "Community-requested utilities and components.",
    issues_count: 124,
  },
  {
    id: "sample-b",
    owner_handle: "lucide",
    name: "Lucide Icons",
    slug: "icons",
    tagline: "Vote on the next icons and naming conventions.",
    issues_count: 3120,
  },
  {
    id: "sample-c",
    owner_handle: "vite",
    name: "Vite Core",
    slug: "core",
    tagline: "Track build tooling priorities and plugin needs.",
    issues_count: 580,
  },
];

const SAMPLE_REQUESTS = [
  {
    id: "#182",
    title: "Offline mode with conflict handling",
    type: "Feature",
    status: "Planned",
    upvotes: 76,
  },
  {
    id: "#121",
    title: "Export votes and request timeline as CSV",
    type: "Feature",
    status: "In Progress",
    upvotes: 43,
  },
  {
    id: "#77",
    title: "Email digest shows stale status tags",
    type: "Bug",
    status: "Open",
    upvotes: 18,
  },
];

function cls(...values) {
  return values.filter(Boolean).join(" ");
}

function csrfTokenFromCookie() {
  const tokenPart = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("csrftoken="));

  return tokenPart ? decodeURIComponent(tokenPart.slice("csrftoken=".length)) : "";
}

function projectPath(project) {
  return `/${project.owner_handle}/${project.slug}/`;
}

function toReadableCount(value) {
  const count = Number(value || 0);
  if (!Number.isFinite(count)) {
    return "0";
  }
  return new Intl.NumberFormat("en-US").format(count);
}

export default function LandingPage({ initialAuthMode = null }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUserHandle, setCurrentUserHandle] = useState("");
  const [featuredProjects, setFeaturedProjects] = useState([]);
  const [isFeaturedLoading, setIsFeaturedLoading] = useState(true);
  const [authMode, setAuthMode] = useState(initialAuthMode);

  const [signInIdentity, setSignInIdentity] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [signUpHandle, setSignUpHandle] = useState("");
  const [signUpDisplayName, setSignUpDisplayName] = useState("");
  const [authFeedback, setAuthFeedback] = useState("");
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false);

  const projectsToShow = useMemo(() => {
    if (featuredProjects.length) {
      return featuredProjects;
    }
    return DEFAULT_FEATURED_PROJECTS;
  }, [featuredProjects]);

  const refreshSession = useCallback(async () => {
    const response = await fetch("/auth/me");
    if (!response.ok) {
      setIsAuthenticated(false);
      setCurrentUserHandle("");
      return;
    }

    const data = await response.json();
    setIsAuthenticated(Boolean(data.is_authenticated));
    setCurrentUserHandle(String(data.current_user_handle || ""));
  }, []);

  useEffect(() => {
    refreshSession().catch(() => {
      setIsAuthenticated(false);
      setCurrentUserHandle("");
    });
  }, [refreshSession]);

  useEffect(() => {
    if (isAuthenticated) {
      setAuthMode(null);
      return;
    }

    if (initialAuthMode) {
      setAuthMode(initialAuthMode);
    }
  }, [initialAuthMode, isAuthenticated]);

  useEffect(() => {
    let isCancelled = false;

    async function loadFeaturedProjects() {
      setIsFeaturedLoading(true);
      try {
        const response = await fetch("/api/public/featured-projects?limit=3");
        if (!response.ok) {
          throw new Error("Projects not available.");
        }
        const data = await response.json();
        if (!isCancelled) {
          setFeaturedProjects(Array.isArray(data) ? data : []);
        }
      } catch {
        if (!isCancelled) {
          setFeaturedProjects([]);
        }
      } finally {
        if (!isCancelled) {
          setIsFeaturedLoading(false);
        }
      }
    }

    loadFeaturedProjects();
    return () => {
      isCancelled = true;
    };
  }, []);

  async function ensureCsrfCookie() {
    await fetch("/auth/me");
  }

  async function onSignInSubmit(event) {
    event.preventDefault();
    const identity = signInIdentity.trim();
    if (!identity) {
      setAuthFeedback("Email or handle is required.");
      return;
    }

    setIsAuthSubmitting(true);
    setAuthFeedback("Signing in...");

    try {
      await ensureCsrfCookie();
      const response = await fetch("/auth/sign-in", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({ email_or_handle: identity }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Sign in failed.";
        setAuthFeedback(detail);
        return;
      }

      const handle = String(payload.current_user_handle || "").trim();
      if (!handle) {
        setAuthFeedback("Session started but no handle was returned.");
        return;
      }

      window.location.assign(`/${handle}/`);
    } catch {
      setAuthFeedback("Sign in failed. Please try again.");
    } finally {
      setIsAuthSubmitting(false);
    }
  }

  async function onSignUpSubmit(event) {
    event.preventDefault();
    const email = signUpEmail.trim().toLowerCase();
    const handle = signUpHandle.trim().toLowerCase();
    const displayName = signUpDisplayName.trim();

    if (!email || !handle) {
      setAuthFeedback("Email and handle are required.");
      return;
    }

    setIsAuthSubmitting(true);
    setAuthFeedback("Creating account...");

    try {
      await ensureCsrfCookie();
      const response = await fetch("/auth/sign-up", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({
          email,
          handle,
          display_name: displayName,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Sign up failed.";
        setAuthFeedback(detail);
        return;
      }

      const nextHandle = String(payload.current_user_handle || "").trim();
      if (!nextHandle) {
        setAuthFeedback("Account created but handle was missing.");
        return;
      }

      window.location.assign(`/${nextHandle}/`);
    } catch {
      setAuthFeedback("Sign up failed. Please try again.");
    } finally {
      setIsAuthSubmitting(false);
    }
  }

  function openAuth(mode) {
    setAuthMode(mode);
    setAuthFeedback("");
  }

  function closeAuth() {
    setAuthMode(null);
    setAuthFeedback("");
    setIsAuthSubmitting(false);
  }

  return (
    <div className="min-h-screen bg-[#f3f4f6] text-[#111827]">
      <div className="relative overflow-hidden border-b border-[#e5e7eb] bg-white">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,_rgba(6,182,212,0.16),transparent_45%),radial-gradient(circle_at_20%_10%,_rgba(17,24,39,0.08),transparent_35%)]" />
        <header className="relative z-10 border-b border-[#e5e7eb]">
          <div className="mx-auto flex h-[64px] w-full max-w-6xl items-center justify-between px-4 sm:px-6">
            <a href="/" className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-sm-ds bg-[#06B6D4] text-white shadow-sm">
                <Layers size={20} />
              </div>
              <span className="text-lg font-bold tracking-tight">FeatureRequest</span>
            </a>

            <nav className="hidden items-center gap-6 text-sm font-medium text-[#6b7280] md:flex">
              <a href="#overview" className="hover:text-[#111827]">
                Overview
              </a>
              <a href="#sample" className="hover:text-[#111827]">
                Sample Dashboard
              </a>
              <a href="#featured" className="hover:text-[#111827]">
                Featured Boards
              </a>
            </nav>

            {isAuthenticated ? (
              <a
                href={`/${currentUserHandle}/`}
                className="rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white transition-colors hover:bg-black"
              >
                Go to Dashboard
              </a>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => openAuth("signIn")}
                  className="rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide text-[#6b7280] transition-colors hover:text-[#111827]"
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => openAuth("signUp")}
                  className="rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white transition-colors hover:bg-black"
                >
                  Sign Up
                </button>
              </div>
            )}
          </div>
        </header>

        <section id="overview" className="relative z-10 mx-auto max-w-6xl px-4 pb-16 pt-16 sm:px-6 md:pt-20">
          <div className="grid gap-10 md:grid-cols-[1fr_360px] md:items-center">
            <div className="space-y-6">
              <p className="inline-flex items-center gap-2 rounded-full border border-cyan-100 bg-cyan-50 px-3 py-1 text-[10px] font-mono font-bold uppercase tracking-wider text-[#06B6D4]">
                <Sparkles size={12} />
                Public Feedback Boards
              </p>
              <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
                Ship what matters with requests, votes, and comments in one place.
              </h1>
              <p className="max-w-2xl text-base text-[#6b7280] sm:text-lg">
                FeatureRequest helps teams collect feature ideas, bug reports, and customer context from public
                boards. Prioritize by real demand and keep the discussion attached to each request.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row">
                {!isAuthenticated ? (
                  <>
                    <button
                      type="button"
                      onClick={() => openAuth("signUp")}
                      className="rounded-sm-ds bg-[#06B6D4] px-6 py-3 text-xs font-bold uppercase tracking-wide text-white transition-colors hover:bg-cyan-600"
                    >
                      Create Board
                    </button>
                    <button
                      type="button"
                      onClick={() => openAuth("signIn")}
                      className="rounded-sm-ds border border-[#d1d5db] bg-white px-6 py-3 text-xs font-bold uppercase tracking-wide text-[#111827] transition-colors hover:bg-[#f9fafb]"
                    >
                      Continue Existing Account
                    </button>
                  </>
                ) : (
                  <a
                    href={`/${currentUserHandle}/`}
                    className="inline-flex w-fit items-center rounded-sm-ds bg-[#06B6D4] px-6 py-3 text-xs font-bold uppercase tracking-wide text-white transition-colors hover:bg-cyan-600"
                  >
                    Open My Workspace
                  </a>
                )}
              </div>
            </div>

            <div className="rounded-md-ds border border-[#e5e7eb] bg-white p-5 shadow-ds">
              <p className="mb-3 text-[10px] font-mono font-bold uppercase tracking-widest text-[#9ca3af]">
                Why teams use FeatureRequest
              </p>
              <div className="space-y-4 text-sm text-[#6b7280]">
                <div className="flex items-start gap-3">
                  <ArrowBigUpDash className="mt-0.5 text-[#06B6D4]" size={18} />
                  <p>Prioritize using upvotes instead of scattered inbox threads.</p>
                </div>
                <div className="flex items-start gap-3">
                  <MessageCircle className="mt-0.5 text-[#06B6D4]" size={18} />
                  <p>Keep request-level discussion and updates transparent.</p>
                </div>
                <div className="flex items-start gap-3">
                  <FolderOpen className="mt-0.5 text-[#06B6D4]" size={18} />
                  <p>Launch public project boards instantly and share one URL for feedback.</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      <main className="mx-auto max-w-6xl space-y-14 px-4 py-14 sm:px-6">
        <section id="sample" className="rounded-md-ds border border-[#e5e7eb] bg-white shadow-ds">
          <div className="flex items-center gap-2 border-b border-[#e5e7eb] px-4 py-3">
            <span className="h-2.5 w-2.5 rounded-full bg-[#d1d5db]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#d1d5db]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#d1d5db]" />
            <div className="ml-3 rounded-sm-ds border border-[#e5e7eb] bg-[#f9fafb] px-2 py-1 text-[10px] font-mono text-[#9ca3af]">
              featurerequest.io/acme/mobile-app
            </div>
          </div>

          <div className="grid min-h-[420px] gap-0 lg:grid-cols-[260px_1fr]">
            <aside className="border-r border-[#e5e7eb] bg-[#f9fafb] p-4">
              <p className="mb-3 text-[10px] font-mono font-bold uppercase tracking-widest text-[#9ca3af]">
                Projects
              </p>
              <div className="space-y-2">
                <div className="rounded-sm-ds bg-cyan-50 px-3 py-2 text-sm font-semibold text-[#06B6D4]">All Projects</div>
                <div className="rounded-sm-ds bg-white px-3 py-2 text-sm text-[#6b7280]">Mobile App</div>
                <div className="rounded-sm-ds bg-white px-3 py-2 text-sm text-[#6b7280]">Web Console</div>
              </div>
            </aside>

            <div className="grid lg:grid-cols-[370px_1fr]">
              <div className="border-r border-[#e5e7eb]">
                <div className="space-y-2 border-b border-[#e5e7eb] p-4">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold uppercase tracking-widest text-[#6b7280]">Requests</p>
                    <span className="rounded-sm-ds bg-[#06B6D4] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-white">
                      New
                    </span>
                  </div>
                  <div className="rounded-sm-ds border border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-xs text-[#9ca3af]">
                    Filter issues...
                  </div>
                </div>

                <div className="divide-y divide-[#e5e7eb]">
                  {SAMPLE_REQUESTS.map((request, index) => (
                    <div
                      key={request.id}
                      className={cls(
                        "space-y-2 p-4",
                        index === 0 ? "border-l-4 border-[#06B6D4] bg-cyan-50/40" : "border-l-4 border-transparent",
                      )}
                    >
                      <div className="flex items-center justify-between text-[10px] font-mono text-[#9ca3af]">
                        <span>{request.id}</span>
                        <span>{request.upvotes} votes</span>
                      </div>
                      <p className="text-sm font-semibold text-[#111827]">{request.title}</p>
                      <div className="flex items-center gap-2 text-[10px] font-mono">
                        <span className="rounded bg-purple-50 px-1.5 py-0.5 text-purple-700">{request.type}</span>
                        <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">{request.status}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="hidden bg-white p-6 lg:block">
                <div className="mb-5 flex items-center justify-between border-b border-[#e5e7eb] pb-4">
                  <h3 className="text-lg font-bold text-[#111827]">{SAMPLE_REQUESTS[0].title}</h3>
                  <span className="rounded-sm-ds border border-[#e5e7eb] px-2 py-1 text-xs font-semibold text-[#111827]">
                    Upvote (76)
                  </span>
                </div>
                <p className="mb-8 text-sm text-[#6b7280]">
                  Users need full offline workflow support while traveling. Suggested scope includes local cache,
                  write queue, and conflict prompts.
                </p>
                <p className="mb-3 text-[10px] font-mono font-bold uppercase tracking-widest text-[#9ca3af]">
                  Activity & Comments
                </p>
                <div className="rounded-md-ds border border-[#e5e7eb] bg-[#f9fafb] p-4 text-sm text-[#6b7280]">
                  Discuss implementation details with stakeholders and notify subscribers when status changes.
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="featured">
          <div className="mb-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-[#06B6D4]">
                Featured Public Projects
              </p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">Explore active request boards</h2>
            </div>
            {isFeaturedLoading ? <p className="text-xs text-[#9ca3af]">Loading projects...</p> : null}
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {projectsToShow.map((project) => (
              <a
                key={project.id}
                href={projectPath(project)}
                className="group rounded-md-ds border border-[#e5e7eb] bg-white p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-[#06B6D4] hover:shadow-ds"
              >
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-sm-ds bg-cyan-50 text-[#06B6D4]">
                    <FolderOpen size={20} />
                  </div>
                  <div>
                    <p className="font-semibold text-[#111827] group-hover:text-[#06B6D4]">{project.name}</p>
                    <p className="text-[10px] font-mono text-[#6b7280]">
                      /{project.owner_handle}/{project.slug}
                    </p>
                  </div>
                </div>
                <p className="mb-5 min-h-[40px] text-sm text-[#6b7280]">
                  {project.tagline || "Open request board for roadmap planning and bug triage."}
                </p>
                <div className="flex items-center justify-between text-[10px] font-mono font-bold uppercase tracking-wide">
                  <span className="text-[#6b7280]">{toReadableCount(project.issues_count)} Requests</span>
                  <span className="text-[#06B6D4]">View Board</span>
                </div>
              </a>
            ))}
          </div>
        </section>
      </main>

      {authMode ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#111827]/60 p-4"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              closeAuth();
            }
          }}
        >
          <div className="w-full max-w-md overflow-hidden rounded-md-ds border border-[#e5e7eb] bg-white shadow-2xl">
            <div className="border-b border-[#e5e7eb] bg-[#f9fafb] p-3">
              <div className="grid grid-cols-2 gap-2 rounded-sm-ds bg-white p-1">
                <button
                  type="button"
                  onClick={() => openAuth("signIn")}
                  className={cls(
                    "rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide",
                    authMode === "signIn" ? "bg-[#111827] text-white" : "text-[#6b7280] hover:text-[#111827]",
                  )}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => openAuth("signUp")}
                  className={cls(
                    "rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide",
                    authMode === "signUp" ? "bg-[#111827] text-white" : "text-[#6b7280] hover:text-[#111827]",
                  )}
                >
                  Sign Up
                </button>
              </div>
            </div>

            <div className="p-6">
              {authMode === "signIn" ? (
                <form className="space-y-4" onSubmit={onSignInSubmit}>
                  <h3 className="text-lg font-bold text-[#111827]">Welcome back</h3>
                  <p className="text-sm text-[#6b7280]">Use your email or handle to continue.</p>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                      Email or Handle
                    </label>
                    <input
                      type="text"
                      value={signInIdentity}
                      onChange={(event) => setSignInIdentity(event.target.value)}
                      className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                      autoFocus
                    />
                  </div>
                  {authFeedback ? <p className="text-xs text-[#6b7280]">{authFeedback}</p> : null}
                  <div className="flex justify-end gap-3">
                    <button
                      type="button"
                      onClick={closeAuth}
                      className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isAuthSubmitting}
                      className="rounded-sm-ds bg-[#06B6D4] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-cyan-600 disabled:opacity-50"
                    >
                      Continue
                    </button>
                  </div>
                </form>
              ) : (
                <form className="space-y-4" onSubmit={onSignUpSubmit}>
                  <h3 className="text-lg font-bold text-[#111827]">Create your account</h3>
                  <p className="text-sm text-[#6b7280]">Set a public handle, then publish your first board.</p>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                      Handle
                    </label>
                    <input
                      type="text"
                      value={signUpHandle}
                      onChange={(event) => setSignUpHandle(event.target.value)}
                      className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                      placeholder="your_team"
                      autoFocus
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                      Email
                    </label>
                    <input
                      type="email"
                      value={signUpEmail}
                      onChange={(event) => setSignUpEmail(event.target.value)}
                      className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                      placeholder="you@company.com"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                      Display Name (optional)
                    </label>
                    <input
                      type="text"
                      value={signUpDisplayName}
                      onChange={(event) => setSignUpDisplayName(event.target.value)}
                      className="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]"
                      placeholder="Product Team"
                    />
                  </div>
                  {authFeedback ? <p className="text-xs text-[#6b7280]">{authFeedback}</p> : null}
                  <div className="flex justify-end gap-3">
                    <button
                      type="button"
                      onClick={closeAuth}
                      className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isAuthSubmitting}
                      className="rounded-sm-ds bg-[#111827] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-black disabled:opacity-50"
                    >
                      Create Account
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
