import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowBigUpDash,
  FolderOpen,
  Layers,
  Lock,
  MessageSquare,
  Palette,
  Sparkles,
} from "lucide-react";

const DEFAULT_FEATURED_PROJECTS = [
  {
    id: "sample-a",
    owner_handle: "onurmatik",
    name: "Mini Feedback",
    slug: "mini-feedback",
    tagline: "Solo founder board where users vote on what ships next.",
    issues_count: 86,
  },
  {
    id: "sample-b",
    owner_handle: "buildwithada",
    name: "ShipLog",
    slug: "shiplog",
    tagline: "Public changelog + request inbox for one-person products.",
    issues_count: 142,
  },
  {
    id: "sample-c",
    owner_handle: "makercem",
    name: "Tiny CRM",
    slug: "tiny-crm",
    tagline: "Keep users close and let them discover your other projects.",
    issues_count: 57,
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
      <header className="sticky top-0 z-50 border-b border-[#e5e7eb] bg-white h-[56px] flex items-center px-4 md:px-8">
        <div className="mx-auto flex h-full w-full max-w-7xl items-center justify-between">
          <a href="/" className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-sm-ds bg-[#06B6D4] flex items-center justify-center text-white shadow-sm">
              <Layers size={18} />
            </div>
            <span className="text-lg font-bold tracking-tight">FeatureRequest</span>
          </a>

          <nav className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm font-medium text-[#6b7280] hover:text-[#111827] transition-colors">
              Features
            </a>
            <a href="#projects" className="text-sm font-medium text-[#6b7280] hover:text-[#111827] transition-colors">
              Public Boards
            </a>
            <a href="#pricing" className="text-sm font-medium text-[#6b7280] hover:text-[#111827] transition-colors">
              Pricing
            </a>
          </nav>

          <div className="flex items-center gap-4">
            {!isAuthenticated ? (
              <>
                <button
                  type="button"
                  onClick={() => openAuth("signIn")}
                  className="text-sm font-bold text-[#6b7280] transition-colors hover:text-[#111827] px-2"
                >
                  Sign in
                </button>
                <button
                  type="button"
                  onClick={() => openAuth("signUp")}
                  className="px-4 py-2 bg-[#111827] text-xs font-bold uppercase tracking-wide text-white rounded-sm-ds shadow-sm hover:bg-black transition-all"
                >
                  Get Started
                </button>
              </>
            ) : (
              <a
                href={`/${currentUserHandle}/`}
                className="px-4 py-2 bg-[#111827] text-xs font-bold uppercase tracking-wide text-white rounded-sm-ds shadow-sm hover:bg-black transition-all"
              >
                Open My Workspace
              </a>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto relative">
        <section className="pt-16 pb-20 md:pt-24 md:pb-32 px-4 border-b border-[#e5e7eb] bg-white">
          <div className="mx-auto max-w-4xl text-center space-y-8">
            <p className="inline-flex items-center gap-2 px-3 py-1 bg-cyan-50 border border-cyan-100 rounded-full mx-auto">
              <span className="h-2 w-2 rounded-full bg-[#06B6D4]" />
              <span className="text-[10px] font-mono font-bold text-[#06B6D4] uppercase tracking-wider">
                Open Beta Now Live
              </span>
            </p>
            <h1 className="text-4xl md:text-6xl font-bold tracking-tight text-[#111827]">
              Ship the features your <span className="text-[#06B6D4]">users actually want</span>
            </h1>
            <p className="text-lg md:text-xl text-[#6b7280] max-w-2xl mx-auto leading-relaxed">
              The simplest way to manage feature requests, bug reports, and product feedback. Public boards, upvoting,
              and focused discussions for all your projects in one place.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <button
                type="button"
                onClick={() => openAuth("signUp")}
                className="w-full sm:w-auto px-8 py-3 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all uppercase tracking-wide"
              >
                Create your Board
              </button>
              <a
                href="https://github.com/onurmatik/feature-request"
                target="_blank"
                rel="noopener noreferrer"
                className="w-full sm:w-auto px-8 py-3 bg-white border border-[#e5e7eb] text-[#111827] text-sm font-bold rounded-sm-ds hover:bg-[#f3f4f6] transition-all uppercase tracking-wide inline-flex items-center justify-center gap-2"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="h-4 w-4"
                  aria-hidden="true"
                >
                  <path d="M12 2C6.477 2 2 6.485 2 12.013c0 4.425 2.866 8.184 6.839 9.504.5.092.682-.217.682-.482 0-.237-.008-.865-.013-1.697-2.782.603-3.369-1.34-3.369-1.34-.454-1.157-1.11-1.465-1.11-1.465-.908-.62.069-.608.069-.608 1.003.07 1.531 1.033 1.531 1.033.892 1.53 2.341 1.088 2.91.832.092-.646.35-1.09.636-1.34-2.22-.252-4.555-1.112-4.555-4.945 0-1.093.39-1.987 1.03-2.686-.103-.252-.447-1.27.098-2.647 0 0 .84-.27 2.75 1.027a9.564 9.564 0 0 1 2.5-.337 9.55 9.55 0 0 1 2.5.337c1.909-1.297 2.748-1.027 2.748-1.027.547 1.377.202 2.395.1 2.647.64.7 1.029 1.593 1.029 2.686 0 3.842-2.339 4.69-4.566 4.936.359.31.678.923.678 1.862 0 1.344-.013 2.428-.013 2.76 0 .267.18.578.688.48A10.022 10.022 0 0 0 22 12.013C22 6.485 17.523 2 12 2Z" />
                </svg>
                View on Github
              </a>
            </div>
          </div>
        </section>

        <section id="demo" className="-mt-12 md:-mt-20 px-4">
          <div className="mx-auto max-w-5xl bg-white border border-[#e5e7eb] rounded-md-ds shadow-2xl overflow-hidden">
            <div className="h-10 bg-[#f9fafb] border-b border-[#e5e7eb] flex items-center px-4 gap-2">
              <div className="flex gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#e5e7eb]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#e5e7eb]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#e5e7eb]" />
              </div>
              <div className="flex-1 flex justify-center">
                <div className="w-1/2 h-5 bg-white border border-[#e5e7eb] rounded text-[10px] font-mono text-[#9ca3af] flex items-center px-2">
                  featurerequest.io/onurmatik/mini-feedback
                </div>
              </div>
            </div>
            <div className="flex h-[400px] md:h-[600px] opacity-90 grayscale-[0.2]">
              <aside className="hidden sm:block w-48 border-r border-[#e5e7eb] p-3 bg-white">
                <div className="space-y-4">
                  <div className="space-y-1">
                    <div className="h-4 w-16 bg-[#f3f4f6] rounded mb-4" />
                    <div className="h-8 w-full bg-cyan-50 rounded" />
                    <div className="h-8 w-full bg-[#f9fafb] rounded" />
                    <div className="h-8 w-full bg-[#f9fafb] rounded" />
                    <div className="h-8 w-full bg-[#f9fafb] rounded" />
                  </div>
                </div>
              </aside>
              <div className="w-full sm:w-80 border-r border-[#e5e7eb] bg-white">
                <div className="space-y-4 border-b border-[#e5e7eb] p-4">
                  <div className="flex justify-between items-center">
                    <div className="h-4 w-20 bg-[#f3f4f6] rounded" />
                    <span className="h-6 w-20 rounded bg-[#06B6D4] text-[10px] font-bold uppercase tracking-wide text-white flex items-center justify-center">
                      New
                    </span>
                  </div>
                  <div className="h-8 w-full bg-[#f3f4f6] rounded" />
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
              <div className="hidden md:block flex-1 bg-white p-8">
                <div className="max-w-2xl space-y-6">
                  <div className="flex justify-between border-b border-[#e5e7eb] pb-4">
                    <div className="h-8 w-48 bg-[#f3f4f6] rounded" />
                    <div className="h-8 w-32 bg-[#f3f4f6] rounded" />
                  </div>
                  <div className="space-y-3">
                    <div className="h-4 w-full bg-[#f3f4f6] rounded" />
                    <div className="h-4 w-full bg-[#f3f4f6] rounded" />
                    <div className="h-4 w-3/4 bg-[#f3f4f6] rounded" />
                  </div>
                  <div className="pt-8 space-y-4">
                    <div className="h-4 w-40 bg-[#f3f4f6] rounded mb-6" />
                    <div className="flex gap-3">
                      <div className="w-8 h-8 rounded-full bg-cyan-50 shrink-0" />
                      <div className="flex-1 h-16 bg-[#f9fafb] border border-[#e5e7eb] rounded" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="projects" className="py-20 px-4 max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <p className="text-[10px] font-mono font-bold text-[#06B6D4] uppercase tracking-[0.2em]">Featured Public Boards</p>
            <h2 className="text-3xl font-bold text-[#111827] mt-4">Community Projects</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {projectsToShow.map((project) => (
              <a
                key={project.id}
                href={projectPath(project)}
                className="group rounded-md-ds border border-[#e5e7eb] bg-white p-6 hover:border-[#06B6D4] transition-all hover:shadow-ds"
              >
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-10 w-10 rounded-sm-ds bg-cyan-50 text-[#06B6D4] flex items-center justify-center">
                    <FolderOpen size={20} />
                  </div>
                  <div>
                    <p className="font-bold text-[#111827] group-hover:text-[#06B6D4]">{project.name}</p>
                    <p className="text-[10px] font-mono text-[#6b7280]">/{project.owner_handle}/{project.slug}</p>
                  </div>
                </div>
                <p className="text-sm text-[#6b7280] mb-6">
                  {project.tagline || "Public request board for roadmap planning and bug triage."}
                </p>
                <div className="flex items-center justify-between text-[10px] font-mono font-bold uppercase tracking-wide">
                  <span className="text-[#6b7280]">{toReadableCount(project.issues_count)} Requests</span>
                  <span className="text-[#06B6D4]">View Board</span>
                </div>
              </a>
            ))}
          </div>
        </section>

        <section id="features" className="py-20 bg-white border-y border-[#e5e7eb]">
          <div className="max-w-7xl mx-auto px-4 grid grid-cols-1 md:grid-cols-3 gap-12">
            <div className="space-y-4">
              <div className="w-12 h-12 bg-[#f3f4f6] rounded-sm-ds flex items-center justify-center text-[#111827]">
                <ArrowBigUpDash size={22} />
              </div>
              <h3 className="font-bold text-lg">Community Prioritization</h3>
              <p className="text-sm text-[#6b7280] leading-relaxed">
                Let your users vote on features. Sort requests by popularity and move the roadmap with confidence.
              </p>
            </div>
            <div className="space-y-4">
              <div className="w-12 h-12 bg-[#f3f4f6] rounded-sm-ds flex items-center justify-center text-[#111827]">
                <MessageSquare size={22} />
              </div>
              <h3 className="font-bold text-lg">Native Discussion</h3>
              <p className="text-sm text-[#6b7280] leading-relaxed">
                Discuss requirements and implementation details directly per request instead of scattered threads.
              </p>
            </div>
            <div className="space-y-4">
              <div className="w-12 h-12 bg-[#f3f4f6] rounded-sm-ds flex items-center justify-center text-[#111827]">
                <Lock size={22} />
              </div>
              <h3 className="font-bold text-lg">Public or Private</h3>
              <p className="text-sm text-[#6b7280] leading-relaxed">
                Build in public with open boards or keep sensitive feedback private with board-level control.
              </p>
            </div>
          </div>
        </section>

        <section id="pricing" className="py-20 px-4">
          <div className="mx-auto max-w-3xl bg-[#111827] rounded-md-ds p-12 text-center text-white space-y-8 shadow-2xl">
            <h2 className="text-3xl font-bold">Ready to listen to your users?</h2>
            <p className="text-[#9ca3af] max-w-md mx-auto">
              Bring your feedback loop to one place and let your community shape your roadmap.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <button
                type="button"
                onClick={() => openAuth("signUp")}
                className="w-full sm:w-auto px-8 py-3 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all uppercase tracking-wide"
              >
                Start for free
              </button>
              <span className="text-[#6b7280] font-mono text-[10px] uppercase tracking-widest">No credit card required</span>
            </div>
          </div>
        </section>
      </main>

      <footer className="bg-white border-t border-[#e5e7eb] py-8 px-4">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-[#06B6D4] rounded-sm-ds flex items-center justify-center text-white">
              <Layers size={14} />
            </div>
            <span className="text-sm font-bold tracking-tight">FeatureRequest</span>
            <span className="text-[10px] font-mono text-[#9ca3af] ml-2">© 2026</span>
          </div>
          <div className="flex items-center gap-6">
            <a href="#" className="text-xs font-medium text-[#6b7280] hover:text-[#111827]">
              Privacy
            </a>
            <a href="#" className="text-xs font-medium text-[#6b7280] hover:text-[#111827]">
              Terms
            </a>
            <a href="#" className="text-xs font-medium text-[#6b7280] hover:text-[#111827]">
              Contact
            </a>
            <div className="flex items-center gap-3 ml-4">
              <a href="#" className="text-[#6b7280] hover:text-[#111827]">
                <Sparkles size={14} />
              </a>
              <a href="#" className="text-[#6b7280] hover:text-[#111827]">
                <Palette size={14} />
              </a>
            </div>
          </div>
        </div>
      </footer>

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

            <div className="flex min-h-[374px] flex-col">
              {authMode === "signIn" ? (
                <form className="flex flex-1 flex-col" onSubmit={onSignInSubmit}>
                  <div className="flex-1 space-y-4 p-6">
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
                  </div>
                  <div className="flex justify-end gap-3 bg-[#f9fafb] border-t border-[#e5e7eb] p-3">
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
                <form className="flex flex-1 flex-col" onSubmit={onSignUpSubmit}>
                  <div className="flex-1 space-y-4 p-6">
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
                        placeholder="yourhandle"
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
                        placeholder="you@indie.dev"
                      />
                    </div>
                    {authFeedback ? <p className="text-xs text-[#6b7280]">{authFeedback}</p> : null}
                  </div>
                  <div className="flex justify-end gap-3 bg-[#f9fafb] border-t border-[#e5e7eb] p-3">
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
