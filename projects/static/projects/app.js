(() => {
  const TYPE_OPTIONS = [
    { value: "", label: "All Types" },
    { value: "feature", label: "Feature" },
    { value: "bug", label: "Bug" },
  ];

  const STATUS_OPTIONS = [
    { value: "", label: "All Statuses" },
    { value: "open", label: "Open" },
    { value: "planned", label: "Planned" },
    { value: "in_progress", label: "In Progress" },
    { value: "done", label: "Done" },
    { value: "closed", label: "Closed" },
  ];

  const DETAIL_STATUS_OPTIONS = STATUS_OPTIONS.filter((item) => item.value);

  const PRIORITY_OPTIONS = [
    { value: "", label: "All Priorities" },
    { value: "1", label: "Low" },
    { value: "2", label: "Medium" },
    { value: "3", label: "High" },
    { value: "4", label: "Critical" },
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

  const PRICING_PLANS = [
    {
      id: "free",
      title: "Starter",
      name: "Free",
      description: "Free for 1 project",
      cta: "Start free",
    },
    {
      id: "pro_30",
      title: "Growth",
      name: "Pro",
      description: "$3/mo for up to 30 projects",
      cta: "Upgrade",
    },
  ];

  const PROJECT_UPGRADE_PLAN = {
    id: "pro_30",
    title: "Growth",
    name: "Pro",
    description: "$3/mo for up to 30 projects",
    cta: "Upgrade",
  };

  const APP_NAME = "Feature Request";
  const APP_BASE_DESCRIPTION =
    "Feature Request helps you collect, prioritize, and manage feedback, feature requests, and bug reports for your projects.";
  const FEATURE_REQUEST_SKILL_PATH = ".agents/skills/feature-request/SKILL.md";
  const AGENT_PROMPT_PRESETS = [
    {
      value: "portfolio-triage",
      label: "Portfolio triage",
      description: "Read-only queue snapshot across all owned projects.",
    },
    {
      value: "project-triage",
      label: "Project triage",
      description: "Read-only queue snapshot for one selected project.",
    },
    {
      value: "project-implementation",
      label: "Project implementation",
      description: "Plan and implement one ready issue in the local repo.",
    },
  ];
  const PROJECT_AGENT_PROMPT_PRESETS = new Set(["project-triage", "project-implementation"]);
  const HANDLE_REGEX = /^[a-z0-9_]+$/;
  const SETTINGS_SECTIONS = new Set(["general", "api", "connect-agent"]);

  const ADMIN_PATH = (() => {
    const raw = typeof window.__FR_ADMIN_PATH__ === "string" ? window.__FR_ADMIN_PATH__ : "/admin/";
    const segment = String(raw || "").trim().replace(/^\/+|\/+$/g, "");
    return segment ? `/${segment}/` : "/admin/";
  })();
  const ADMIN_PATH_PARTS = ADMIN_PATH.split("/").filter(Boolean).map((segment) => normalizeHandle(segment));
  const RESERVED_HANDLES = new Set(["messages", "settings", ADMIN_PATH_PARTS[0]].filter(Boolean));

  const root = document.getElementById("app");
  const bootstrap = window.__FR_BOOTSTRAP__ || {};
  const isInitialMobileViewport =
    typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767px)").matches;

  const state = {
    projects: [],
    interactedProjects: [],
    issues: [],
    comments: [],
    selectedProjectSlug: "",
    selectedIssueId: null,
    isIssueDetailOpen: false,
    typeFilter: "",
    statusFilter: "open",
    priorityFilter: "",
    searchQuery: "",
    statusLine: "",
    statusError: false,
    view: "issues",
    isRouteNotFound: false,
    isBooting: false,
    loadedCommentsIssueId: null,
    commentDraft: "",
    commentFeedback: "",
    isCommentSubmitting: false,
    editingCommentId: null,
    commentEditDraft: "",
    commentEditFeedback: "",
    isCommentEditSubmitting: false,
    isIssueUpdating: false,
    isIssueEditOpen: false,
    issueTitleDraft: "",
    issueDescriptionDraft: "",
    issueEditFeedback: "",
    messages: [],
    isMessagesLoading: false,
    selectedMessageThreadId: "",
    messageSidebarProjects: [],
    isMessageSidebarProjectsLoading: false,
    isInteractedProjectsLoading: false,
    projectSidebarSectionsOpen: {
      owned: !isInitialMobileViewport,
      interacted: false,
    },
    messageComposerBody: "",
    messageComposerFeedback: "",
    messageComposerFeedbackTone: "",
    isMessageComposerSubmitting: false,
    apiTokens: [],
    apiTokenSecrets: {},
    isApiTokensLoading: false,
    apiTokenFeedback: "",
    apiTokenFeedbackTone: "",
    agentPromptCopyFeedback: "",
    agentPromptCopyFeedbackTone: "",
    latestCreatedTokenValue: "",
    agentPromptValue: "",
    agentPromptPreset: "portfolio-triage",
    agentPromptProjectSlug: "",
    agentPromptProjects: [],
    isAgentPromptProjectsLoading: false,
    isAgentRefreshSubmitting: false,
    isContactOpen: false,
    contactSenderName: "",
    contactSenderEmail: "",
    contactBody: "",
    contactFeedback: "",
    contactFeedbackTone: "",
    isContactSubmitting: false,
    isNewIssueOpen: false,
    newIssueTitle: "",
    newIssueDescription: "",
    newIssueType: "feature",
    newIssuePriority: "2",
    newIssueFeedback: "",
    isNewIssueSubmitting: false,
    isDeleteModalOpen: false,
    deleteSlugConfirm: "",
    projectNameDraft: "",
    projectTaglineDraft: "",
    projectUrlDraft: "",
    projectFeedback: "",
    projectFeedbackTone: "",
    projectDraftProjectId: null,
    isProjectSaving: false,
    isNewProjectSubmitting: false,
    newProjectFeedback: "",
    newProjectFeedbackTone: "",
    isProjectDeleting: false,
    isUpgradePlanOpen: false,
    isUpgradePlanSubmitting: false,
    upgradePlanFeedback: "",
    isAuthenticated: Boolean(bootstrap.isAuthenticated),
    currentUserHandle: String(bootstrap.currentUserHandle || "").trim(),
    currentUserAvatarUrl: String(bootstrap.currentUserAvatarUrl || "").trim(),
    subscriptionTier: String(bootstrap.subscription_tier || "free").toLowerCase(),
    subscriptionStatus: String(bootstrap.subscription_status || "").toLowerCase(),
    projectLimit: Number(bootstrap.project_limit || 1),
    signInIdentity: "",
    signUpEmail: "",
    signUpHandle: "",
    authMode: null,
    authFeedback: "",
    isAuthSubmitting: false,
    isProfileMenuOpen: false,
    isPricingOpen: false,
    selectedPlanId: "free",
    pricingFeedback: "",
    isPricingSubmitting: false,
    ownerHandle: "",
  };

  const ICONS = {
    "alert-triangle": '<path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    bot: '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "external-link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    key: '<path d="m15.5 7.5 2 2"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>',
    "layout-dashboard": '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "list-todo": '<rect x="3" y="5" width="6" height="6" rx="1"/><path d="m3 17 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    message: '<path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>',
    "message-square": '<path d="M21 15a4 4 0 0 1-4 4H7l-4 4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/>',
    pencil: '<path d="M21.17 6.83a2.82 2.82 0 0 0-4-4L3 17v4h4Z"/><path d="m15 5 4 4"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8A2 2 0 0 1 21 8.8V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.09a2 2 0 0 1-1-1.74v-.51a2 2 0 0 1 1-1.72l.15-.1a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "thumbs-up": '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  };

  function normalizeHandle(value) {
    return String(value || "").trim().toLowerCase();
  }

  function cls(...values) {
    return values.filter(Boolean).join(" ");
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  }

  function icon(name, size = 16, className = "") {
    const paths = ICONS[name] || "";
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="${escapeAttr(className)}" aria-hidden="true">${paths}</svg>`;
  }

  function selectedAttr(value, current) {
    return String(value) === String(current) ? " selected" : "";
  }

  function disabledAttr(value) {
    return value ? " disabled" : "";
  }

  function renderOptions(options, selectedValue) {
    return options
      .map((option) => `<option value="${escapeAttr(option.value)}"${selectedAttr(option.value, selectedValue)}>${escapeHtml(option.label)}</option>`)
      .join("");
  }

  function isValidHandle(value) {
    return HANDLE_REGEX.test(normalizeHandle(value));
  }

  function isReservedHandle(value) {
    return RESERVED_HANDLES.has(normalizeHandle(value));
  }

  function isAdminRoute(pathname = window.location.pathname) {
    const pathParts = String(pathname || "").split("/").filter(Boolean).map((part) => normalizeHandle(part));
    if (!ADMIN_PATH_PARTS.length || pathParts.length < ADMIN_PATH_PARTS.length) {
      return false;
    }
    return ADMIN_PATH_PARTS.every((segment, index) => pathParts[index] === segment);
  }

  function isLandingRoute(pathname = window.location.pathname) {
    const pathParts = String(pathname || "").split("/").filter(Boolean);
    const first = normalizeHandle(pathParts[0] || "");
    return !pathParts.length || ["sign-in", "signin", "login", "sign-up", "signup"].includes(first);
  }

  function initialAuthModeFromRoute(pathname = window.location.pathname) {
    const first = normalizeHandle(String(pathname || "").split("/").filter(Boolean)[0] || "");
    if (first === "sign-up" || first === "signup") {
      return "signUp";
    }
    if (first === "sign-in" || first === "signin" || first === "login") {
      return "signIn";
    }
    return null;
  }

  function parseRoute(pathname = window.location.pathname) {
    const pathParts = String(pathname || "").split("/").filter(Boolean);
    if (!pathParts.length) {
      return { kind: "landing" };
    }

    const first = normalizeHandle(pathParts[0]);
    if (["sign-in", "signin", "login", "sign-up", "signup"].includes(first)) {
      return pathParts.length === 1 ? { kind: "landing" } : { kind: "notFound" };
    }

    if (first === "messages") {
      if (pathParts.length > 2) {
        return { kind: "notFound" };
      }
      const selectedMessageHandle = normalizeHandle(pathParts[1] || "");
      if (selectedMessageHandle && (!isValidHandle(selectedMessageHandle) || isReservedHandle(selectedMessageHandle))) {
        return { kind: "notFound" };
      }
      return { kind: "messages", selectedMessageHandle };
    }

    if (first === "settings") {
      if (pathParts.length === 1) {
        return { kind: "settings", section: "general" };
      }
      if (pathParts.length === 2 && SETTINGS_SECTIONS.has(normalizeHandle(pathParts[1]))) {
        return { kind: "settings", section: normalizeHandle(pathParts[1]) };
      }
      return { kind: "notFound" };
    }

    if (isAdminRoute(pathname) || !isValidHandle(first) || isReservedHandle(first)) {
      return { kind: "notFound" };
    }

    if (pathParts.length === 1) {
      return { kind: "board", ownerHandle: first, projectSlug: "", isProjectFormRoute: false };
    }
    if (pathParts.length === 2) {
      return { kind: "board", ownerHandle: first, projectSlug: String(pathParts[1] || ""), isProjectFormRoute: false };
    }
    if (pathParts.length === 3 && pathParts[1] === "projects" && pathParts[2] === "new") {
      return { kind: "board", ownerHandle: first, projectSlug: "", isProjectFormRoute: true };
    }
    return { kind: "notFound" };
  }

  function settingsSectionToView(section) {
    if (section === "api") {
      return "settingsApi";
    }
    if (section === "connect-agent") {
      return "settingsConnectAgent";
    }
    return "settingsGeneral";
  }

  function viewToSettingsSection(view) {
    if (view === "settingsApi") {
      return "api";
    }
    if (view === "settingsConnectAgent") {
      return "connect-agent";
    }
    return "general";
  }

  function messageThreadIdFromHandle(handle) {
    const normalized = normalizeHandle(handle);
    return normalized ? `handle:${normalized}` : "";
  }

  function getHandleFromThreadId(threadId) {
    if (!String(threadId || "").startsWith("handle:")) {
      return "";
    }
    return normalizeHandle(String(threadId).replace("handle:", ""));
  }

  function applyRouteToState() {
    const route = parseRoute();
    state.isRouteNotFound = route.kind === "notFound";
    if (route.kind === "board") {
      const nextOwnerHandle = normalizeHandle(route.ownerHandle);
      if (state.ownerHandle && state.ownerHandle !== nextOwnerHandle) {
        state.projects = [];
        state.interactedProjects = [];
        state.issues = [];
        state.comments = [];
        state.selectedIssueId = null;
        state.isIssueDetailOpen = false;
        state.loadedCommentsIssueId = null;
      }
      state.ownerHandle = nextOwnerHandle;
      state.selectedProjectSlug = route.isProjectFormRoute ? "" : String(route.projectSlug || "");
      state.isIssueDetailOpen = false;
      state.view = route.isProjectFormRoute ? "newProject" : "issues";
      return;
    }
    if (route.kind === "messages") {
      state.ownerHandle = "";
      state.view = "messages";
      state.selectedMessageThreadId = messageThreadIdFromHandle(route.selectedMessageHandle);
      return;
    }
    if (route.kind === "settings") {
      state.ownerHandle = "";
      state.view = settingsSectionToView(route.section);
      return;
    }
  }

  function csrfTokenFromCookie() {
    const tokenPart = document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith("csrftoken="));
    return tokenPart ? decodeURIComponent(tokenPart.slice("csrftoken=".length)) : "";
  }

  async function ensureCsrfCookie() {
    await fetch("/auth/me");
  }

  function authSignInEndpoint({ useCurrentPathAsNext = false } = {}) {
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

  function getPostAuthRedirect(handle, { useCurrentPathAsFallback = false } = {}) {
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

  function detailFromPayload(payload, fallback) {
    if (typeof payload?.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload?.detail) && payload.detail.length) {
      return payload.detail.map((item) => item.msg || item.message || String(item)).join(" ");
    }
    return fallback;
  }

  async function jsonOrEmpty(response) {
    return response.json().catch(() => ({}));
  }

  function setStatus(text, isError = false) {
    state.statusLine = text;
    state.statusError = Boolean(isError);
  }

  function toReadableStatus(status) {
    if (status === "in_progress") {
      return "In Progress";
    }
    return String(status || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function toReadableType(value) {
    return value === "bug" ? "Bug" : "Feature";
  }

  function toReadablePriority(priority) {
    const map = { 1: "Low", 2: "Medium", 3: "High", 4: "Critical" };
    return map[Number(priority)] || "Priority";
  }

  function priorityTone(priority) {
    const map = {
      1: "border-emerald-100 text-emerald-700",
      2: "border-blue-100 text-blue-700",
      3: "border-amber-100 text-amber-700",
      4: "border-rose-100 text-rose-700",
    };
    return map[Number(priority)] || "border-gray-100 text-gray-500";
  }

  function statusTone(status) {
    const map = {
      open: "border-gray-100 text-gray-500",
      planned: "border-blue-100 text-blue-700",
      in_progress: "border-emerald-100 text-emerald-700",
      done: "border-cyan-100 text-cyan-700",
      closed: "border-zinc-200 text-zinc-500",
    };
    return map[status] || "border-gray-100 text-gray-500";
  }

  function typeTone(type) {
    return type === "bug" ? "border-rose-100 text-rose-700" : "border-purple-100 text-purple-700";
  }

  function methodTone(method) {
    const value = String(method || "").toUpperCase();
    if (value === "POST") {
      return "text-[#16a34a]";
    }
    if (value === "DELETE") {
      return "text-[#dc2626]";
    }
    return "text-[#06B6D4]";
  }

  function formatRelativeDate(isoString) {
    if (!isoString) {
      return "-";
    }
    const diff = Date.now() - new Date(isoString).getTime();
    if (!Number.isFinite(diff)) {
      return "-";
    }
    const minute = 60 * 1000;
    const hour = 60 * minute;
    const day = 24 * hour;
    if (diff < hour) {
      return `${Math.max(1, Math.round(diff / minute))}m ago`;
    }
    if (diff < day) {
      return `${Math.round(diff / hour)}h ago`;
    }
    return `${Math.round(diff / day)}d ago`;
  }

  function formatLongDate(isoString) {
    if (!isoString) {
      return "-";
    }
    const date = new Date(isoString);
    if (!Number.isFinite(date.getTime())) {
      return "-";
    }
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
    }).format(date);
  }

  function safeEpoch(value) {
    const timestamp = Date.parse(String(value || ""));
    return Number.isFinite(timestamp) ? timestamp : 0;
  }

  function trimForPreview(value, maxLength = 100) {
    const text = String(value || "").trim();
    if (!text || text.length <= maxLength) {
      return text;
    }
    return `${text.slice(0, maxLength).trimEnd()}...`;
  }

  function getProjectListMetaText(project) {
    const tagline = String(project?.tagline || "").trim();
    if (tagline) {
      return tagline;
    }
    const projectUrl = String(project?.url || "").trim();
    if (!projectUrl) {
      return "";
    }
    return projectUrl.replace(/^https?:\/\//i, "").replace(/\/+$/, "");
  }

  function agentTokenStorageKey(handle) {
    return `fr_agent_token_secret:${normalizeHandle(handle || "anonymous")}`;
  }

  function readStoredAgentToken(handle) {
    try {
      return String(window.localStorage.getItem(agentTokenStorageKey(handle)) || "");
    } catch {
      return "";
    }
  }

  function writeStoredAgentToken(handle, tokenValue) {
    const value = String(tokenValue || "").trim();
    if (!value) {
      return;
    }
    try {
      window.localStorage.setItem(agentTokenStorageKey(handle), value);
    } catch {
      // Storage can fail in private browsing; the visible token still works.
    }
  }

  function agentSkillCatalogUrl(baseUrl) {
    const baseOrigin = String(baseUrl || "").replace(/\/+$/, "");
    return `${baseOrigin}/${FEATURE_REQUEST_SKILL_PATH}`;
  }

  function normalizeAgentPromptPreset(value) {
    const candidate = String(value || "").trim();
    return AGENT_PROMPT_PRESETS.some((preset) => preset.value === candidate) ? candidate : "portfolio-triage";
  }

  function isProjectAgentPromptPreset(value) {
    return PROJECT_AGENT_PROMPT_PRESETS.has(normalizeAgentPromptPreset(value));
  }

  function buildAgentPromptText(baseUrl, tokenValue, options = {}) {
    const baseOrigin = String(baseUrl || "").replace(/\/+$/, "");
    const token = String(tokenValue || "YOUR_AGENT_TOKEN").trim() || "YOUR_AGENT_TOKEN";
    const preset = normalizeAgentPromptPreset(options.preset);
    const project = options.project || null;
    const ownerHandle = normalizeHandle(options.ownerHandle || project?.owner_handle || "");
    const projectSlug = String(options.projectSlug || project?.slug || "").trim();
    const projectName = String(project?.name || projectSlug || "selected project").trim();
    const commonLines = [
      "Use the FeatureRequest skill to manage feature requests via API.",
      "",
      `API token: ${token}`,
      `Base URL: ${baseOrigin}`,
      `Skill catalog: ${agentSkillCatalogUrl(baseOrigin)}`,
      "",
      "Authentication: use Authorization: Bearer <API token> for API calls.",
      "If the token is already provided above, do not call the agent-token connect/refresh endpoints; those endpoints are only for web-session onboarding.",
    ];

    if (preset === "project-triage") {
      return commonLines
        .concat([
          "",
          "Preset: Project triage",
          "Scope:",
          `- owner_handle: ${ownerHandle || "<owner_handle>"}`,
          `- project_slug: ${projectSlug || "<project_slug>"}`,
          `- project_name: ${projectName}`,
          "- Only read FeatureRequest issues for this exact owner/project. Do not read or change other projects.",
          `- Use GET ${baseOrigin}/api/projects/${ownerHandle || "<owner_handle>"}/${projectSlug || "<project_slug>"}/issues with status/type/priority filters as needed.`,
          "",
          "Return Queue Snapshot, Priority Decisions, Active Follow-ups, Risks and Blockers, and Next Checkpoint.",
          "Do not make code changes or FeatureRequest write calls in this triage run.",
        ])
        .join("\n");
    }

    if (preset === "project-implementation") {
      return commonLines
        .concat([
          "",
          "Preset: Project implementation",
          "Scope:",
          `- owner_handle: ${ownerHandle || "<owner_handle>"}`,
          `- project_slug: ${projectSlug || "<project_slug>"}`,
          `- project_name: ${projectName}`,
          "- Only use FeatureRequest issues for this exact owner/project. Do not read or change other projects.",
          `- Read ready candidates from GET ${baseOrigin}/api/projects/${ownerHandle || "<owner_handle>"}/${projectSlug || "<project_slug>"}/issues.`,
          "",
          "Implementation rules:",
          "- FeatureRequest is the ticket source of truth; perform code work only in the local repository where this agent is running.",
          "- Pick at most one ready issue per run unless the user explicitly says otherwise.",
          "- Treat open and planned issues as candidates; prefer critical/high priority and clear acceptance criteria.",
          "- Before code changes, produce a short implementation plan.",
          "- Run relevant tests after edits.",
          "- After implementation, add a concise comment back to the issue when write access is available.",
          "- Do not mark the issue done automatically; reserve done/closed for merge or release confirmation.",
        ])
        .join("\n");
    }

    return commonLines
      .concat([
        "",
        "Preset: Portfolio triage",
        "Scope:",
        "- Read all projects owned by the authenticated user with GET /api/projects.",
        "- Read issue queues for those projects only.",
        "- Do not make code changes or FeatureRequest write calls.",
        "",
        "Return Queue Snapshot, Priority Decisions, Active Follow-ups, Risks and Blockers, and Next Checkpoint.",
      ])
      .join("\n");
  }

  async function copyToClipboard(value) {
    const text = String(value || "");
    if (!text) {
      return false;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // Fallback below.
    }
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "true");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.focus({ preventScroll: true });
      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);
      const copied = document.execCommand("copy");
      document.body.removeChild(textarea);
      return copied;
    } catch {
      return false;
    }
  }

  function markdownInline(value) {
    let html = escapeHtml(value);
    html = html.replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\n]+|\/[^)\n]+)\)/g, (_match, label, href) => {
      const safeHref = escapeAttr(href);
      const external = href.startsWith("http");
      return `<a href="${safeHref}"${external ? ' target="_blank" rel="noopener noreferrer"' : ""} class="text-[#06B6D4] underline underline-offset-2">${escapeHtml(label)}</a>`;
    });
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");
    html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    html = html.replace(/_([^_\n]+)_/g, "<em>$1</em>");
    return html;
  }

  function markdownContent(value, fallback = "") {
    const content = String(value || "").trim();
    if (!content) {
      return `<p>${escapeHtml(fallback)}</p>`;
    }
    const lines = content.replaceAll("\r\n", "\n").split("\n");
    const blocks = [];
    let paragraph = [];
    let list = null;

    function flushParagraph() {
      if (!paragraph.length) {
        return;
      }
      const body = paragraph.map((line, index) => `<span class="${index ? "block mt-1" : "block"}">${markdownInline(line)}</span>`).join("");
      blocks.push(`<p class="mb-4 leading-relaxed">${body}</p>`);
      paragraph = [];
    }

    function flushList() {
      if (!list || !list.items.length) {
        list = null;
        return;
      }
      const tag = list.ordered ? "ol" : "ul";
      const clsName = list.ordered ? "pl-5 mb-4 list-decimal space-y-2" : "pl-5 mb-4 list-disc space-y-2";
      blocks.push(`<${tag} class="${clsName}">${list.items.map((item) => `<li>${markdownInline(item)}</li>`).join("")}</${tag}>`);
      list = null;
    }

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
      const unorderedListMatch = line.match(/^\s*[-*]\s+(.*)$/);
      const orderedListMatch = line.match(/^\s*\d+\.\s+(.*)$/);
      if (line.startsWith("```")) {
        flushParagraph();
        flushList();
        const codeLines = [];
        for (i += 1; i < lines.length; i += 1) {
          if (lines[i].trim() === "```") {
            break;
          }
          codeLines.push(lines[i]);
        }
        blocks.push(`<pre class="bg-[#0b1220] text-[#e5e7eb] p-3 rounded-sm-ds mb-4 overflow-x-auto"><code class="font-mono text-xs leading-relaxed">${escapeHtml(codeLines.join("\n"))}</code></pre>`);
        continue;
      }
      if (headingMatch) {
        flushParagraph();
        flushList();
        const level = Math.min(headingMatch[1].length, 6);
        blocks.push(`<h${level} class="font-bold text-[#111827] mt-1 mb-2 last:mb-0">${markdownInline(headingMatch[2].trim())}</h${level}>`);
        continue;
      }
      if (unorderedListMatch || orderedListMatch) {
        if (!list || list.ordered !== Boolean(orderedListMatch)) {
          flushList();
          list = { ordered: Boolean(orderedListMatch), items: [] };
        }
        list.items.push(unorderedListMatch ? unorderedListMatch[1] : orderedListMatch[1]);
        continue;
      }
      if (!line.trim()) {
        flushParagraph();
        flushList();
        continue;
      }
      paragraph.push(line);
    }
    flushParagraph();
    flushList();
    return `<div class="prose prose-sm max-w-none space-y-1">${blocks.join("")}</div>`;
  }

  function getComputed() {
    const selectedProject = state.projects.find((project) => project.slug === state.selectedProjectSlug) || null;
    const query = state.searchQuery.trim().toLowerCase();
    const filteredIssues = query
      ? state.issues.filter((issue) => {
          const title = String(issue.title || "").toLowerCase();
          const description = String(issue.description || "").toLowerCase();
          return title.includes(query) || description.includes(query);
        })
      : state.issues;
    const selectedIssue =
      filteredIssues.find((issue) => issue.id === state.selectedIssueId) || filteredIssues[0] || null;
    const isOwnerViewer =
      state.isAuthenticated &&
      normalizeHandle(state.currentUserHandle) === normalizeHandle(state.ownerHandle);
    const workspaceOwnerHandle = normalizeHandle(state.currentUserHandle) || normalizeHandle(state.ownerHandle);
    const isGlobalSettingsView = ["settingsGeneral", "settingsApi", "settingsConnectAgent"].includes(state.view);
    const route = parseRoute();
    const messageRouteHandle = route.kind === "messages" ? normalizeHandle(route.selectedMessageHandle || "") : "";
    const messageSidebarProjectsOwnerHandle = messageRouteHandle || normalizeHandle(state.currentUserHandle);
    const sidebarProjectsOwnerHandle =
      state.view === "messages" ? messageSidebarProjectsOwnerHandle : normalizeHandle(state.ownerHandle);
    const isSidebarOwnerViewer =
      state.isAuthenticated && normalizeHandle(state.currentUserHandle) === sidebarProjectsOwnerHandle;
    const ownedProjectsTitle = isSidebarOwnerViewer
      ? "My Projects"
      : sidebarProjectsOwnerHandle
        ? `@${sidebarProjectsOwnerHandle}'s Projects`
        : "Projects";
    const interactedProjectsTitle = isSidebarOwnerViewer
      ? "Projects you've interacted with"
      : sidebarProjectsOwnerHandle
        ? `Projects @${sidebarProjectsOwnerHandle} interacted with`
        : "Projects interacted with";
    const projectLimitToUse = Number(state.projectLimit || 1);
    const hasActivePaidPlan =
      projectLimitToUse > 1 || (state.subscriptionTier === "pro_30" && !state.subscriptionStatus);
    const isAtProjectLimit = isOwnerViewer && !hasActivePaidPlan && state.projects.length >= projectLimitToUse;
    const apiBaseUrl = window.location.origin.replace(/\/+$/, "");
    const apiTokens = Array.isArray(state.apiTokens) ? state.apiTokens : [];
    const activeAgentToken = apiTokens.length ? apiTokens[0] : null;
    const activeAgentTokenSecret = activeAgentToken ? String(state.apiTokenSecrets[activeAgentToken.id] || "") : "";
    const visibleAgentTokenValue =
      activeAgentTokenSecret ||
      state.latestCreatedTokenValue ||
      (activeAgentToken ? `${activeAgentToken.token_prefix}••••••••` : "");
    const agentPromptProjects = Array.isArray(state.agentPromptProjects) ? state.agentPromptProjects : [];
    const selectedAgentPromptProject =
      agentPromptProjects.find((project) => project.slug === state.agentPromptProjectSlug) ||
      agentPromptProjects[0] ||
      null;
    const agentPromptPreset = normalizeAgentPromptPreset(state.agentPromptPreset);
    const agentPromptProject = isProjectAgentPromptPreset(agentPromptPreset) ? selectedAgentPromptProject : null;
    const promptTextValue = buildAgentPromptText(apiBaseUrl, activeAgentTokenSecret || state.latestCreatedTokenValue, {
      preset: agentPromptPreset,
      ownerHandle: normalizeHandle(state.currentUserHandle),
      project: agentPromptProject,
    });
    const messageThreads = buildMessageThreads();
    const selectedMessageThread =
      messageThreads.find((thread) => thread.threadId === state.selectedMessageThreadId) || null;
    const selectedMessageHandle =
      selectedMessageThread?.correspondentHandle || getHandleFromThreadId(state.selectedMessageThreadId);
    const canSendDirectMessage = Boolean(
      state.isAuthenticated &&
        normalizeHandle(selectedMessageHandle) &&
        normalizeHandle(selectedMessageHandle) !== normalizeHandle(state.currentUserHandle),
    );

    return {
      selectedProject,
      filteredIssues,
      selectedIssue,
      isOwnerViewer,
      workspaceOwnerHandle,
      isGlobalSettingsView,
      isApiAccessView: state.view === "settingsApi",
      isConnectAgentView: state.view === "settingsConnectAgent",
      isSettingsGeneralView: state.view === "settingsGeneral",
      sidebarProjectsOwnerHandle,
      isSidebarOwnerViewer,
      sidebarProjectsTitle: isSidebarOwnerViewer
        ? "My projects"
        : sidebarProjectsOwnerHandle
          ? `${sidebarProjectsOwnerHandle}'s projects`
          : "Projects",
      ownedProjectsTitle,
      interactedProjectsTitle,
      isAtProjectLimit,
      apiBaseUrl,
      activeAgentToken,
      activeAgentTokenSecret,
      visibleAgentTokenValue,
      canCopyActiveAgentToken: Boolean(activeAgentTokenSecret),
      agentPromptProjects,
      selectedAgentPromptProject,
      agentPromptPreset,
      promptTextValue: String(promptTextValue || "").trim(),
      messageThreads,
      selectedMessageThread,
      selectedMessageHandle,
      canSendDirectMessage,
      messageSidebarProjectsOwnerHandle,
    };
  }

  function buildMessageThreads() {
    const viewerHandle = normalizeHandle(state.currentUserHandle);
    const grouped = new Map();
    for (const message of state.messages) {
      const senderHandle = normalizeHandle(message.sender_handle);
      const recipientHandle = normalizeHandle(message.recipient_handle);
      const isOutgoing = Boolean(senderHandle) && senderHandle === viewerHandle;
      const correspondentHandle = isOutgoing ? recipientHandle : senderHandle;
      const correspondentEmail = isOutgoing ? "" : String(message.sender_email || "").trim();
      const correspondentName = isOutgoing ? `@${recipientHandle}` : String(message.sender_name || "").trim();
      const threadId = getMessageThreadId(correspondentHandle, correspondentEmail);
      const existing =
        grouped.get(threadId) || {
          threadId,
          correspondentHandle,
          correspondentName,
          correspondentEmail,
          messages: [],
          latestMessageEpoch: 0,
          latestMessageAt: "",
          latestMessageText: "",
          isNewConversation: false,
        };
      existing.messages.push({ ...message, isOutgoing });
      const parsed = safeEpoch(message.created_at);
      if (parsed >= existing.latestMessageEpoch) {
        existing.latestMessageEpoch = parsed;
        existing.latestMessageAt = String(message.created_at || "");
        existing.latestMessageText = String(message.body || "");
      }
      grouped.set(threadId, existing);
    }
    const threads = [...grouped.values()]
      .map((thread) => ({
        ...thread,
        messages: thread.messages.sort((a, b) => safeEpoch(a.created_at) - safeEpoch(b.created_at)),
      }))
      .sort((a, b) => b.latestMessageEpoch - a.latestMessageEpoch);
    const selectedHandle = getHandleFromThreadId(state.selectedMessageThreadId);
    const selectedThreadId = messageThreadIdFromHandle(selectedHandle);
    if (selectedThreadId && !threads.some((thread) => thread.threadId === selectedThreadId)) {
      threads.unshift({
        threadId: selectedThreadId,
        correspondentHandle: selectedHandle,
        correspondentName: `@${selectedHandle}`,
        correspondentEmail: "",
        messages: [],
        latestMessageEpoch: Number.MAX_SAFE_INTEGER,
        latestMessageAt: "",
        latestMessageText: "",
        isNewConversation: true,
      });
    }
    return threads;
  }

  function getMessageThreadId(correspondentHandle, correspondentEmail) {
    const handle = normalizeHandle(correspondentHandle);
    if (handle) {
      return `handle:${handle}`;
    }
    const email = String(correspondentEmail || "").trim().toLowerCase();
    return `email:${email || "anonymous"}`;
  }

  function getMessageThreadLabel(thread) {
    if (thread?.correspondentHandle) {
      return `@${thread.correspondentHandle}`;
    }
    if (thread?.correspondentName) {
      return thread.correspondentName;
    }
    if (thread?.correspondentEmail) {
      return thread.correspondentEmail;
    }
    return "Guest";
  }

  function getMessageThreadLabelById(threadId) {
    if (!threadId) {
      return "No conversation selected";
    }
    if (threadId.startsWith("handle:")) {
      return `@${threadId.replace("handle:", "")}`;
    }
    if (threadId.startsWith("email:")) {
      return threadId.replace("email:", "") || "Guest";
    }
    return "Guest";
  }

  function userAvatar(imageUrl, label, sizeClass = "w-8 h-8", fallbackClassName = "bg-cyan-50 border border-cyan-100 text-[#06B6D4]", fallbackTextClassName = "text-[10px] font-bold") {
    const safeLabel = String(label || "").trim();
    const safeImageUrl = String(imageUrl || "").trim();
    if (!safeImageUrl) {
      const fallback = (safeLabel.slice(0, 2).toUpperCase() || "??");
      return `<div class="${sizeClass} rounded-full flex items-center justify-center shrink-0 ${fallbackClassName} ${fallbackTextClassName}">${escapeHtml(fallback)}</div>`;
    }
    return `<img src="${escapeAttr(safeImageUrl)}" alt="${escapeAttr(safeLabel || "user")} avatar" class="${sizeClass} rounded-full object-cover shrink-0 border border-cyan-100" referrerpolicy="no-referrer">`;
  }

  function projectIcon(project) {
    const faviconUrl = String(project?.favicon_url || "").trim();
    if (!faviconUrl) {
      return icon("folder", 18);
    }
    return `<span class="inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center text-[#6b7280]"><img src="${escapeAttr(faviconUrl)}" alt="${escapeAttr(project.name || "Project")} icon" class="h-[18px] w-[18px] rounded-sm-ds object-contain bg-white border border-[#e5e7eb] shrink-0" referrerpolicy="no-referrer" onerror="this.classList.add('hidden'); this.nextElementSibling.classList.remove('hidden');"><span class="hidden">${icon("folder", 18)}</span></span>`;
  }

  function projectBoardUrl(ownerHandle, slug = "") {
    const normalizedOwner = normalizeHandle(ownerHandle);
    return normalizedOwner ? `/${normalizedOwner}/${slug ? `${slug}/` : ""}` : "/";
  }

  function boardUrl(slug = "") {
    return projectBoardUrl(state.ownerHandle, slug);
  }

  function currentUserWorkspaceUrl() {
    const handle = normalizeHandle(state.currentUserHandle);
    return state.isAuthenticated && isValidHandle(handle) ? `/${handle}/` : "/";
  }

  function messagesUrl(handle = "") {
    const normalized = normalizeHandle(handle);
    return normalized ? `/messages/${normalized}/` : "/messages/";
  }

  function settingsUrl(section = "general") {
    if (section === "api") {
      return "/settings/api";
    }
    if (section === "connect-agent") {
      return "/settings/connect-agent";
    }
    return "/settings/";
  }

  function pageMeta(computed) {
    let title = APP_NAME;
    let description = APP_BASE_DESCRIPTION;
    const selectedProject = computed.selectedProject;
    const selectedIssue = computed.selectedIssue;
    if (state.isRouteNotFound) {
      title = `404 | ${APP_NAME}`;
      description = "The requested page could not be found.";
    } else if (state.view === "settingsApi") {
      title = `API Access | ${APP_NAME}`;
      description = "Manage API bearer tokens and endpoint quickstart guides for agent integrations.";
    } else if (state.view === "settingsConnectAgent") {
      title = `Connect Agent | ${APP_NAME}`;
      description = "Connect your agent, rotate token, and copy integration prompt.";
    } else if (state.view === "settingsGeneral") {
      title = `Settings | ${APP_NAME}`;
      description = "Manage global account settings for your workspace.";
    } else if (state.view === "messages") {
      title = `Messages | ${APP_NAME}`;
      description = "Review direct messages from people who contacted this board.";
    } else if (state.view === "projectSettings" && selectedProject?.name) {
      title = `${selectedProject.name} Settings | ${APP_NAME}`;
      description = `Manage project settings for ${selectedProject.name} on ${APP_NAME}.`;
    } else if (state.view === "newProject") {
      title = `New Project | ${APP_NAME}`;
    } else if (selectedIssue?.title && selectedProject?.name) {
      title = `${selectedIssue.title} - ${selectedProject.name} | ${APP_NAME}`;
      description = `View discussion and details for "${selectedIssue.title}" in ${selectedProject.name} on ${APP_NAME}.`;
    } else if (selectedProject?.name) {
      title = `${selectedProject.name} | ${APP_NAME}`;
      description = `${selectedProject.name}: ${selectedProject.tagline || "Feature request board and bug tracker."}`;
    } else if (state.ownerHandle) {
      title = `${state.ownerHandle}'s projects | ${APP_NAME}`;
      description = `${APP_NAME} board for ${state.ownerHandle} with public projects and requests.`;
    }
    return { title, description };
  }

  function updateHead(computed) {
    const meta = isLandingRoute()
      ? {
          title: "Feature Request",
          description: APP_BASE_DESCRIPTION,
        }
      : pageMeta(computed);
    document.title = meta.title;
    setMeta('meta[name="description"]', "name", "description", "content", meta.description);
    setMeta('meta[property="og:title"]', "property", "og:title", "content", meta.title);
    setMeta('meta[property="og:description"]', "property", "og:description", "content", meta.description);
  }

  function setMeta(selector, keyName, keyValue, attrName, attrValue) {
    let tag = document.querySelector(selector);
    if (!tag) {
      tag = document.createElement("meta");
      tag.setAttribute(keyName, keyValue);
      document.head.appendChild(tag);
    }
    tag.setAttribute(attrName, attrValue);
  }

  function render() {
    const activeElement = document.activeElement;
    const focusKey = activeElement?.dataset?.bind || "";
    const focusSelection =
      focusKey && typeof activeElement.selectionStart === "number"
        ? { start: activeElement.selectionStart, end: activeElement.selectionEnd }
        : null;
    const computed = getComputed();
    updateHead(computed);
    syncProjectDrafts(computed.selectedProject);

    root.innerHTML = isLandingRoute() ? renderLanding() : renderApplication(computed);
    if (focusKey && window.CSS?.escape) {
      const nextElement = getVisibleBoundElement(focusKey);
      if (nextElement) {
        nextElement.focus({ preventScroll: true });
        if (focusSelection && typeof nextElement.setSelectionRange === "function") {
          try {
            nextElement.setSelectionRange(focusSelection.start, focusSelection.end);
          } catch {
            // Some input types do not support selection ranges.
          }
        }
      }
    }
    ensureSelectedIssueComments(computed.selectedIssue);
  }

  function getVisibleBoundElement(focusKey) {
    const selector = `[data-bind="${CSS.escape(focusKey)}"]`;
    const candidates = [...root.querySelectorAll(selector)];
    return (
      candidates.find((element) => {
        const styles = window.getComputedStyle(element);
        return element.getClientRects().length > 0 && styles.visibility !== "hidden";
      }) ||
      candidates[0] ||
      null
    );
  }

  function syncProjectDrafts(selectedProject) {
    const nextProjectId = selectedProject?.id || null;
    if (state.projectDraftProjectId === nextProjectId) {
      return;
    }
    state.projectDraftProjectId = nextProjectId;
    state.deleteSlugConfirm = "";
    state.projectNameDraft = selectedProject?.name || "";
    state.projectTaglineDraft = selectedProject?.tagline || "";
    state.projectUrlDraft = selectedProject?.url || "";
    state.projectFeedback = "";
    state.projectFeedbackTone = "";
  }

  function ensureSelectedIssueComments(selectedIssue) {
    const nextId = selectedIssue?.id || null;
    if (state.loadedCommentsIssueId === nextId) {
      return;
    }
    state.loadedCommentsIssueId = nextId;
    state.comments = [];
    state.commentFeedback = "";
    state.isIssueEditOpen = false;
    state.issueTitleDraft = selectedIssue?.title || "";
    state.issueDescriptionDraft = selectedIssue?.description || "";
    state.issueEditFeedback = "";
    state.editingCommentId = null;
    state.commentEditDraft = "";
    state.commentEditFeedback = "";
    if (nextId) {
      refreshComments(nextId).catch(() => {
        state.comments = [];
        render();
      });
    }
  }

  function renderLanding() {
    const brandHref = currentUserWorkspaceUrl();
    return `
      <div class="min-h-screen bg-[#f3f4f6] text-[#111827]">
        <header class="sticky top-0 z-50 border-b border-[#e5e7eb] bg-white h-[56px] flex items-center px-4 md:px-8">
          <div class="mx-auto flex h-full w-full max-w-7xl items-center justify-between">
            <a href="${escapeAttr(brandHref)}" class="flex items-center gap-2">
              <div class="h-8 w-8 rounded-sm-ds bg-[#06B6D4] flex items-center justify-center text-white shadow-sm">${icon("list-todo", 18)}</div>
              <span class="text-lg font-bold tracking-tight">FeatureRequest</span>
            </a>
            <nav class="hidden items-center gap-8 md:flex">
              <a href="#features" class="text-sm font-medium text-[#6b7280] hover:text-[#111827] transition-colors">Features</a>
              <button type="button" data-action="open-pricing" class="text-sm font-medium text-[#6b7280] hover:text-[#111827] transition-colors">Pricing</button>
            </nav>
            <div class="flex items-center gap-4">
              ${
                state.isAuthenticated
                  ? `<a href="/${escapeAttr(state.currentUserHandle)}/" class="px-4 py-2 bg-[#111827] text-xs font-bold uppercase tracking-wide text-white rounded-sm-ds shadow-sm hover:bg-black transition-all">Open My Workspace</a>`
                  : `<button type="button" data-action="open-auth" data-mode="signIn" class="text-sm font-bold text-[#6b7280] transition-colors hover:text-[#111827] px-2">Sign in</button>
                     <button type="button" data-action="open-auth" data-mode="signUp" class="px-4 py-2 bg-[#111827] text-xs font-bold uppercase tracking-wide text-white rounded-sm-ds shadow-sm hover:bg-black transition-all">Get Started</button>`
              }
            </div>
          </div>
        </header>
        <main class="flex-1 overflow-y-auto relative">
          <section class="pt-16 pb-20 md:pt-24 md:pb-32 px-4 border-b border-[#e5e7eb] bg-white">
            <div class="mx-auto max-w-4xl text-center space-y-8">
              <h1 class="text-4xl md:text-6xl font-bold tracking-tight text-[#111827]">Ship the features your <span class="text-[#06B6D4]">users actually want</span></h1>
              <a href="#features" class="inline-flex items-center gap-2 px-3 py-1 bg-cyan-50 border border-cyan-100 rounded-sm-ds mx-auto hover:bg-cyan-100 transition-colors" aria-label="Jump to features">
                ${icon("bot", 14, "text-[#dc2626]")}
                <span class="text-[10px] font-mono font-bold text-[#dc2626] uppercase tracking-wider">New!</span>
                <span class="text-[10px] font-mono font-bold text-[#06B6D4] uppercase tracking-wider">Let your Agents manage your customer requests</span>
              </a>
              <p class="text-lg md:text-xl text-[#6b7280] max-w-2xl mx-auto leading-relaxed">The simplest way to manage feature requests, bug reports, and product feedback. Public boards, upvoting, and focused discussions for all your projects in one place.</p>
              <div class="flex flex-col sm:flex-row items-center justify-center gap-4">
                <button type="button" data-action="landing-create-board" class="w-full sm:w-auto px-8 py-3 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all uppercase tracking-wide">Create your Board</button>
                <a href="https://github.com/onurmatik/feature-request" target="_blank" rel="noopener noreferrer" class="w-full sm:w-auto px-8 py-3 bg-white border border-[#e5e7eb] text-[#111827] text-sm font-bold rounded-sm-ds hover:bg-[#f3f4f6] transition-all uppercase tracking-wide inline-flex items-center justify-center gap-2">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="h-4 w-4" aria-hidden="true"><path d="M12 2C6.477 2 2 6.485 2 12.013c0 4.425 2.866 8.184 6.839 9.504.5.092.682-.217.682-.482 0-.237-.008-.865-.013-1.697-2.782.603-3.369-1.34-3.369-1.34-.454-1.157-1.11-1.465-1.11-1.465-.908-.62.069-.608.069-.608 1.003.07 1.531 1.033 1.531 1.033.892 1.53 2.341 1.088 2.91.832.092-.646.35-1.09.636-1.34-2.22-.252-4.555-1.112-4.555-4.945 0-1.093.39-1.987 1.03-2.686-.103-.252-.447-1.27.098-2.647 0 0 .84-.27 2.75 1.027a9.564 9.564 0 0 1 2.5-.337 9.55 9.55 0 0 1 2.5.337c1.909-1.297 2.748-1.027 2.748-1.027.547 1.377.202 2.395.1 2.647.64.7 1.029 1.593 1.029 2.686 0 3.842-2.339 4.69-4.566 4.936.359.31.678.923.678 1.862 0 1.344-.013 2.428-.013 2.76 0 .267.18.578.688.48A10.022 10.022 0 0 0 22 12.013C22 6.485 17.523 2 12 2Z"/></svg>
                  View on Github
                </a>
              </div>
            </div>
          </section>
          <section id="demo" class="-mt-12 md:-mt-20 px-4 pb-20">${renderLandingDemo()}</section>
          <section id="features" class="py-20 bg-white border-y border-[#e5e7eb]">
            <div class="max-w-7xl mx-auto px-4 grid grid-cols-1 md:grid-cols-3 gap-12">
              ${renderFeatureCard("thumbs-up", "Community Prioritization", "Let your users vote on features. Sort requests by popularity and move the roadmap with confidence.", "bg-cyan-50", "text-[#06B6D4]")}
              ${renderFeatureCard("message-square", "Direct contact", "Enable users to contact you directly, with AI spam filtering keeping your inbox clean.", "bg-amber-50", "text-[#f59e0b]")}
              ${renderFeatureCard("bot", "Agent Friendly", "Prompt your agent with the FeatureRequest SKILL to manage your users' requests, triage, and priorities.", "bg-green-50", "text-[#16a34a]")}
            </div>
          </section>
          <section id="pricing" class="py-20 px-4">
            <div class="mx-auto max-w-3xl bg-[#111827] rounded-md-ds p-12 text-center text-white space-y-8 shadow-2xl">
              <h2 class="text-3xl font-bold">Ready to listen to your users?</h2>
              <p class="text-[#9ca3af] max-w-md mx-auto">Bring your feedback loop to one place and let your community shape your roadmap.</p>
              <div class="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
                <button type="button" data-action="landing-first-board" class="w-full sm:w-auto px-8 py-3 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all uppercase tracking-wide">Create your first board</button>
                <span class="text-[#6b7280] font-mono text-[10px] uppercase tracking-widest">It's free</span>
              </div>
            </div>
          </section>
        </main>
        <footer class="bg-white border-t border-[#e5e7eb] py-8 px-4">
          <div class="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
            <div class="flex items-center gap-2">
              <div class="w-6 h-6 bg-[#06B6D4] rounded-sm-ds flex items-center justify-center text-white">${icon("list-todo", 14)}</div>
              <span class="text-sm font-bold tracking-tight">FeatureRequest</span>
              <span class="text-[10px] font-mono text-[#9ca3af] ml-2">© 2026</span>
            </div>
            <div class="flex items-center gap-6">
              <a href="https://featurerequest.io/onurmatik/feature-request/" class="text-xs font-medium text-[#6b7280] hover:text-[#111827]">Suggest features. Report a bug. Contact the founder.</a>
            </div>
          </div>
        </footer>
        ${renderAuthModal("yourhandle", "you@indie.dev", "z-50")}
        ${renderPricingModal()}
      </div>`;
  }

  function renderLandingDemo() {
    return `
      <a href="/onurmatik/feature-request/" class="mx-auto max-w-5xl block bg-white border border-[#e5e7eb] rounded-md-ds shadow-2xl overflow-hidden relative group transition-all duration-300 hover:shadow-[0_20px_50px_rgba(6,182,212,0.15)]">
        <div class="h-10 bg-[#f9fafb] border-b border-[#e5e7eb] flex items-center px-4 gap-2">
          <div class="flex gap-1.5"><span class="h-2.5 w-2.5 rounded-full bg-[#e5e7eb]"></span><span class="h-2.5 w-2.5 rounded-full bg-[#e5e7eb]"></span><span class="h-2.5 w-2.5 rounded-full bg-[#e5e7eb]"></span></div>
          <div class="flex-1 flex justify-center"><div class="w-1/2 h-5 bg-white border border-[#e5e7eb] rounded text-[10px] font-mono text-[#9ca3af] flex items-center px-2">featurerequest.io/onurmatik/feature-request</div></div>
        </div>
        <div class="flex h-[400px] md:h-[600px]">
          <aside class="hidden sm:block w-48 border-r border-[#e5e7eb] p-3 bg-white">
            <div class="space-y-4"><div class="space-y-1"><div class="h-4 w-16 bg-[#f3f4f6] rounded mb-4"></div><div class="h-8 w-full bg-cyan-50 rounded"></div><div class="h-8 w-full bg-[#f9fafb] rounded"></div><div class="h-8 w-full bg-[#f9fafb] rounded"></div><div class="h-8 w-full bg-[#f9fafb] rounded"></div></div></div>
          </aside>
          <div class="w-full sm:w-80 border-r border-[#e5e7eb] bg-white">
            <div class="space-y-4 border-b border-[#e5e7eb] p-4"><div class="flex justify-between items-center"><div class="h-4 w-20 bg-[#f3f4f6] rounded"></div><span class="h-6 w-20 rounded bg-[#06B6D4] text-[10px] font-bold uppercase tracking-wide text-white flex items-center justify-center">New</span></div><div class="h-8 w-full bg-[#f3f4f6] rounded"></div></div>
            <div class="divide-y divide-[#e5e7eb]">
              ${SAMPLE_REQUESTS.map((request, index) => `
                <div class="space-y-2 p-4 ${index === 0 ? "border-l-4 border-[#06B6D4] bg-cyan-50/40" : "border-l-4 border-transparent"}">
                  <div class="flex items-center justify-between text-[10px] font-mono text-[#9ca3af]"><span>${request.id}</span><span>${request.upvotes} votes</span></div>
                  <p class="text-sm font-semibold text-[#111827]">${escapeHtml(request.title)}</p>
                  <div class="flex items-center gap-2 text-[10px] font-mono"><span class="rounded bg-purple-50 px-1.5 py-0.5 text-purple-700">${request.type}</span><span class="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">${request.status}</span></div>
                </div>`).join("")}
            </div>
          </div>
          <div class="hidden md:block flex-1 bg-white p-8">
            <div class="max-w-2xl space-y-6"><div class="flex justify-between border-b border-[#e5e7eb] pb-4"><div class="h-8 w-48 bg-[#f3f4f6] rounded"></div><div class="h-8 w-32 bg-[#f3f4f6] rounded"></div></div><div class="space-y-3"><div class="h-4 w-full bg-[#f3f4f6] rounded"></div><div class="h-4 w-full bg-[#f3f4f6] rounded"></div><div class="h-4 w-3/4 bg-[#f3f4f6] rounded"></div></div><div class="pt-8 space-y-4"><div class="h-4 w-40 bg-[#f3f4f6] rounded mb-6"></div><div class="flex gap-3"><div class="w-8 h-8 rounded-full bg-cyan-50 shrink-0"></div><div class="flex-1 h-16 bg-[#f9fafb] border border-[#e5e7eb] rounded"></div></div></div></div>
          </div>
        </div>
        <div class="h-14 md:h-16 bg-[#f9fafb] border-t border-[#e5e7eb] px-4 md:px-6 flex items-center justify-between">
          <div class="flex items-center gap-3 min-w-0"><div class="hidden sm:flex h-8 w-8 rounded-sm-ds bg-white border border-[#e5e7eb] items-center justify-center text-[#6b7280] shrink-0">${icon("link", 16)}</div><div class="min-w-0"><span class="block text-[10px] font-mono font-bold uppercase tracking-wider text-[#9ca3af] leading-none mb-1">Project Board</span><span class="block text-[11px] md:text-xs font-mono text-[#111827] truncate">featurerequest.io/onurmatik/feature-request</span></div></div>
          <div class="flex items-center gap-2 px-3 md:px-4 py-2 bg-[#111827] text-white text-[10px] md:text-xs font-bold uppercase tracking-wide rounded-sm-ds shadow-sm group-hover:bg-[#06B6D4] transition-colors shrink-0"><span class="hidden sm:inline">See Feature Request's own board</span><span class="sm:hidden">See board</span>${icon("arrow-right", 14)}</div>
        </div>
      </a>`;
  }

  function renderFeatureCard(iconName, title, copy, bgClass, textClass) {
    return `
      <div class="space-y-4">
        <div class="w-12 h-12 ${bgClass} rounded-sm-ds flex items-center justify-center ${textClass}">${icon(iconName, 22)}</div>
        <h3 class="font-bold text-lg">${escapeHtml(title)}</h3>
        <p class="text-sm text-[#6b7280] leading-relaxed">${escapeHtml(copy)}</p>
      </div>`;
  }

  function renderAuthModal(signUpHandlePlaceholder = "yourhandle", signUpEmailPlaceholder = "you@example.com", overlayClassName = "z-50") {
    if (!state.authMode) {
      return "";
    }
    const isSignIn = state.authMode === "signIn";
    return `
      <div class="fixed inset-0 flex items-center justify-center bg-[#111827]/60 p-4 ${overlayClassName}" data-action="modal-backdrop" data-modal="auth">
        <div class="w-full max-w-md overflow-hidden rounded-md-ds border border-[#e5e7eb] bg-white shadow-2xl">
          <div class="border-b border-[#e5e7eb] bg-[#f9fafb] p-3">
            <div class="grid grid-cols-2 gap-2 rounded-sm-ds bg-white p-1">
              <button type="button" data-action="open-auth" data-mode="signIn" class="rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide ${isSignIn ? "bg-[#111827] text-white" : "text-[#6b7280] hover:text-[#111827]"}">Sign In</button>
              <button type="button" data-action="open-auth" data-mode="signUp" class="rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide ${!isSignIn ? "bg-[#111827] text-white" : "text-[#6b7280] hover:text-[#111827]"}">Sign Up</button>
            </div>
          </div>
          <div class="flex min-h-[374px] flex-col">
            ${
              isSignIn
                ? `<form class="flex flex-1 flex-col" data-form="sign-in">
                    <div class="flex-1 space-y-4 p-6">
                      <h3 class="text-lg font-bold text-[#111827]">Welcome back</h3>
                      <p class="text-sm text-[#6b7280]">Use your email or handle to continue.</p>
                      <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">Email or Handle</label><input type="text" data-bind="signInIdentity" value="${escapeAttr(state.signInIdentity)}" class="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]" autofocus></div>
                      ${state.authFeedback ? `<p class="text-xs text-[#6b7280]">${escapeHtml(state.authFeedback)}</p>` : ""}
                    </div>
                    <div class="flex justify-end gap-3 border-t border-[#e5e7eb] bg-[#f9fafb] p-3"><button type="button" data-action="close-auth" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Cancel</button><button type="submit" class="rounded-sm-ds bg-[#06B6D4] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-cyan-600 disabled:opacity-50"${disabledAttr(state.isAuthSubmitting)}>Continue</button></div>
                  </form>`
                : `<form class="flex flex-1 flex-col" data-form="sign-up">
                    <div class="flex-1 space-y-4 p-6">
                      <h3 class="text-lg font-bold text-[#111827]">Create your account</h3>
                      <p class="text-sm text-[#6b7280]">Set a public handle, then publish your first board.</p>
                      <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">Handle</label><input type="text" data-bind="signUpHandle" value="${escapeAttr(state.signUpHandle)}" class="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]" placeholder="${escapeAttr(signUpHandlePlaceholder)}" autofocus></div>
                      <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">Email</label><input type="email" data-bind="signUpEmail" value="${escapeAttr(state.signUpEmail)}" class="w-full rounded-sm-ds border border-[#e5e7eb] px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]" placeholder="${escapeAttr(signUpEmailPlaceholder)}"></div>
                      ${state.authFeedback ? `<p class="text-xs text-[#6b7280]">${escapeHtml(state.authFeedback)}</p>` : ""}
                    </div>
                    <div class="flex justify-end gap-3 border-t border-[#e5e7eb] bg-[#f9fafb] p-3"><button type="button" data-action="close-auth" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Cancel</button><button type="submit" class="rounded-sm-ds bg-[#111827] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-black disabled:opacity-50"${disabledAttr(state.isAuthSubmitting)}>Create Account</button></div>
                  </form>`
            }
          </div>
        </div>
      </div>`;
  }

  function renderPricingModal() {
    if (!state.isPricingOpen) {
      return "";
    }
    const selectedPlan = PRICING_PLANS.find((plan) => plan.id === state.selectedPlanId) || PRICING_PLANS[0];
    return `
      <div class="fixed inset-0 z-[60] flex items-center justify-center bg-[#111827]/60 p-4" data-action="modal-backdrop" data-modal="pricing">
        <div class="w-full max-w-xl overflow-hidden rounded-md-ds border border-[#e5e7eb] bg-white shadow-2xl">
          <div class="px-6 py-5 border-b border-[#e5e7eb] bg-[#f9fafb]"><h3 class="text-lg font-bold text-[#111827]">Choose your plan</h3><p class="text-sm text-[#6b7280]">Select the billing option that matches your board needs.</p></div>
          <div class="p-6 space-y-4">
            <div class="grid gap-3 md:grid-cols-2">
              ${PRICING_PLANS.map((plan) => `<button type="button" data-action="select-plan" data-plan="${escapeAttr(plan.id)}" class="border rounded-md-ds p-4 text-left transition-all ${state.selectedPlanId === plan.id ? "bg-cyan-50 border-[#06B6D4]" : "border-[#e5e7eb] hover:border-[#06B6D4]"}"><p class="text-xs font-mono text-[#6b7280] uppercase tracking-wide">${escapeHtml(plan.title)}</p><p class="mt-1 text-lg font-bold text-[#111827]">${escapeHtml(plan.name)}</p><p class="mt-2 text-sm text-[#6b7280]">${escapeHtml(plan.description)}</p></button>`).join("")}
            </div>
            ${state.pricingFeedback ? `<p class="text-sm text-[#dc2626]">${escapeHtml(state.pricingFeedback)}</p>` : ""}
            <div class="flex items-center justify-end gap-3"><button type="button" data-action="close-pricing" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Cancel</button><button type="button" data-action="submit-pricing" class="px-5 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all disabled:opacity-50"${disabledAttr(state.isPricingSubmitting)}>${state.isPricingSubmitting ? "Please wait..." : escapeHtml(selectedPlan.cta || "Continue")}</button></div>
          </div>
        </div>
      </div>`;
  }

  function renderApplication(computed) {
    if (state.isRouteNotFound) {
      return renderNotFound();
    }
    return `
      <div class="h-screen flex flex-col bg-[#f3f4f6] text-[#111827]">
        ${renderAppHeader(computed)}
        <div class="flex-1 flex overflow-hidden">
          ${state.ownerHandle || state.view === "messages" || computed.isGlobalSettingsView ? renderSidebar(computed) : ""}
          <div class="flex-1 flex overflow-hidden">
            ${
              state.view === "issues"
                ? renderIssuesView(computed)
                : state.view === "messages"
                  ? renderMessagesView(computed)
                  : computed.isGlobalSettingsView
                    ? renderSettingsView(computed)
                    : state.view === "projectSettings"
                      ? renderProjectSettingsView(computed)
                      : renderNewProjectView(computed)
            }
          </div>
        </div>
        ${renderContactModal()}
        ${renderAuthModal("your_team", "you@company.com", "z-[120]")}
        ${renderUpgradeModal()}
        ${renderDeleteModal(computed)}
      </div>`;
  }

  function renderNotFound() {
    return `
      <div class="min-h-screen bg-[#f3f4f6] text-[#111827] flex items-center justify-center px-4">
        <div class="w-full max-w-lg rounded-md-ds border border-[#e5e7eb] bg-white p-8 shadow-sm">
          <p class="text-[10px] font-mono font-bold uppercase tracking-widest text-[#6b7280]">404</p>
          <h1 class="mt-3 text-3xl font-bold tracking-tight text-[#111827]">Page not found</h1>
          <p class="mt-3 text-sm text-[#6b7280]">The requested URL does not match a valid board or route.</p>
          <a href="/" class="mt-6 inline-flex items-center rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-black">Go Home</a>
        </div>
      </div>`;
  }

  function renderAppHeader(computed) {
    const selectedProject = computed.selectedProject;
    const messagesNavbarHandle = parseRoute().kind === "messages" ? normalizeHandle(parseRoute().selectedMessageHandle) : "";
    const projectFormUrl = state.ownerHandle ? `/${state.ownerHandle}/projects/new/` : "/projects/new/";
    const brandHref = currentUserWorkspaceUrl();
    return `
      <header class="h-[56px] bg-white border-b border-[#e5e7eb] flex items-center justify-between px-4 md:px-6 shrink-0 z-50">
        <div class="flex items-center gap-4 md:gap-6 min-w-0">
          <div class="flex items-center gap-2 shrink-0"><a href="${escapeAttr(brandHref)}" class="flex items-center gap-2"><div class="w-8 h-8 bg-[#06B6D4] rounded-sm-ds flex items-center justify-center text-white shadow-sm">${icon("list-todo", 20)}</div><span class="font-bold text-lg tracking-tight">FeatureRequest</span></a></div>
          <nav class="hidden md:flex items-center text-sm font-medium text-[#6b7280] gap-2 truncate">
            ${
              computed.isGlobalSettingsView
                ? `<a href="${settingsUrl("general")}" data-action="settings-nav" data-section="general" class="hover:text-[#111827]">settings</a><span class="text-[#d1d5db] font-mono">/</span><span class="text-[#111827] font-semibold truncate">${computed.isApiAccessView ? "api access" : computed.isConnectAgentView ? "connect agent" : "general"}</span>`
                : state.view === "messages" && messagesNavbarHandle
                  ? `<a href="/${escapeAttr(messagesNavbarHandle)}/" class="hover:text-[#111827]">${escapeHtml(messagesNavbarHandle)}</a><span class="text-[#d1d5db] font-mono">/</span><span class="text-[#111827] font-semibold truncate">Contact</span>`
                  : state.view === "messages"
                    ? `<span class="text-[#111827] font-semibold">messages</span>`
                    : `<a href="/${escapeAttr(state.ownerHandle || "")}/" class="hover:text-[#111827]">${escapeHtml(state.ownerHandle || "owner")}</a><span class="text-[#d1d5db] font-mono">/</span><span class="text-[#111827] font-semibold truncate">${escapeHtml(selectedProject ? selectedProject.name : "All Projects")}</span>${computed.isOwnerViewer ? `<a href="${projectFormUrl}" data-action="open-project-form" class="ml-2 p-1 rounded flex items-center text-[#6b7280] hover:text-[#111827] hover:bg-[#f3f4f6] transition-colors" aria-label="Create New Project" title="Create New Project">${icon("plus", 18)}</a>` : ""}`
            }
          </nav>
        </div>
        <div class="flex items-center gap-3">
          ${computed.isOwnerViewer ? `<a href="${projectFormUrl}" data-action="open-project-form" aria-label="Create New Project" class="md:hidden p-1 rounded flex items-center text-[#6b7280] hover:text-[#111827] hover:bg-[#f3f4f6] transition-colors" title="Create New Project">${icon("plus", 18)}</a>` : ""}
          ${
            state.isAuthenticated
              ? renderProfileMenu(computed)
              : `<div class="flex items-center gap-2"><button type="button" data-action="open-auth" data-mode="signIn" class="rounded-sm-ds px-3 py-2 text-xs font-bold uppercase tracking-wide text-[#6b7280] transition-colors hover:text-[#111827]">Sign In</button><button type="button" data-action="open-auth" data-mode="signUp" class="rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white transition-colors hover:bg-black">Sign Up</button></div>`
          }
        </div>
      </header>`;
  }

  function renderProfileMenu(computed) {
    const dashboardHandle = normalizeHandle(state.currentUserHandle);
    return `
      <div class="relative" data-profile-menu>
        <button type="button" data-action="toggle-profile" class="flex items-center gap-2 rounded-sm-ds border border-transparent px-2 py-1 transition-colors hover:border-[#e5e7eb] hover:bg-[#f8fafc]">
          <span class="text-xs font-mono text-[#6b7280]">${escapeHtml(state.currentUserHandle || "user")}</span>
          ${userAvatar(state.currentUserAvatarUrl, state.currentUserHandle || "user")}
          ${icon("chevron-down", 14, "text-[#6b7280]")}
        </button>
        ${
          state.isProfileMenuOpen
            ? `<div class="absolute right-0 top-full mt-2 w-44 rounded-sm-ds border border-[#e5e7eb] bg-white shadow-sm overflow-hidden z-50">
                ${dashboardHandle ? `<a href="/${escapeAttr(dashboardHandle)}/" class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]">${icon("layout-dashboard", 16)}Workspace</a>` : ""}
                ${computed.workspaceOwnerHandle ? `<button type="button" data-action="profile-new-project" class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]">${icon("plus", 16)}New Project</button>` : ""}
                <a href="/messages" class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]">${icon("message", 16)}Messages</a>
                <div class="h-px bg-[#e5e7eb] my-1"></div>
                <div class="px-3 pt-2 pb-1"><p class="text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider">Integrations</p></div>
                <a href="/settings/api" data-action="settings-nav" data-section="api" class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]">${icon("key", 16)}API Access</a>
                <a href="/settings/connect-agent" data-action="settings-nav" data-section="connect-agent" class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]">${icon("bot", 16)}Agent Integration</a>
                <div class="h-px bg-[#e5e7eb] my-1"></div>
                <button type="button" data-action="logout" class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]">${icon("logout", 16)}Logout</button>
              </div>`
            : ""
        }
      </div>`;
  }

  function renderSidebar(computed) {
    return `
      <aside class="w-72 bg-white border-r border-[#e5e7eb] flex-col shrink-0 hidden md:flex">
        <div class="flex-1 p-2 space-y-4 overflow-y-auto">
          ${computed.isGlobalSettingsView ? renderSettingsSidebar(computed) : state.view === "messages" ? renderMessageProjectButtons(computed) : renderBoardProjectsSection(computed)}
        </div>
        ${
          computed.isGlobalSettingsView
            ? `<div class="p-2 border-t border-[#e5e7eb]"><a href="${computed.workspaceOwnerHandle ? `/${computed.workspaceOwnerHandle}/` : "/"}" class="w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds text-[#6b7280] hover:bg-[#f3f4f6] font-medium text-sm transition-colors">${icon("layout-dashboard", 18)}Back to Workspace</a></div>`
            : `<div class="p-2 border-t border-[#e5e7eb]"><button type="button" data-action="${computed.isSidebarOwnerViewer ? "open-project-form" : "open-sidebar-contact"}" class="w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds text-[#6b7280] hover:bg-[#f3f4f6] font-medium text-sm transition-colors">${computed.isSidebarOwnerViewer ? icon("plus", 18) : icon("message", 18)}${computed.isSidebarOwnerViewer ? "Add new project" : computed.sidebarProjectsOwnerHandle ? `Contact @${escapeHtml(computed.sidebarProjectsOwnerHandle)}` : "Contact"}</button></div>`
        }
      </aside>`;
  }

  function renderSidebarHeader(title, computed) {
    return `
      <div class="px-3 pb-2 flex items-center justify-between relative">
        <h3 class="text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider">${escapeHtml(title)}</h3>
        ${
          computed.isSidebarOwnerViewer
            ? `<button type="button" data-action="open-project-form" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" aria-label="Add new project" title="Add new project">${icon("plus", 14)}</button>`
            : computed.sidebarProjectsOwnerHandle
              ? `<button type="button" data-action="open-sidebar-contact" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" aria-label="Contact @${escapeAttr(computed.sidebarProjectsOwnerHandle)}" title="Contact @${escapeAttr(computed.sidebarProjectsOwnerHandle)}">${icon("message", 14)}</button>`
              : ""
        }
        <span class="pointer-events-none absolute left-[-0.5rem] right-[-0.5rem] bottom-0 h-px bg-[#e5e7eb]"></span>
      </div>`;
  }

  function renderBoardProjectsSection(computed) {
    return `
      <div class="space-y-2">
        ${renderProjectAccordionSection({
          sectionKey: "owned",
          title: computed.ownedProjectsTitle,
          projects: state.projects,
          loading: false,
          emptyText: "No public projects found.",
          computed,
          canManage: true,
          showOwnerMeta: false,
        })}
        ${renderProjectAccordionSection({
          sectionKey: "interacted",
          title: computed.interactedProjectsTitle,
          projects: state.interactedProjects,
          loading: state.isInteractedProjectsLoading,
          emptyText: "No interaction with others' projects yet.",
          computed,
          canManage: false,
          showOwnerMeta: true,
        })}
      </div>`;
  }

  function renderProjectAccordionSection(options) {
    const projects = Array.isArray(options.projects) ? options.projects : [];
    const expanded = state.projectSidebarSectionsOpen[options.sectionKey] !== false;
    const countText = options.loading ? "..." : String(projects.length);
    const headerAction =
      options.sectionKey === "owned"
        ? computedSidebarHeaderAction(options.computed)
        : "";
    const isInteracted = options.sectionKey === "interacted";
    const sectionClass = isInteracted
      ? "space-y-1 mt-7 border-t border-[#e5e7eb]/60 pt-4"
      : "space-y-1";
    const bodyClass = isInteracted
      ? "max-h-[40vh] space-y-1 overflow-y-auto pr-1"
      : "space-y-1";
    const statusTextClass = isInteracted
      ? "mx-3 rounded-sm-ds border border-dashed border-[#e5e7eb] bg-[#f9fafb] px-3 py-2 text-[11px] leading-snug text-[#6b7280]"
      : "px-3 text-xs text-[#6b7280]";
    const body = (() => {
      if (!expanded) {
        return "";
      }
      if (options.loading) {
        return `<p class="${statusTextClass}">Loading projects...</p>`;
      }
      if (!projects.length) {
        return `<p class="${statusTextClass}">${escapeHtml(options.emptyText)}</p>`;
      }
      return projects
        .map((project) =>
          renderProjectSidebarRow(project, options.computed, {
            canManage: options.canManage,
            showOwnerMeta: options.showOwnerMeta,
          }),
        )
        .join("");
    })();
    return `
      <div class="${sectionClass}">
        <div class="px-3 py-1.5 mb-1 flex items-center justify-between gap-2 relative">
          <button type="button" data-action="toggle-project-section" data-section="${escapeAttr(options.sectionKey)}" class="min-w-0 flex flex-1 items-center gap-1.5 text-left text-[#9ca3af] hover:text-[#111827] transition-colors" aria-expanded="${expanded ? "true" : "false"}">
            ${icon(expanded ? "chevron-down" : "chevron-right", 12, "shrink-0")}
            <h3 class="min-w-0 truncate text-[10px] font-mono font-bold uppercase tracking-wider">${escapeHtml(options.title)}</h3>
            <span class="shrink-0 rounded-sm-ds border border-[#e5e7eb] bg-white px-1.5 py-0.5 text-[10px] font-mono font-bold leading-none text-[#9ca3af]">${escapeHtml(countText)}</span>
          </button>
          ${headerAction}
        </div>
        ${body ? `<div class="${bodyClass}">${body}</div>` : ""}
      </div>`;
  }

  function computedSidebarHeaderAction(computed) {
    if (computed.isSidebarOwnerViewer) {
      return `<button type="button" data-action="open-project-form" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" aria-label="Add new project" title="Add new project">${icon("plus", 14)}</button>`;
    }
    if (computed.sidebarProjectsOwnerHandle) {
      return `<button type="button" data-action="open-sidebar-contact" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" aria-label="Contact @${escapeAttr(computed.sidebarProjectsOwnerHandle)}" title="Contact @${escapeAttr(computed.sidebarProjectsOwnerHandle)}">${icon("message", 14)}</button>`;
    }
    return "";
  }

  function renderProjectSidebarRow(project, computed, options = {}) {
    const ownerHandle = normalizeHandle(project.owner_handle || computed.sidebarProjectsOwnerHandle);
    const slug = String(project.slug || "");
    const projectMetaText = getProjectListMetaText(project);
    const metaText = options.showOwnerMeta
      ? `@${ownerHandle}`
      : projectMetaText;
    const openIssuesCount = Number(project.open_issues_count || 0);
    const isActive = normalizeHandle(state.ownerHandle) === ownerHandle && state.selectedProjectSlug === slug;
    const canManage =
      Boolean(options.canManage) &&
      computed.isSidebarOwnerViewer &&
      ownerHandle === computed.sidebarProjectsOwnerHandle;
    const trailing = [
      openIssuesCount > 0
        ? `<span class="shrink-0 rounded-sm-ds border border-cyan-100 bg-white px-1.5 py-0.5 text-[10px] font-mono font-bold leading-none text-[#06B6D4]">${openIssuesCount}</span>`
        : "",
      canManage
        ? `<button type="button" data-action="open-project-settings" data-slug="${escapeAttr(slug)}" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" title="Project Settings" aria-label="Project settings for ${escapeAttr(project.name)}">${icon("settings", 16)}</button>`
        : "",
      project.url
        ? `<a href="${escapeAttr(project.url)}" target="_blank" rel="noreferrer" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" aria-label="Open ${escapeAttr(project.name)} website" title="Open project site">${icon("external-link", 16)}</a>`
        : "",
    ].join("");
    return `
      <div class="relative">
        <button type="button" data-action="navigate-project" data-owner="${escapeAttr(ownerHandle)}" data-slug="${escapeAttr(slug)}" class="sidebar-project-btn w-full flex items-start gap-3 px-3 py-2 rounded-sm-ds font-medium text-sm transition-colors ${isActive ? "bg-cyan-50 text-[#06B6D4]" : "text-[#6b7280] hover:bg-[#f3f4f6]"}">
          ${projectIcon(project)}
          <span class="flex-1 min-w-0 text-left"><span class="block font-medium leading-tight ${trailing ? "pr-24" : ""} truncate">${escapeHtml(project.name)}</span>${metaText ? `<span class="mt-1 block min-w-0 truncate ${trailing ? "pr-10" : ""} text-[11px] leading-tight text-[#6b7280]">${escapeHtml(metaText)}</span>` : ""}</span>
        </button>
        ${trailing ? `<span class="absolute top-2 right-2 flex items-center gap-1">${trailing}</span>` : ""}
      </div>`;
  }

  function renderMessageProjectButtons(computed) {
    return `
      <div class="space-y-1">
        ${renderSidebarHeader(computed.sidebarProjectsTitle, computed)}
        ${
          !computed.messageSidebarProjectsOwnerHandle
            ? `<p class="px-3 text-xs text-[#6b7280]">${state.isAuthenticated ? "No projects found." : "Sign in to see your projects."}</p>`
            : state.isMessageSidebarProjectsLoading
              ? `<p class="px-3 text-xs text-[#6b7280]">Loading projects...</p>`
              : state.messageSidebarProjects.length
                ? state.messageSidebarProjects
                    .map((project) => `
                      <div class="relative">
                        <a href="/${escapeAttr(computed.messageSidebarProjectsOwnerHandle)}/${escapeAttr(project.slug)}/" class="sidebar-project-btn w-full flex items-start gap-3 px-3 py-2 rounded-sm-ds font-medium text-sm transition-colors text-[#6b7280] hover:bg-[#f3f4f6]">
                          ${projectIcon(project)}
                          <span class="flex-1 min-w-0 text-left"><span class="block font-medium leading-tight pr-10 truncate">${escapeHtml(project.name)}</span>${getProjectListMetaText(project) ? `<span class="block w-full text-[11px] leading-tight text-[#6b7280] pt-2">${escapeHtml(getProjectListMetaText(project))}</span>` : ""}</span>
                        </a>
                        ${project.url ? `<span class="absolute top-2 right-2"><a href="${escapeAttr(project.url)}" target="_blank" rel="noreferrer" class="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors" aria-label="Open ${escapeAttr(project.name)} website" title="Open project site">${icon("external-link", 16)}</a></span>` : ""}
                      </div>`)
                    .join("")
                : `<p class="px-3 text-xs text-[#6b7280]">No public projects found.</p>`
        }
      </div>`;
  }

  function renderSettingsSidebar(computed) {
    return `
      <div class="space-y-1">
        <div class="px-3 pb-2 flex items-center justify-between relative"><h3 class="text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider">Settings</h3><span class="p-1 rounded-sm-ds invisible shrink-0" aria-hidden="true">${icon("plus", 14)}</span><span class="pointer-events-none absolute left-[-0.5rem] right-[-0.5rem] bottom-0 h-px bg-[#e5e7eb]"></span></div>
        <div class="space-y-1 px-1">${renderSettingsNavItems(computed, false)}</div>
      </div>`;
  }

  function renderSettingsNavItems(computed, mobile) {
    const items = [
      { key: "general", label: "General", iconName: "settings" },
      { key: "api", label: "API Access", iconName: "key" },
      { key: "connect-agent", label: "Agent Integration", iconName: "bot" },
    ];
    return items
      .map((item) => {
        const isActive = viewToSettingsSection(state.view) === item.key;
        if (mobile) {
          return `<a href="${settingsUrl(item.key)}" data-action="settings-nav" data-section="${item.key}" class="rounded-sm-ds border px-3 py-2 text-xs font-bold uppercase tracking-wide text-center transition-colors ${isActive ? "border-cyan-200 bg-cyan-50 text-[#06B6D4]" : "border-[#e5e7eb] text-[#6b7280] hover:text-[#111827]"}"><span class="inline-flex items-center justify-center mr-1.5 align-middle">${icon(item.iconName, 12)}</span>${escapeHtml(item.label)}</a>`;
        }
        return `<a href="${settingsUrl(item.key)}" data-action="settings-nav" data-section="${item.key}" class="w-full flex items-center gap-3 px-2 py-1.5 rounded-sm-ds font-medium text-sm transition-colors ${isActive ? "bg-cyan-50 text-[#06B6D4]" : "text-[#6b7280] hover:bg-[#f3f4f6]"}">${icon(item.iconName, 15)}${escapeHtml(item.label)}</a>`;
      })
      .join("");
  }

  function renderSettingsMobileNav(computed) {
    return `<div class="space-y-2 md:hidden"><p class="text-[10px] font-mono font-bold uppercase tracking-widest text-[#9ca3af]">Settings</p><div class="grid grid-cols-1 sm:grid-cols-3 gap-2">${renderSettingsNavItems(computed, true)}</div></div>`;
  }

  function emptyRequestsText() {
    if (!state.selectedProjectSlug) {
      return state.typeFilter || state.statusFilter || state.priorityFilter || state.searchQuery.trim()
        ? "No requests found for this filter."
        : "Select a project to narrow the request list.";
    }
    if (state.typeFilter || state.statusFilter || state.priorityFilter || state.searchQuery.trim()) {
      return "No requests match the active filters. Reset filters to see everything for this project.";
    }
    return "No requests yet for this project.";
  }

  function renderIssuesView(computed) {
    const mobileFocusedPane = state.isNewIssueOpen
      ? renderNewIssuePane()
      : state.isIssueDetailOpen && computed.selectedIssue
        ? renderIssueDetail(computed, { showBackButton: true })
        : "";
    const issueListDisplayClass = mobileFocusedPane ? "hidden lg:flex" : "flex";
    return `
      <div class="flex-1 flex overflow-hidden">
        ${mobileFocusedPane ? `<section class="mobile-issue-pane flex-1 bg-white flex-col overflow-hidden">${mobileFocusedPane}</section>` : ""}
        <section class="${issueListDisplayClass} issue-list-shell w-full md:w-[380px] border-r border-[#e5e7eb] bg-white flex-col shrink-0">
          <div class="p-4 border-b border-[#e5e7eb] space-y-3">
            <div class="mobile-project-picker md:hidden space-y-3">${renderBoardProjectsSection(computed)}</div>
            <div class="flex items-center justify-between gap-3"><h2 class="text-sm font-bold uppercase tracking-widest text-[#6b7280]">Requests</h2><div class="flex items-center gap-2">${computed.isOwnerViewer && computed.selectedProject ? `<button type="button" data-action="copy-project-agent-prompt" class="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1.5 text-[10px] font-bold uppercase tracking-wide text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#111827]" title="Copy project-scoped agent prompt">${icon("bot", 12)}<span class="hidden sm:inline">Agent Prompt</span></button>` : ""}<button type="button" data-action="open-new-issue" class="px-3 py-1.5 bg-[#06B6D4] text-white text-[10px] font-bold rounded-sm-ds hover:bg-cyan-600 shadow-sm transition-all uppercase tracking-wide disabled:opacity-45 disabled:cursor-not-allowed"${disabledAttr(!state.selectedProjectSlug)}>New Request</button></div></div>
            <div class="relative">${icon("search", 16, "absolute left-3 top-1/2 -translate-y-1/2 text-[#d1d5db]")}<input data-bind="searchQuery" value="${escapeAttr(state.searchQuery)}" type="text" placeholder="Filter issues..." class="w-full pl-9 pr-3 py-2 bg-[#f3f4f6] border border-[#e5e7eb] text-xs rounded-sm-ds focus:ring-1 focus:ring-[#06B6D4] outline-none"></div>
            <div class="grid grid-cols-3 gap-2">
              <select data-bind="typeFilter" class="text-[11px] font-medium bg-white border border-[#e5e7eb] rounded-sm-ds px-2 py-1 outline-none">${renderOptions(TYPE_OPTIONS, state.typeFilter)}</select>
              <select data-bind="statusFilter" class="text-[11px] font-medium bg-white border border-[#e5e7eb] rounded-sm-ds px-2 py-1 outline-none">${renderOptions(STATUS_OPTIONS, state.statusFilter)}</select>
              <select data-bind="priorityFilter" class="text-[11px] font-medium bg-white border border-[#e5e7eb] rounded-sm-ds px-2 py-1 outline-none">${renderOptions(PRIORITY_OPTIONS, state.priorityFilter)}</select>
            </div>
            <div class="flex items-center justify-between"><span class="text-xs ${state.statusError ? "text-[#dc2626]" : "text-[#6b7280]"}">${escapeHtml(state.statusLine)}</span><button type="button" data-action="reset-filters" class="text-[10px] font-mono font-bold text-[#6b7280] hover:text-[#111827] uppercase">Reset</button></div>
          </div>
          <div class="issue-list-scroll flex-1 overflow-y-auto divide-y divide-[#e5e7eb]">
            ${
              !computed.filteredIssues.length
                ? `<div class="p-4 text-sm text-[#6b7280]">${emptyRequestsText()}</div>`
                : computed.filteredIssues.map((issue) => renderIssueRow(issue, computed.selectedIssue?.id === issue.id)).join("")
            }
          </div>
        </section>
        <main class="hidden lg:flex flex-1 bg-white flex-col overflow-hidden">${state.isNewIssueOpen ? renderNewIssuePane() : computed.selectedIssue ? renderIssueDetail(computed) : `<div class="p-10 text-[#6b7280]">Select a request to view details.</div>`}</main>
      </div>`;
  }

  function renderIssueRow(issue, active) {
    return `
      <button type="button" data-action="select-issue" data-id="${issue.id}" class="issue-list-item w-full text-left p-4 cursor-pointer transition-colors group ${active ? "bg-cyan-50/50 border-l-4 border-[#06B6D4]" : "hover:bg-[#f9fafb] border-l-4 border-transparent"}">
        <div class="flex justify-between items-start mb-1"><span class="text-[10px] font-mono font-bold ${active ? "text-[#06B6D4]" : "text-[#d1d5db]"}">#${issue.id}</span><span class="text-[10px] text-[#6b7280]">${formatRelativeDate(issue.created_at)}</span></div>
        <h3 class="text-sm leading-tight mb-2 ${active ? "font-semibold text-[#111827] group-hover:text-[#06B6D4]" : "font-medium text-[#111827]"}">${escapeHtml(issue.title)}</h3>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="px-1.5 py-0.5 bg-white border text-[9px] font-mono font-bold rounded uppercase ${typeTone(issue.issue_type)}">${toReadableType(issue.issue_type)}</span>
          <span class="px-1.5 py-0.5 bg-white border text-[9px] font-mono font-bold rounded uppercase ${priorityTone(issue.priority)}">${toReadablePriority(issue.priority)}</span>
          <span class="px-1.5 py-0.5 bg-white border text-[9px] font-mono font-bold rounded uppercase ${statusTone(issue.status)}">${toReadableStatus(issue.status)}</span>
          <div class="flex-1"></div><div class="flex items-center gap-1 text-[#6b7280]">${icon("thumbs-up", 14)}<span class="text-[10px] font-mono font-bold">${Number(issue.upvotes_count || 0)}</span></div>
        </div>
      </button>`;
  }

  function renderNewIssuePane() {
    return `
      <div class="flex-1 overflow-y-auto px-4 py-5 md:px-8 space-y-4">
        <h1 class="text-2xl font-bold text-[#111827]">Create New Request</h1><p class="text-sm text-[#6b7280]">Describe your issue in detail below.</p>
        <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Title</label><input data-bind="newIssueTitle" value="${escapeAttr(state.newIssueTitle)}" type="text" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"></div>
        <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Description</label><textarea data-bind="newIssueDescription" rows="5" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-y">${escapeHtml(state.newIssueDescription)}</textarea></div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Issue Type</label><select data-bind="newIssueType" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"><option value="feature"${selectedAttr("feature", state.newIssueType)}>Feature</option><option value="bug"${selectedAttr("bug", state.newIssueType)}>Bug</option></select></div>
          <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Priority</label><select data-bind="newIssuePriority" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none">${renderOptions(PRIORITY_OPTIONS.filter((option) => option.value), state.newIssuePriority)}</select></div>
        </div>
        ${state.newIssueFeedback ? `<p class="${state.newIssueFeedback.toLowerCase().includes("rejected by moderation") ? "text-xs text-[#b91c1c]" : "text-xs text-[#6b7280]"}">${escapeHtml(state.newIssueFeedback)}</p>` : ""}
        <div class="flex justify-end gap-3"><button type="button" data-action="close-new-issue" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Cancel</button><button type="button" data-action="submit-new-issue" class="px-4 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all shadow-sm disabled:opacity-45"${disabledAttr(state.isNewIssueSubmitting)}>Create Request</button></div>
      </div>`;
  }

  function renderIssueDetail(computed, options = {}) {
    const issue = computed.selectedIssue;
    const showBackButton = Boolean(options.showBackButton);
    const canEditSelectedIssue =
      state.isAuthenticated &&
      issue &&
      (computed.isOwnerViewer || normalizeHandle(issue.author_handle) === normalizeHandle(state.currentUserHandle));
    return `
      <header class="px-4 py-3 md:px-8 border-b border-[#e5e7eb] flex flex-col md:flex-row md:items-center md:justify-between gap-3 shrink-0">
        <div class="flex flex-col gap-3">
          ${showBackButton ? `<button type="button" data-action="back-to-request-list" class="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-[#6b7280] hover:text-[#111827]">${icon("chevron-left", 14)}Requests</button>` : ""}
          <div class="flex flex-wrap items-center gap-3">
          <button type="button" data-action="upvote" class="flex items-center gap-1.5 px-3 py-1.5 border border-[#e5e7eb] rounded-sm-ds text-[#111827] font-semibold text-xs hover:bg-[#f3f4f6] transition-colors disabled:opacity-50"${disabledAttr(state.isIssueUpdating)}>${icon("thumbs-up", 18, "text-[#06B6D4]")}Upvote (${Number(issue.upvotes_count || 0)})</button>
          <div class="hidden sm:block h-4 w-[1px] bg-[#e5e7eb]"></div>
          <div class="flex items-center gap-2">${userAvatar(issue.author_avatar_url, issue.author_handle || `user-${issue.author_id}`, "w-6 h-6", "bg-cyan-50 border border-cyan-100 text-[#06B6D4]", "text-[9px] font-bold")}<span class="text-[10px] font-mono text-[#6b7280] uppercase">Created by @${escapeHtml(issue.author_handle || `user-${issue.author_id}`)} • ${formatLongDate(issue.created_at)}</span></div>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <div class="flex items-center gap-2 border border-[#e5e7eb] rounded-sm-ds px-2 py-1"><label class="text-[10px] font-mono text-[#6b7280] uppercase">Status</label><select data-patch-issue="true" data-field="status" class="text-xs font-bold text-[#16a34a] bg-transparent outline-none cursor-pointer disabled:cursor-not-allowed"${disabledAttr(!state.isAuthenticated || state.isIssueUpdating)}>${renderOptions(DETAIL_STATUS_OPTIONS, issue.status)}</select></div>
          <div class="flex items-center gap-2 border border-[#e5e7eb] rounded-sm-ds px-2 py-1"><label class="text-[10px] font-mono text-[#6b7280] uppercase">Priority</label><select data-patch-issue="true" data-field="priority" class="text-xs font-bold text-[#f59e0b] bg-transparent outline-none cursor-pointer disabled:cursor-not-allowed"${disabledAttr(!state.isAuthenticated || state.isIssueUpdating)}>${renderOptions(PRIORITY_OPTIONS.filter((option) => option.value), String(issue.priority))}</select></div>
        </div>
      </header>
      <div class="flex-1 overflow-hidden flex flex-col">
        <div class="flex-1 overflow-y-auto px-4 py-5 md:px-8 space-y-8">
          <div>${state.isIssueEditOpen ? renderIssueEditForm() : renderIssueDisplay(issue, canEditSelectedIssue)}</div>
          <div class="border-t border-[#e5e7eb] pt-8">
            <h4 class="text-xs font-bold text-[#6b7280] uppercase tracking-widest mb-6">Activity & Comments (${state.comments.length})</h4>
            <div class="space-y-6">${state.comments.length ? state.comments.map((comment) => renderComment(comment, computed)).join("") : `<p class="text-sm text-[#6b7280]">No comments yet.</p>`}</div>
          </div>
        </div>
        <div class="border-t border-[#e5e7eb] bg-[#f9fafb] p-4 space-y-3">
          <textarea data-bind="commentDraft" rows="3" class="w-full bg-white border border-[#e5e7eb] rounded-sm-ds p-3 text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none" placeholder="${state.isAuthenticated ? "Type your comment..." : "Login to post a comment."}"${disabledAttr(!state.isAuthenticated || state.isCommentSubmitting)}>${escapeHtml(state.commentDraft)}</textarea>
          <div class="flex items-center justify-between">
            ${
              state.commentFeedback
                ? `<span class="text-[10px] font-mono ${state.commentFeedback.toLowerCase().includes("rejected by moderation") ? "text-[#b91c1c]" : "text-[#d1d5db]"}">${escapeHtml(state.commentFeedback)}</span>`
                : String(issue.status || "").toLowerCase() === "closed"
                  ? `<span class="text-[10px] font-mono text-[#b45309]">This item is closed. You can still post here but I suggest creating a new request.</span>`
                  : `<span class="text-[10px] font-mono text-[#d1d5db]">Markdown supported</span>`
            }
            <button type="button" data-action="post-comment" class="px-4 py-1.5 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors disabled:opacity-45 disabled:cursor-not-allowed"${disabledAttr(!state.isAuthenticated || state.isCommentSubmitting || !state.commentDraft.trim())}>Post Comment</button>
          </div>
        </div>
      </div>`;
  }

  function renderIssueDisplay(issue, canEditSelectedIssue) {
    return `
      <div class="mb-4 flex items-start justify-between gap-4">
        <h1 class="text-2xl font-bold text-[#111827]">${escapeHtml(issue.title)}</h1>
        ${canEditSelectedIssue ? `<button type="button" data-action="edit-issue" class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm-ds border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#111827] disabled:opacity-45" title="Edit request" aria-label="Edit request"${disabledAttr(state.isIssueUpdating)}>${icon("pencil", 15)}</button>` : ""}
      </div>
      <div class="text-[#6b7280]">${markdownContent(issue.description, "No description provided.")}</div>`;
  }

  function renderIssueEditForm() {
    return `
      <div class="space-y-4">
        <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Title</label><input data-bind="issueTitleDraft" value="${escapeAttr(state.issueTitleDraft)}" type="text" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none disabled:bg-[#f9fafb]"${disabledAttr(state.isIssueUpdating)}></div>
        <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Description</label><textarea data-bind="issueDescriptionDraft" rows="7" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-y disabled:bg-[#f9fafb]"${disabledAttr(state.isIssueUpdating)}>${escapeHtml(state.issueDescriptionDraft)}</textarea></div>
        <div class="flex items-center justify-between gap-3"><span class="text-xs text-[#dc2626]">${escapeHtml(state.issueEditFeedback)}</span><div class="flex items-center gap-2"><button type="button" data-action="cancel-issue-edit" class="inline-flex h-8 w-8 items-center justify-center rounded-sm-ds border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f3f4f6] disabled:opacity-45" title="Cancel edit" aria-label="Cancel edit"${disabledAttr(state.isIssueUpdating)}>${icon("x", 15)}</button><button type="button" data-action="save-issue-edit" class="inline-flex h-8 w-8 items-center justify-center rounded-sm-ds bg-[#06B6D4] text-white hover:bg-cyan-600 disabled:opacity-45" title="Save request" aria-label="Save request"${disabledAttr(state.isIssueUpdating || !state.issueTitleDraft.trim())}>${icon("save", 15)}</button></div></div>
      </div>`;
  }

  function canEditComment(comment, computed) {
    return (
      state.isAuthenticated &&
      (computed.isOwnerViewer || normalizeHandle(comment?.author_handle) === normalizeHandle(state.currentUserHandle))
    );
  }

  function renderComment(comment, computed) {
    const editableComment = canEditComment(comment, computed);
    const isEditingComment = state.editingCommentId === comment.id;
    return `
      <div class="flex gap-4">
        ${userAvatar(comment.author_avatar_url, comment.author_handle)}
        <div class="flex-1">
          <div class="flex items-center justify-between gap-3 mb-1"><span class="text-xs font-bold">@${escapeHtml(comment.author_handle)}</span><span class="flex items-center gap-2"><span class="text-[10px] font-mono text-[#d1d5db]">${formatRelativeDate(comment.created_at)}</span>${editableComment && !isEditingComment ? `<button type="button" data-action="edit-comment" data-id="${comment.id}" class="inline-flex h-6 w-6 items-center justify-center rounded-sm-ds text-[#9ca3af] hover:bg-[#f3f4f6] hover:text-[#111827]" title="Edit comment" aria-label="Edit comment">${icon("pencil", 13)}</button>` : ""}</span></div>
          ${
            isEditingComment
              ? `<div class="space-y-2"><textarea data-bind="commentEditDraft" rows="4" class="w-full bg-white border border-[#e5e7eb] rounded-sm-ds p-3 text-sm text-[#111827] focus:ring-1 focus:ring-[#06B6D4] outline-none resize-y disabled:bg-[#f9fafb]"${disabledAttr(state.isCommentEditSubmitting)}>${escapeHtml(state.commentEditDraft)}</textarea><div class="flex items-center justify-between gap-3"><span class="text-[10px] font-mono text-[#dc2626]">${escapeHtml(state.commentEditFeedback)}</span><span class="flex items-center gap-2"><button type="button" data-action="cancel-comment-edit" class="inline-flex h-7 w-7 items-center justify-center rounded-sm-ds border border-[#e5e7eb] text-[#6b7280] hover:bg-[#f3f4f6] disabled:opacity-45" title="Cancel edit" aria-label="Cancel edit"${disabledAttr(state.isCommentEditSubmitting)}>${icon("x", 14)}</button><button type="button" data-action="save-comment-edit" data-id="${comment.id}" class="inline-flex h-7 w-7 items-center justify-center rounded-sm-ds bg-[#111827] text-white hover:bg-black disabled:opacity-45" title="Save comment" aria-label="Save comment"${disabledAttr(state.isCommentEditSubmitting || !state.commentEditDraft.trim())}>${icon("save", 14)}</button></span></div></div>`
              : `<div class="p-3 bg-[#f9fafb] border border-[#e5e7eb] rounded-sm-ds text-sm text-[#6b7280]">${markdownContent(comment.body)}</div>`
          }
        </div>
      </div>`;
  }

  function renderMessagesView(computed) {
    return `
      <div class="flex-1 flex overflow-hidden">
        <section class="w-full md:w-[360px] border-r border-[#e5e7eb] bg-white flex flex-col shrink-0">
          <div class="p-4 border-b border-[#e5e7eb] space-y-2"><div class="flex items-center justify-between"><h2 class="text-sm font-bold uppercase tracking-widest text-[#6b7280]">Messages</h2>${state.isAuthenticated ? `<button type="button" data-action="refresh-messages" class="text-[10px] font-mono font-bold text-[#6b7280] hover:text-[#111827] uppercase">Refresh</button>` : ""}</div><p class="text-xs text-[#6b7280]">${state.isMessagesLoading ? "Loading conversations..." : computed.messageThreads.length ? "Select a conversation to view messages." : "No conversations found yet."}</p></div>
          <div class="flex-1 overflow-y-auto divide-y divide-[#e5e7eb]">
            ${
              state.isMessagesLoading
                ? `<p class="p-4 text-sm text-[#6b7280]">Loading messages...</p>`
                : computed.messageThreads.length
                  ? computed.messageThreads.map((thread) => renderMessageThreadRow(thread)).join("")
                  : `<p class="p-4 text-sm text-[#6b7280]">No messages found yet.</p>`
            }
          </div>
        </section>
        <main class="flex-1 bg-white flex flex-col overflow-hidden">${renderMessageThreadDetail(computed)}</main>
      </div>`;
  }

  function renderMessageThreadRow(thread) {
    const isActive = thread.threadId === state.selectedMessageThreadId;
    return `
      <button type="button" data-action="select-message-thread" data-thread="${escapeAttr(thread.threadId)}" class="w-full text-left px-4 py-3 transition-colors ${isActive ? "bg-cyan-50 border-l-4 border-[#06B6D4]" : "hover:bg-[#f9fafb] border-l-4 border-transparent"}">
        <div class="flex items-center justify-between gap-2"><span class="text-sm font-semibold ${isActive ? "text-[#06B6D4]" : "text-[#111827]"}">${escapeHtml(getMessageThreadLabel(thread))}</span><span class="text-[10px] text-[#6b7280]">${thread.isNewConversation ? "new" : formatRelativeDate(thread.latestMessageAt)}</span></div>
        <p class="text-xs text-[#6b7280] mt-1">${escapeHtml(thread.isNewConversation ? "Start a new conversation." : trimForPreview(thread.latestMessageText))}</p>
      </button>`;
  }

  function renderMessageThreadDetail(computed) {
    const thread = computed.selectedMessageThread;
    const selectedHandle = computed.selectedMessageHandle;
    return `
      <div class="border-b border-[#e5e7eb] px-4 py-3">
        <div class="flex items-center justify-between gap-2"><h2 class="text-sm font-bold uppercase tracking-widest text-[#6b7280]">${escapeHtml(thread ? getMessageThreadLabel(thread) : getMessageThreadLabelById(state.selectedMessageThreadId))}</h2>${selectedHandle ? `<span class="text-[10px] font-mono text-[#6b7280]">${thread ? thread.messages.length : 0} message${thread?.messages.length === 1 ? "" : "s"}</span>` : `<span class="text-[10px] font-mono text-[#6b7280]">No conversation selected</span>`}</div>
        ${!state.isAuthenticated ? `<p class="mt-2 text-xs text-[#6b7280]">Sign in to open your message inbox.</p>` : ""}
      </div>
      <div class="flex-1 overflow-y-auto space-y-3 px-4 py-4">
        ${
          thread && thread.messages.length
            ? thread.messages.map((message) => renderMessageBubble(message, thread)).join("")
            : selectedHandle
              ? `<div class="text-sm text-[#6b7280]">Start a new conversation with ${escapeHtml(getMessageThreadLabelById(state.selectedMessageThreadId))}.</div>`
              : `<div class="text-sm text-[#6b7280]">Select a user from the left to open a conversation.</div>`
        }
      </div>
      <div class="border-t border-[#e5e7eb] bg-[#f9fafb] p-4 space-y-3">${renderMessageComposer(computed)}</div>`;
  }

  function renderMessageBubble(message, thread) {
    return `
      <div class="flex ${message.isOutgoing ? "justify-end" : "justify-start"}">
        <div class="max-w-[88%] rounded-sm-ds border p-3 text-sm break-words space-y-1 ${message.isOutgoing ? "bg-cyan-50 border-cyan-100 text-[#0f172a]" : "bg-[#f9fafb] border-[#e5e7eb] text-[#6b7280]"}">
          <div class="flex items-center justify-between gap-2"><span class="text-[10px] font-mono font-bold uppercase text-[#6b7280]">${message.isOutgoing ? `@${normalizeHandle(state.currentUserHandle) || "you"}` : escapeHtml(getMessageThreadLabel(thread))}</span><span class="text-[10px] text-[#9ca3af]">${formatRelativeDate(message.created_at)}</span></div>
          <div>${escapeHtml(message.body)}</div>
        </div>
      </div>`;
  }

  function renderMessageComposer(computed) {
    if (!computed.selectedMessageHandle) {
      return `<p class="text-xs text-[#6b7280]">Select a conversation to send a message.</p>`;
    }
    if (!state.isAuthenticated) {
      return `<div class="flex items-center justify-between gap-3"><p class="text-xs text-[#6b7280]">Sign in to send a direct message.</p><button type="button" data-action="open-auth" data-mode="signIn" class="px-3 py-1.5 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors">Sign In</button></div>`;
    }
    if (!computed.canSendDirectMessage) {
      return `<p class="text-xs text-[#6b7280]">Select another user to start a conversation.</p>`;
    }
    return `
      <textarea data-bind="messageComposerBody" rows="3" placeholder="Message ${escapeAttr(getMessageThreadLabelById(state.selectedMessageThreadId))}..." class="w-full bg-white border border-[#e5e7eb] rounded-sm-ds p-3 text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none"${disabledAttr(state.isMessageComposerSubmitting)}>${escapeHtml(state.messageComposerBody)}</textarea>
      <div class="flex items-center justify-between gap-3">
        ${state.messageComposerFeedback ? `<span class="text-xs ${state.messageComposerFeedbackTone === "error" ? "text-[#dc2626]" : state.messageComposerFeedbackTone === "success" ? "text-[#16a34a]" : "text-[#6b7280]"}">${escapeHtml(state.messageComposerFeedback)}</span>` : `<span class="text-xs text-[#6b7280]">Press send to deliver instantly.</span>`}
        <button type="button" data-action="send-direct-message" class="px-4 py-1.5 bg-[#06B6D4] text-white text-xs font-bold rounded-sm-ds hover:bg-cyan-600 transition-colors disabled:opacity-45"${disabledAttr(state.isMessageComposerSubmitting || !state.messageComposerBody.trim())}>${state.isMessageComposerSubmitting ? "Sending..." : "Send"}</button>
      </div>`;
  }

  function renderSettingsView(computed) {
    if (computed.isSettingsGeneralView) {
      return `
        <div class="flex-1 bg-white flex flex-col overflow-hidden">
          <div class="flex-1 overflow-y-auto">
            <div class="max-w-6xl mx-auto w-full px-6 md:px-8 py-10 space-y-8">
              ${renderSettingsMobileNav(computed)}
              <div><h2 class="text-2xl font-bold text-[#111827] mb-2">General Settings</h2><p class="text-sm text-[#6b7280]">Global workspace settings live here. API access applies to all of your projects.</p></div>
              <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <section class="rounded-md-ds border border-[#e5e7eb] bg-white p-6 space-y-4"><h3 class="text-sm font-bold uppercase tracking-widest text-[#6b7280]">API Access</h3>${state.isAuthenticated ? `<div class="space-y-1"><p class="text-sm text-[#111827]">Generate and manage tokens for programmatic access.</p><p class="text-xs text-[#6b7280]">Your API tokens inherit your account permissions and can access all of your projects.</p><a href="${settingsUrl("api")}" data-action="settings-nav" data-section="api" class="inline-flex items-center gap-2 rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-black transition-colors">${icon("key", 14)}Open API Access</a></div>` : `<div class="space-y-3"><p class="text-sm text-[#6b7280]">Sign in to manage settings and API tokens.</p><button type="button" data-action="open-auth" data-mode="signIn" class="px-4 py-2 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors">Sign In</button></div>`}</section>
                <section class="rounded-md-ds border border-[#e5e7eb] bg-white p-6 space-y-4"><h3 class="text-sm font-bold uppercase tracking-widest text-[#6b7280]">Agent Integration</h3><div class="space-y-2 text-sm text-[#6b7280]"><p>One agent token is maintained per user.</p><p>It is write-enabled and only rotates when you refresh it.</p></div><a href="${settingsUrl("connect-agent")}" data-action="settings-nav" data-section="connect-agent" class="inline-flex items-center gap-2 rounded-sm-ds bg-[#06B6D4] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-cyan-600 transition-colors">${icon("bot", 14)}Open Agent Integration</a></section>
              </div>
            </div>
          </div>
        </div>`;
    }
    return renderApiOrAgentSettings(computed);
  }

  function renderApiOrAgentSettings(computed) {
    const apiQuickstartEndpoints = [
      { method: "GET", path: "/api/projects", description: "List current user's projects" },
      { method: "POST", path: "/api/projects/<owner_handle>/<project_slug>/issues", description: "Create an issue in a project" },
      { method: "GET", path: "/api/issues/<issue_id>", description: "Get issue details" },
      { method: "GET", path: "/api/auth/agent-token", description: "Get single agent-token status" },
      { method: "POST", path: "/api/auth/agent-token/connect", description: "Create single token if missing (or rotate existing)" },
      { method: "POST", path: "/api/auth/agent-token/refresh", description: "Rotate existing agent token" },
    ];
    return `
      <div class="flex-1 bg-white flex flex-col overflow-hidden">
        <div class="p-4 border-b border-[#e5e7eb] bg-white md:hidden">${renderSettingsMobileNav(computed)}</div>
        <div class="flex-1 flex flex-col md:flex-row overflow-hidden">
          <section class="flex-1 flex flex-col min-w-0 bg-white md:border-r border-[#e5e7eb]">
            <div class="p-6 space-y-4 ${computed.isConnectAgentView ? "" : "border-b border-[#e5e7eb]"}">
              <div class="flex items-start justify-between gap-4"><h1 class="text-xl font-bold tracking-tight text-[#111827]">${computed.isConnectAgentView ? "Connect Agent" : "API Access"}</h1></div>
              ${
                computed.isConnectAgentView
                  ? `<p class="text-sm text-[#6b7280]">Connect your agent once so it can work with your feature requests automatically.</p><div class="rounded-sm-ds border border-[#fde68a] bg-[#fffbeb] p-3 text-sm text-[#92400e] flex items-start gap-2">${icon("alert-triangle", 16, "mt-0.5 shrink-0")}<span>The agents can act on your behalf without any permission restriction. In other words, they can do whatever you can do on this platform. Only use agents you trust.</span></div><div class="rounded-sm-ds border border-[#e5e7eb] bg-[#f9fafb] p-3 space-y-2"><p class="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">Agent Token</p><div class="flex flex-col md:flex-row md:items-center gap-2"><code class="flex-1 block w-full overflow-x-auto rounded-sm-ds bg-white border border-[#e5e7eb] px-2 py-1 text-[11px] text-[#111827]">${escapeHtml(computed.visibleAgentTokenValue || "Preparing token...")}</code><div class="flex items-center gap-2"><button type="button" data-action="copy-agent-token" class="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1 text-[10px] font-bold text-[#111827] hover:bg-[#f3f4f6] disabled:opacity-45" title="${computed.canCopyActiveAgentToken ? "Copy token" : "Refresh token to copy"}"${disabledAttr(!computed.canCopyActiveAgentToken)}>${icon("copy", 12)}Copy</button><button type="button" data-action="refresh-agent-token" class="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1 text-[10px] font-bold text-[#111827] hover:bg-[#f3f4f6] disabled:opacity-45"${disabledAttr(!state.isAuthenticated || state.isApiTokensLoading || state.isAgentRefreshSubmitting)}>${state.isAgentRefreshSubmitting ? "Refreshing..." : "Refresh"}</button></div></div><p class="text-[11px] text-[#6b7280]">The token does not expire. Refresh if you want to revoke the current token and issue a new one.</p></div>${renderAgentPromptPresetPicker(computed)}`
                  : `<p class="text-sm text-[#6b7280]">Manage API endpoints and authentication details for integrations.</p>`
              }
              ${state.apiTokenFeedback ? `<p class="text-xs ${state.apiTokenFeedbackTone === "error" ? "text-[#dc2626]" : state.apiTokenFeedbackTone === "success" ? "text-[#16a34a]" : "text-[#6b7280]"}">${escapeHtml(state.apiTokenFeedback)}</p>` : ""}
            </div>
            <div class="flex-1 overflow-y-auto">${computed.isConnectAgentView ? "" : renderApiTokensTable()}</div>
          </section>
          <aside class="w-full md:w-[460px] flex flex-col bg-[#f9fafb] border-t border-[#e5e7eb] md:border-t-0">
            <div class="p-6 border-b border-[#e5e7eb] bg-white"><h2 class="text-sm font-bold uppercase tracking-widest text-[#6b7280] flex items-center gap-2">${icon("key", 14)}${computed.isConnectAgentView ? "Agent Prompt" : "API Quickstart"}</h2></div>
            ${
              computed.isConnectAgentView
                ? `<div class="flex-1 overflow-y-auto p-6 space-y-4"><p class="text-sm text-[#6b7280]">Give this prompt to your agent to manage your feature requests.</p><div class="rounded-sm-ds border border-[#e5e7eb] bg-white p-3 space-y-3"><pre class="block w-full overflow-x-auto whitespace-pre-wrap rounded-sm-ds bg-[#f9fafb] border border-[#e5e7eb] px-2 py-2 text-[11px] text-[#111827]">${escapeHtml(computed.promptTextValue)}</pre><div class="flex items-center border-t border-[#e5e7eb] pt-2 ${state.agentPromptCopyFeedback ? "justify-between" : "justify-end"}">${state.agentPromptCopyFeedback ? `<p class="text-[11px] ${state.agentPromptCopyFeedbackTone === "error" ? "text-[#dc2626]" : "text-[#16a34a]"}">${escapeHtml(state.agentPromptCopyFeedback)}</p>` : ""}<button type="button" data-action="copy-agent-prompt" class="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1 text-[10px] font-bold text-[#111827] hover:bg-[#f3f4f6]">${icon("copy", 12)}Copy Prompt</button></div></div></div>`
                : `<div class="flex-1 overflow-y-auto p-6 space-y-6"><div class="space-y-3"><h3 class="text-xs font-bold uppercase font-mono text-[#6b7280] tracking-wider">Endpoint URL</h3><div class="bg-[#111827] text-white p-3 rounded-sm-ds font-mono text-xs break-all">${escapeHtml(computed.apiBaseUrl)}</div><button type="button" data-action="copy-base-url" class="text-[10px] font-mono font-bold uppercase text-[#6b7280] hover:text-[#111827]">Copy base URL</button></div><div class="space-y-4"><h3 class="text-xs font-bold uppercase font-mono text-[#6b7280] tracking-wider">Authentication</h3><p class="text-xs text-[#6b7280] leading-relaxed">Include your API token in the <code class="bg-[#e5e7eb] px-1 rounded text-[#111827]">Authorization</code> header as a Bearer token.</p><div class="bg-[#111827] text-gray-300 p-3 rounded-sm-ds font-mono text-[11px] overflow-x-auto">curl -H "Authorization: Bearer YOUR_TOKEN" \\<br>${escapeHtml(computed.apiBaseUrl)}/api/projects</div></div><div class="space-y-4"><h3 class="text-xs font-bold uppercase font-mono text-[#6b7280] tracking-wider">Common Endpoints</h3><div class="space-y-2">${apiQuickstartEndpoints.slice(0, 3).map((item) => `<div class="flex items-center justify-between text-[11px] font-mono border-b border-[#e5e7eb] pb-2"><span class="font-bold ${methodTone(item.method)}">${item.method}</span><span class="text-[#111827]">${escapeHtml(item.path.replace("<token_id>", ":token_id"))}</span></div>`).join("")}</div></div><div class="bg-white border border-[#e5e7eb] p-4 rounded-md-ds space-y-2"><p class="text-[11px] text-[#6b7280]">Need the full API spec?</p><a href="/api/docs" target="_blank" rel="noreferrer" class="text-xs font-bold text-[#06B6D4] hover:underline flex items-center gap-1">View Full Docs${icon("external-link", 12)}</a></div></div>`
            }
          </aside>
        </div>
      </div>`;
  }

  function renderAgentPromptPresetPicker(computed) {
    const projectPreset = isProjectAgentPromptPreset(state.agentPromptPreset);
    return `
      <div class="space-y-3">
        <p class="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">Prompt Preset</p>
        <div class="grid gap-2">
          ${AGENT_PROMPT_PRESETS.map((preset) => {
            const isActive = computed.agentPromptPreset === preset.value;
            return `<button type="button" data-action="select-agent-prompt-preset" data-preset="${escapeAttr(preset.value)}" class="w-full rounded-sm-ds border px-3 py-2 text-left transition-colors ${isActive ? "border-cyan-200 bg-cyan-50 text-[#111827]" : "border-[#e5e7eb] bg-white text-[#6b7280] hover:bg-[#f3f4f6] hover:text-[#111827]"}"><span class="block text-xs font-bold">${escapeHtml(preset.label)}</span><span class="mt-1 block text-[11px] leading-tight text-[#6b7280]">${escapeHtml(preset.description)}</span></button>`;
          }).join("")}
        </div>
        ${projectPreset ? renderAgentPromptProjectSelect(computed) : ""}
      </div>`;
  }

  function renderAgentPromptProjectSelect(computed) {
    if (state.isAgentPromptProjectsLoading) {
      return `<p class="text-xs text-[#6b7280]">Loading projects...</p>`;
    }
    if (!computed.agentPromptProjects.length) {
      return `<p class="text-xs text-[#6b7280]">No owned projects found for project-scoped prompts.</p>`;
    }
    return `
      <div class="space-y-1.5">
        <label class="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">Project Scope</label>
        <select data-bind="agentPromptProjectSlug" class="w-full rounded-sm-ds border border-[#e5e7eb] bg-white px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-[#06B6D4]">
          ${computed.agentPromptProjects.map((project) => `<option value="${escapeAttr(project.slug)}"${selectedAttr(project.slug, computed.selectedAgentPromptProject?.slug || "")}>${escapeHtml(project.owner_handle)}/${escapeHtml(project.slug)} - ${escapeHtml(project.name)}</option>`).join("")}
        </select>
      </div>`;
  }

  function renderApiTokensTable() {
    if (!state.isAuthenticated) {
      return `<div class="p-6"><div class="rounded-sm-ds border border-[#e5e7eb] bg-[#f9fafb] p-4 space-y-3"><p class="text-sm text-[#6b7280]">Sign in to manage your API tokens.</p><button type="button" data-action="open-auth" data-mode="signIn" class="px-4 py-2 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors">Sign In</button></div></div>`;
    }
    if (state.isApiTokensLoading) {
      return `<p class="p-6 text-sm text-[#6b7280]">Loading tokens...</p>`;
    }
    return `
      <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-[#e5e7eb]">
          <thead class="bg-[#f9fafb] border-b border-[#e5e7eb]"><tr><th class="px-6 py-3 text-left text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">Name</th><th class="px-6 py-3 text-left text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">Key</th><th class="px-6 py-3 text-center text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">Write</th><th class="px-6 py-3 text-left text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">Created</th></tr></thead>
          <tbody class="bg-white divide-y divide-[#e5e7eb]">${
            !state.apiTokens.length
              ? `<tr><td colspan="4" class="px-6 py-6 text-sm text-[#6b7280]">No API tokens yet.</td></tr>`
              : state.apiTokens.map((token) => `<tr class="group hover:bg-[#f9fafb] transition-colors"><td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-[#111827]"><div><p>${escapeHtml(token.name)}</p></div></td><td class="px-6 py-4 whitespace-nowrap text-sm"><div class="flex items-center gap-2"><code class="bg-[#f3f4f6] px-2 py-0.5 rounded-sm-ds font-mono text-xs text-[#6b7280]">${escapeHtml(token.token_prefix)}••••••••</code><button type="button" data-action="copy-api-token" data-id="${token.id}" title="${state.apiTokenSecrets[token.id] ? "Copy Token" : "Token value unavailable"}" class="text-[#9ca3af] hover:text-[#06B6D4] transition-all ${state.apiTokenSecrets[token.id] ? "opacity-0 group-hover:opacity-100" : "opacity-35 cursor-not-allowed"}"${disabledAttr(!state.apiTokenSecrets[token.id])}>${icon("copy", 14)}</button></div></td><td class="px-6 py-4 whitespace-nowrap text-center text-sm"><span class="inline-flex items-center justify-center text-xs font-mono font-bold rounded-sm-ds w-6 h-6 ${token.can_write ? "text-[#16a34a] bg-[#f0fdf4]" : "text-[#dc2626] bg-[#fef2f2]"}" aria-label="${token.can_write ? "Writable token" : "Read-only token"}">${token.can_write ? "✓" : "✕"}</span></td><td class="px-6 py-4 whitespace-nowrap text-xs text-[#6b7280] font-mono">${formatLongDate(token.created_at)}</td></tr>`).join("")
          }</tbody>
        </table>
      </div>`;
  }

  function renderProjectSettingsView(computed) {
    const project = computed.selectedProject;
    return `
      <div class="flex-1 bg-white flex flex-col overflow-y-auto">
        <div class="max-w-3xl mx-auto w-full px-6 md:px-8 py-10 space-y-12">
          <div><h2 class="text-2xl font-bold text-[#111827] mb-2">Project Settings</h2><p class="text-sm text-[#6b7280]">Manage your project metadata and administrative controls.</p></div>
          <section class="space-y-6">
            <div class="pb-4 border-b border-[#e5e7eb]"><h3 class="text-sm font-bold uppercase tracking-widest text-[#6b7280]">General Information</h3></div>
            ${!computed.isOwnerViewer ? `<p class="text-xs text-[#6b7280]">You are viewing this board as a visitor. Only @${escapeHtml(state.ownerHandle)} can edit project settings.</p>` : ""}
            ${project ? renderProjectFields(computed, false) : `<p class="text-sm text-[#6b7280]">Select a project from sidebar and open settings.</p>`}
            ${state.projectFeedback ? `<p class="text-xs ${state.projectFeedbackTone === "error" ? "text-[#dc2626]" : state.projectFeedbackTone === "success" ? "text-[#16a34a]" : "text-[#6b7280]"}">${escapeHtml(state.projectFeedback)}</p>` : ""}
            <div class="flex justify-end"><button type="button" data-action="save-project" class="px-6 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 shadow-sm transition-all disabled:opacity-45"${disabledAttr(!project || !computed.isOwnerViewer || state.isProjectSaving)}>${state.isProjectSaving ? "Saving..." : "Save Changes"}</button></div>
          </section>
          <section class="space-y-6">
            <div class="pb-4 border-b border-[#e5e7eb]"><h3 class="text-sm font-bold uppercase tracking-widest text-[#dc2626]">Danger Zone</h3></div>
            <div class="p-4 border border-rose-100 bg-rose-50 rounded-md-ds flex flex-col md:flex-row gap-4 md:items-center md:justify-between"><div class="space-y-1"><p class="text-sm font-bold text-[#111827]">Delete this project</p><p class="text-xs text-[#6b7280]">Once deleted, all data including issues and comments will be permanently removed.</p></div><button type="button" data-action="open-delete-modal" class="px-4 py-2 bg-[#dc2626] text-white text-xs font-bold rounded-sm-ds hover:bg-red-700 transition-all shadow-sm"${disabledAttr(!project || !computed.isOwnerViewer || state.isProjectDeleting)}>Delete Project</button></div>
          </section>
        </div>
      </div>`;
  }

  function renderProjectFields(computed, isNewProject) {
    const disabled = !computed.isOwnerViewer || (isNewProject ? state.isNewProjectSubmitting : state.isProjectSaving);
    return `
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Project Name</label><input type="text" data-bind="projectNameDraft" value="${escapeAttr(state.projectNameDraft)}" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm ${computed.isOwnerViewer ? "bg-white" : "bg-[#f9fafb]"}"${disabledAttr(disabled)}></div>
        <div class="space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Project URL</label><input type="url" data-bind="projectUrlDraft" value="${escapeAttr(state.projectUrlDraft)}" placeholder="https://example.com" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm ${computed.isOwnerViewer ? "bg-white" : "bg-[#f9fafb]"}"${disabledAttr(disabled)}></div>
        <div class="md:col-span-2 space-y-1.5"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Tagline</label><input type="text" data-bind="projectTaglineDraft" value="${escapeAttr(state.projectTaglineDraft)}" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm ${computed.isOwnerViewer ? "bg-white" : "bg-[#f9fafb]"}"${disabledAttr(disabled)}></div>
      </div>`;
  }

  function renderNewProjectView(computed) {
    return `
      <div class="flex-1 bg-white flex flex-col overflow-y-auto">
        <div class="max-w-3xl mx-auto w-full px-6 md:px-8 py-10 space-y-12">
          <div><h2 class="text-2xl font-bold text-[#111827] mb-2">New Project</h2><p class="text-sm text-[#6b7280]">Create a new project under your workspace.</p></div>
          ${!computed.isOwnerViewer ? `<p class="text-sm text-[#6b7280]">Only the board owner can create a project.</p>` : ""}
          <section class="space-y-6">
            ${renderProjectFields(computed, true)}
            ${state.newProjectFeedback ? `<p class="text-xs ${state.newProjectFeedbackTone === "error" ? "text-[#dc2626]" : state.newProjectFeedbackTone === "success" ? "text-[#16a34a]" : "text-[#6b7280]"}">${escapeHtml(state.newProjectFeedback)}</p>` : ""}
            <div class="flex justify-end gap-3"><button type="button" data-action="close-new-project" class="px-6 py-2 border border-[#e5e7eb] text-[#6b7280] text-sm font-bold rounded-sm-ds hover:bg-[#f3f4f6] transition-all">Cancel</button><button type="button" data-action="submit-new-project" class="px-6 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 shadow-sm transition-all disabled:opacity-45"${disabledAttr(!computed.isOwnerViewer || state.isNewProjectSubmitting)}>${state.isNewProjectSubmitting ? "Creating..." : "Create Project"}</button></div>
          </section>
        </div>
      </div>`;
  }

  function renderContactModal() {
    if (!state.isContactOpen) {
      return "";
    }
    return `
      <div class="fixed inset-0 bg-[#111827]/60 backdrop-blur-[2px] z-[100] flex items-center justify-center p-4" data-action="modal-backdrop" data-modal="contact">
        <div class="bg-white rounded-md-ds shadow-2xl max-w-md w-full overflow-hidden">
          <div class="p-6">
            <h3 class="text-lg font-bold text-[#111827] mb-2">Message @${escapeHtml(state.ownerHandle || "owner")}</h3>
            <p class="text-sm text-[#6b7280] mb-6">Have a question or feedback? Send a direct message to the project maintainer.</p>
            ${
              !state.isAuthenticated
                ? `<div class="space-y-3 mb-4"><div><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Name</label><input data-bind="contactSenderName" value="${escapeAttr(state.contactSenderName)}" type="text" class="mt-1 w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"></div><div><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Email</label><input data-bind="contactSenderEmail" value="${escapeAttr(state.contactSenderEmail)}" type="email" class="mt-1 w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"></div></div>`
                : ""
            }
            <div class="space-y-3"><label class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Your Message</label><textarea data-bind="contactBody" rows="4" placeholder="How can we help?" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none">${escapeHtml(state.contactBody)}</textarea>${state.contactFeedback ? `<p class="text-xs ${state.contactFeedbackTone === "error" ? "text-[#dc2626]" : state.contactFeedbackTone === "success" ? "text-[#16a34a]" : "text-[#6b7280]"}">${escapeHtml(state.contactFeedback)}</p>` : ""}</div>
          </div>
          <div class="bg-[#f9fafb] px-6 py-4 flex justify-end gap-3"><button type="button" data-action="close-contact" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Cancel</button><button type="button" data-action="submit-contact" class="px-4 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all shadow-sm disabled:opacity-45"${disabledAttr(state.isContactSubmitting)}>Send Message</button></div>
        </div>
      </div>`;
  }

  function renderUpgradeModal() {
    if (!state.isUpgradePlanOpen) {
      return "";
    }
    return `
      <div class="fixed inset-0 z-[110] flex items-center justify-center bg-[#111827]/60 p-4" data-action="modal-backdrop" data-modal="upgrade">
        <div class="w-full max-w-md overflow-hidden rounded-md-ds border border-[#e5e7eb] bg-white shadow-2xl">
          <div class="px-6 py-5 border-b border-[#e5e7eb] bg-[#f9fafb]"><h3 class="text-lg font-bold text-[#111827]">Project limit reached</h3><p class="text-sm text-[#6b7280]">You have reached your plan's project limit. Upgrade to add another project.</p></div>
          <div class="p-6"><div class="border rounded-sm-ds border-[#e5e7eb] p-4"><p class="text-xs font-mono text-[#6b7280] uppercase tracking-wide">${PROJECT_UPGRADE_PLAN.title}</p><p class="mt-1 text-lg font-bold text-[#111827]">${PROJECT_UPGRADE_PLAN.name}</p><p class="mt-2 text-sm text-[#6b7280]">${PROJECT_UPGRADE_PLAN.description}</p></div>${state.upgradePlanFeedback ? `<p class="mt-3 text-xs text-[#dc2626]">${escapeHtml(state.upgradePlanFeedback)}</p>` : ""}</div>
          <div class="bg-[#f9fafb] px-6 py-4 flex justify-end gap-3"><button type="button" data-action="close-upgrade" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Maybe later</button><button type="button" data-action="upgrade-plan" class="px-4 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all shadow-sm disabled:opacity-45"${disabledAttr(state.isUpgradePlanSubmitting)}>${state.isUpgradePlanSubmitting ? "Please wait..." : PROJECT_UPGRADE_PLAN.cta}</button></div>
        </div>
      </div>`;
  }

  function renderDeleteModal(computed) {
    const project = computed.selectedProject;
    if (!state.isDeleteModalOpen || !project) {
      return "";
    }
    return `
      <div class="fixed inset-0 bg-[#111827]/60 backdrop-blur-[2px] z-[100] flex items-center justify-center p-4" data-action="modal-backdrop" data-modal="delete">
        <div class="bg-white rounded-md-ds shadow-2xl max-w-md w-full overflow-hidden">
          <div class="p-6"><div class="w-12 h-12 bg-rose-100 rounded-full flex items-center justify-center text-[#dc2626] mb-4">${icon("alert-triangle", 24)}</div><h3 class="text-lg font-bold text-[#111827] mb-2">Are you absolutely sure?</h3><p class="text-sm text-[#6b7280] mb-6">This action cannot be undone. This will permanently delete the <span class="font-mono font-bold text-[#111827]"> ${escapeHtml(project.slug || "project")}</span> project and all associated data.</p><div class="space-y-3"><p class="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Type project slug to confirm</p><input type="text" data-bind="deleteSlugConfirm" value="${escapeAttr(state.deleteSlugConfirm)}" placeholder="${escapeAttr(project.slug || "project-slug")}" class="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-red-500 outline-none"></div></div>
          <div class="bg-[#f9fafb] px-6 py-4 flex justify-end gap-3"><button type="button" data-action="close-delete-modal" class="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]">Cancel</button><button type="button" data-action="confirm-delete-project" class="px-4 py-2 bg-[#dc2626] text-white text-sm font-bold rounded-sm-ds hover:bg-red-700 transition-all disabled:opacity-45"${disabledAttr(!project || !computed.isOwnerViewer || state.isProjectDeleting || state.deleteSlugConfirm.trim() !== project.slug)}>${state.isProjectDeleting ? "Deleting..." : "Confirm Delete"}</button></div>
        </div>
      </div>`;
  }

  async function refreshSession() {
    const response = await fetch("/auth/me");
    if (!response.ok) {
      state.isAuthenticated = false;
      state.currentUserHandle = "";
      state.currentUserAvatarUrl = "";
      state.subscriptionTier = "free";
      state.subscriptionStatus = "";
      state.projectLimit = 1;
      return;
    }
    const data = await response.json();
    state.isAuthenticated = Boolean(data.is_authenticated);
    state.currentUserHandle = String(data.current_user_handle || "");
    state.currentUserAvatarUrl = String(data.current_user_avatar_url || "");
    state.subscriptionTier = String(data.subscription_tier || "free").toLowerCase();
    state.subscriptionStatus = String(data.subscription_status || "").toLowerCase();
    state.projectLimit = Number(data.project_limit || 1);
  }

  async function refreshProjects() {
    if (!state.ownerHandle) {
      state.projects = [];
      return;
    }
    const response = await fetch(`/api/owners/${encodeURIComponent(state.ownerHandle)}/projects`);
    if (response.status === 404) {
      state.isRouteNotFound = true;
      render();
      return;
    }
    if (!response.ok) {
      setStatus("Projects could not be loaded.", true);
      render();
      return;
    }
    const data = await response.json();
    const route = parseRoute();
    if (
      route.kind === "board" &&
      route.ownerHandle === state.ownerHandle &&
      route.projectSlug &&
      !route.isProjectFormRoute &&
      !data.some((project) => project.slug === route.projectSlug)
    ) {
      state.isRouteNotFound = true;
      render();
      return;
    }
    state.projects = Array.isArray(data) ? data : [];
    if (state.selectedProjectSlug && !state.projects.some((project) => project.slug === state.selectedProjectSlug)) {
      state.selectedProjectSlug = "";
    }
    render();
  }

  async function refreshInteractedProjects() {
    if (!state.ownerHandle) {
      state.interactedProjects = [];
      state.isInteractedProjectsLoading = false;
      return;
    }
    state.isInteractedProjectsLoading = true;
    render();
    try {
      const response = await fetch(`/api/owners/${encodeURIComponent(state.ownerHandle)}/interacted-projects`);
      if (response.status === 404) {
        state.interactedProjects = [];
        state.isRouteNotFound = true;
        render();
        return;
      }
      const data = response.ok ? await response.json() : [];
      state.interactedProjects = Array.isArray(data) ? data : [];
    } catch {
      state.interactedProjects = [];
    } finally {
      state.isInteractedProjectsLoading = false;
      render();
    }
  }

  async function refreshIssues() {
    if (!state.ownerHandle) {
      state.issues = [];
      return;
    }
    const params = new URLSearchParams();
    if (state.selectedProjectSlug) {
      params.set("project_slug", state.selectedProjectSlug);
    }
    if (state.typeFilter) {
      params.set("issue_type", state.typeFilter);
    }
    if (state.statusFilter) {
      params.set("status", state.statusFilter);
    }
    if (state.priorityFilter) {
      params.set("priority", state.priorityFilter);
    }
    setStatus("Requests loading...");
    render();
    const url = `/api/owners/${encodeURIComponent(state.ownerHandle)}/issues${params.toString() ? `?${params.toString()}` : ""}`;
    const response = await fetch(url);
    if (response.status === 404) {
      state.issues = [];
      state.isRouteNotFound = true;
      render();
      return;
    }
    if (!response.ok) {
      state.issues = [];
      setStatus("Requests could not be loaded.", true);
      render();
      return;
    }
    const data = await response.json();
    state.issues = Array.isArray(data) ? data : [];
    const computed = getComputed();
    state.selectedIssueId = computed.selectedIssue?.id || null;
    if (!computed.selectedIssue) {
      state.isIssueDetailOpen = false;
    }
    setStatus(`${state.issues.length} requests listed.`);
    render();
  }

  async function refreshComments(issueId) {
    if (!issueId) {
      state.comments = [];
      render();
      return;
    }
    const response = await fetch(`/api/issues/${issueId}/comments`);
    if (!response.ok) {
      state.comments = [];
      render();
      return;
    }
    state.comments = await response.json();
    render();
  }

  async function refreshMessages() {
    if (!state.isAuthenticated) {
      state.messages = [];
      render();
      return;
    }
    state.isMessagesLoading = true;
    render();
    try {
      const response = await fetch("/api/me/messages");
      if (!response.ok) {
        state.messages = [];
        setStatus("Messages could not be loaded.", true);
        return;
      }
      state.messages = await response.json();
      const computed = getComputed();
      if (!state.selectedMessageThreadId && computed.messageThreads.length) {
        state.selectedMessageThreadId = computed.messageThreads[0].threadId;
      }
    } finally {
      state.isMessagesLoading = false;
      render();
    }
  }

  async function refreshMessageSidebarProjects() {
    const computed = getComputed();
    if (!computed.messageSidebarProjectsOwnerHandle) {
      state.messageSidebarProjects = [];
      state.isMessageSidebarProjectsLoading = false;
      render();
      return;
    }
    state.isMessageSidebarProjectsLoading = true;
    render();
    try {
      const response = await fetch(`/api/owners/${encodeURIComponent(computed.messageSidebarProjectsOwnerHandle)}/projects`);
      state.messageSidebarProjects = response.ok ? await response.json() : [];
    } catch {
      state.messageSidebarProjects = [];
    } finally {
      state.isMessageSidebarProjectsLoading = false;
      render();
    }
  }

  async function refreshAgentPromptProjects() {
    if (!state.isAuthenticated) {
      state.agentPromptProjects = [];
      state.agentPromptProjectSlug = "";
      state.isAgentPromptProjectsLoading = false;
      render();
      return;
    }
    state.isAgentPromptProjectsLoading = true;
    render();
    try {
      const response = await fetch("/api/projects");
      const data = response.ok ? await response.json() : [];
      state.agentPromptProjects = Array.isArray(data) ? data : [];
      if (
        state.agentPromptProjects.length &&
        (!state.agentPromptProjectSlug || !state.agentPromptProjects.some((project) => project.slug === state.agentPromptProjectSlug))
      ) {
        state.agentPromptProjectSlug = state.agentPromptProjects[0].slug;
      }
      if (!state.agentPromptProjects.length) {
        state.agentPromptProjectSlug = "";
      }
    } catch {
      state.agentPromptProjects = [];
      state.agentPromptProjectSlug = "";
    } finally {
      state.isAgentPromptProjectsLoading = false;
      render();
    }
  }

  async function refreshApiTokens() {
    if (!state.isAuthenticated) {
      state.apiTokens = [];
      state.latestCreatedTokenValue = "";
      state.agentPromptValue = "";
      render();
      return;
    }
    const computed = getComputed();
    state.isApiTokensLoading = true;
    render();
    try {
      const response = await fetch("/api/auth/agent-token");
      if (!response.ok) {
        state.apiTokens = [];
        state.apiTokenFeedback = "API tokens could not be loaded.";
        state.apiTokenFeedbackTone = "error";
        return;
      }
      const data = await response.json();
      if (data && data.exists) {
        const tokenRow = {
          id: data.id,
          name: data.name,
          can_write: Boolean(data.can_write),
          token_prefix: data.token_prefix,
          created_at: data.created_at,
          last_used_at: data.last_used_at,
        };
        state.apiTokens = [tokenRow];
        const storedTokenValue = readStoredAgentToken(state.currentUserHandle);
        if (storedTokenValue && storedTokenValue.slice(0, 12) === String(data.token_prefix || "")) {
          state.apiTokenSecrets = { ...state.apiTokenSecrets, [data.id]: storedTokenValue };
          state.latestCreatedTokenValue = storedTokenValue;
          state.agentPromptValue = buildAgentPromptText(computed.apiBaseUrl, storedTokenValue);
        } else {
          await connectAgentToken();
        }
      } else {
        await connectAgentToken();
      }
      state.apiTokenFeedback = "";
      state.apiTokenFeedbackTone = "";
    } finally {
      state.isApiTokensLoading = false;
      render();
    }
  }

  async function connectAgentToken() {
    const computed = getComputed();
    await ensureCsrfCookie();
    const response = await fetch("/api/auth/agent-token/connect", {
      method: "POST",
      headers: { "X-CSRFToken": csrfTokenFromCookie() },
    });
    const payload = await jsonOrEmpty(response);
    if (!response.ok) {
      state.apiTokenFeedback = detailFromPayload(payload, "Agent token could not be loaded.");
      state.apiTokenFeedbackTone = "error";
      state.latestCreatedTokenValue = "";
      state.agentPromptValue = "";
      return "";
    }
    const tokenRow = {
      id: payload.id,
      name: payload.name,
      can_write: Boolean(payload.can_write),
      token_prefix: payload.token_prefix,
      created_at: payload.created_at,
      last_used_at: payload.last_used_at,
    };
    const tokenValue = String(payload.token || "");
    state.apiTokens = [tokenRow];
    state.latestCreatedTokenValue = tokenValue;
    if (tokenValue) {
      writeStoredAgentToken(state.currentUserHandle, tokenValue);
      state.apiTokenSecrets = { ...state.apiTokenSecrets, [tokenRow.id]: tokenValue };
      state.agentPromptValue = buildAgentPromptText(computed.apiBaseUrl, tokenValue);
    }
    return tokenValue;
  }

  async function ensureAgentPromptToken() {
    const computed = getComputed();
    const existingToken = computed.activeAgentTokenSecret || state.latestCreatedTokenValue;
    if (existingToken) {
      return existingToken;
    }
    if (!state.isAuthenticated) {
      return "";
    }
    const tokenValue = await connectAgentToken();
    return tokenValue || getComputed().activeAgentTokenSecret || state.latestCreatedTokenValue || "";
  }

  async function handleCopyAgentPromptFromSettings() {
    const tokenValue = await ensureAgentPromptToken();
    const computed = getComputed();
    if (!tokenValue) {
      state.agentPromptCopyFeedback = "Sign in and create an agent token first.";
      state.agentPromptCopyFeedbackTone = "error";
      render();
      return;
    }
    if (isProjectAgentPromptPreset(state.agentPromptPreset) && !computed.selectedAgentPromptProject) {
      state.agentPromptCopyFeedback = "Select a project for this prompt.";
      state.agentPromptCopyFeedbackTone = "error";
      render();
      return;
    }
    const promptText = buildAgentPromptText(computed.apiBaseUrl, tokenValue, {
      preset: state.agentPromptPreset,
      ownerHandle: state.currentUserHandle,
      project: isProjectAgentPromptPreset(state.agentPromptPreset) ? computed.selectedAgentPromptProject : null,
    });
    const copied = await copyToClipboard(promptText);
    state.agentPromptCopyFeedback = copied ? "Agent prompt copied." : "Copy failed. Please copy manually.";
    state.agentPromptCopyFeedbackTone = copied ? "success" : "error";
    render();
  }

  async function handleCopyProjectAgentPrompt(project) {
    if (!state.isAuthenticated) {
      openAuth("signIn");
      return;
    }
    if (!project) {
      setStatus("Select a project first.", true);
      render();
      return;
    }
    const tokenValue = await ensureAgentPromptToken();
    if (!tokenValue) {
      setStatus("Agent token could not be loaded.", true);
      render();
      return;
    }
    const promptText = buildAgentPromptText(window.location.origin, tokenValue, {
      preset: "project-triage",
      ownerHandle: state.ownerHandle,
      project,
    });
    const copied = await copyToClipboard(promptText);
    setStatus(copied ? "Project agent prompt copied." : "Copy failed. Please copy manually.", !copied);
    render();
  }

  function openAuth(mode) {
    state.authMode = mode;
    state.authFeedback = "";
    render();
  }

  function closeAuth() {
    state.authMode = null;
    state.authFeedback = "";
    state.isAuthSubmitting = false;
    render();
  }

  async function onSignInSubmit() {
    const identity = state.signInIdentity.trim();
    if (!identity) {
      state.authFeedback = "Email or handle is required.";
      render();
      return;
    }
    state.isAuthSubmitting = true;
    state.authFeedback = "Signing in...";
    render();
    try {
      await ensureCsrfCookie();
      const route = parseRoute();
      const useCurrentPathAsNext = route.kind === "messages";
      const response = await fetch(authSignInEndpoint({ useCurrentPathAsNext }), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ email_or_handle: identity }),
      });
      const payload = await jsonOrEmpty(response);
      if (!response.ok) {
        state.authFeedback = detailFromPayload(payload, "Sign in failed.");
        return;
      }
      const handle = String(payload.current_user_handle || "").trim();
      if (!handle) {
        state.authFeedback = detailFromPayload(payload, "Sign in link sent. Check your email.");
        return;
      }
      window.location.assign(getPostAuthRedirect(handle, { useCurrentPathAsFallback: useCurrentPathAsNext }));
    } catch {
      state.authFeedback = "Sign in failed. Please try again.";
    } finally {
      state.isAuthSubmitting = false;
      render();
    }
  }

  async function onSignUpSubmit() {
    const email = state.signUpEmail.trim().toLowerCase();
    const handle = state.signUpHandle.trim().toLowerCase();
    if (!email || !handle) {
      state.authFeedback = "Email and handle are required.";
      render();
      return;
    }
    state.isAuthSubmitting = true;
    state.authFeedback = "Sending sign-up link...";
    render();
    try {
      await ensureCsrfCookie();
      const response = await fetch("/auth/sign-up", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ email, handle, display_name: handle }),
      });
      const payload = await jsonOrEmpty(response);
      state.authFeedback = response.ok ? detailFromPayload(payload, "Sign-up link sent. Check your email.") : detailFromPayload(payload, "Sign up failed.");
    } catch {
      state.authFeedback = "Sign up failed. Please try again.";
    } finally {
      state.isAuthSubmitting = false;
      render();
    }
  }

  async function handleLogout() {
    try {
      const response = await fetch("/auth/logout", { method: "POST", headers: { "X-CSRFToken": csrfTokenFromCookie() } });
      if (!response.ok) {
        setStatus("Logout failed.", true);
        render();
        return;
      }
    } catch {
      setStatus("Logout failed. Please try again.", true);
      render();
      return;
    }
    window.location.assign("/");
  }

  function collapseMobileProjectPicker() {
    if (typeof window.matchMedia !== "function" || !window.matchMedia("(max-width: 767px)").matches) {
      return;
    }
    state.projectSidebarSectionsOpen = {
      ...state.projectSidebarSectionsOpen,
      owned: false,
      interacted: false,
    };
  }

  function setProjectSlugAndHistory(slug) {
    state.view = "issues";
    state.selectedProjectSlug = slug;
    state.selectedIssueId = null;
    state.isIssueDetailOpen = false;
    state.loadedCommentsIssueId = null;
    state.comments = [];
    state.isNewIssueOpen = false;
    collapseMobileProjectPicker();
    const url = boardUrl(slug);
    if (window.location.pathname !== url) {
      window.history.pushState({ slug }, "", url);
    }
    refreshIssues().catch(() => {
      setStatus("Requests could not be loaded.", true);
      render();
    });
  }

  function navigateProjectAndHistory(ownerHandle, slug) {
    const targetOwnerHandle = normalizeHandle(ownerHandle || state.ownerHandle);
    if (!targetOwnerHandle || targetOwnerHandle === normalizeHandle(state.ownerHandle)) {
      setProjectSlugAndHistory(slug);
      return;
    }
    state.view = "issues";
    state.selectedProjectSlug = slug;
    state.selectedIssueId = null;
    state.isIssueDetailOpen = false;
    state.loadedCommentsIssueId = null;
    state.comments = [];
    state.isNewIssueOpen = false;
    collapseMobileProjectPicker();
    const url = projectBoardUrl(targetOwnerHandle, slug);
    if (window.location.pathname !== url) {
      window.history.pushState({ ownerHandle: targetOwnerHandle, slug }, "", url);
    }
    applyRouteToState();
    render();
    runRouteLoads().catch(() => {
      setStatus("Workspace could not be loaded.", true);
      render();
    });
  }

  function setSettingsSectionAndHistory(section, replaceHistory = false) {
    const normalizedSection = SETTINGS_SECTIONS.has(section) ? section : "general";
    state.view = settingsSectionToView(normalizedSection);
    state.isProfileMenuOpen = false;
    const nextUrl = settingsUrl(normalizedSection);
    if (window.location.pathname !== nextUrl) {
      window.history[replaceHistory ? "replaceState" : "pushState"]({ view: state.view }, "", nextUrl);
    }
    render();
    if (state.view === "settingsApi" || state.view === "settingsConnectAgent") {
      refreshApiTokens().catch(() => {
        state.apiTokenFeedback = "API tokens could not be loaded.";
        state.apiTokenFeedbackTone = "error";
        render();
      });
    }
    if (state.view === "settingsConnectAgent") {
      refreshAgentPromptProjects().catch(() => {
        state.agentPromptProjects = [];
        state.agentPromptProjectSlug = "";
        state.isAgentPromptProjectsLoading = false;
        render();
      });
    }
  }

  function setMessagesThreadAndHistory(threadId, replaceHistory = false) {
    const targetHandle = getHandleFromThreadId(threadId);
    state.view = "messages";
    state.selectedMessageThreadId = threadId;
    const nextUrl = messagesUrl(targetHandle);
    if (window.location.pathname !== nextUrl) {
      window.history[replaceHistory ? "replaceState" : "pushState"]({ view: "messages", selectedMessageHandle: targetHandle }, "", nextUrl);
    }
    render();
    if (state.isAuthenticated) {
      refreshMessages().catch(() => {
        setStatus("Messages could not be loaded.", true);
        render();
      });
    }
    refreshMessageSidebarProjects();
  }

  function openProjectFormForHandle(handle) {
    const ownerHandle = normalizeHandle(handle || state.ownerHandle || state.currentUserHandle);
    if (!ownerHandle) {
      return;
    }
    const targetUrl = `/${ownerHandle}/projects/new/`;
    if (ownerHandle !== normalizeHandle(state.ownerHandle)) {
      window.location.assign(targetUrl);
      return;
    }
    if (getComputed().isAtProjectLimit) {
      state.isUpgradePlanOpen = true;
      render();
      return;
    }
    state.projectNameDraft = "";
    state.projectTaglineDraft = "";
    state.projectUrlDraft = "";
    state.projectDraftProjectId = null;
    state.newProjectFeedback = "";
    state.newProjectFeedbackTone = "";
    state.view = "newProject";
    if (window.location.pathname !== targetUrl) {
      window.history.pushState({ slug: "projects", isProjectForm: true }, "", targetUrl);
    }
    render();
  }

  function openMessagesForContactHandle(handle) {
    const ownerHandle = normalizeHandle(handle);
    if (!ownerHandle) {
      return;
    }
    setMessagesThreadAndHistory(messageThreadIdFromHandle(ownerHandle));
  }

  async function handleIssuePatch(payload) {
    const selectedIssue = getComputed().selectedIssue;
    if (!state.isAuthenticated) {
      setStatus("Authentication required for this action.", true);
      render();
      return null;
    }
    if (!selectedIssue?.id) {
      return null;
    }
    state.isIssueUpdating = true;
    render();
    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify(payload),
      });
      const responsePayload = await jsonOrEmpty(response);
      if (!response.ok) {
        setStatus(detailFromPayload(responsePayload, "Issue update failed."), true);
        return null;
      }
      const updated = responsePayload;
      state.issues = state.issues.map((issue) => (issue.id === updated.id ? updated : issue));
      if (Object.prototype.hasOwnProperty.call(payload, "status")) {
        refreshProjects().catch(() => {});
      }
      setStatus("Issue updated.");
      return updated;
    } finally {
      state.isIssueUpdating = false;
      render();
    }
  }

  async function handleUpvote() {
    const selectedIssue = getComputed().selectedIssue;
    if (!state.isAuthenticated) {
      setStatus("Login required for upvote.", true);
      render();
      return;
    }
    if (!selectedIssue?.id) {
      return;
    }
    state.isIssueUpdating = true;
    render();
    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}/upvote/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
      });
      if (!response.ok) {
        setStatus("Upvote action failed.", true);
        return;
      }
      const data = await response.json();
      state.issues = state.issues.map((issue) => (issue.id === data.issue_id ? { ...issue, upvotes_count: data.upvotes_count } : issue));
      setStatus(data.upvoted ? "Upvoted." : "Upvote removed.");
    } finally {
      state.isIssueUpdating = false;
      render();
    }
  }

  async function handlePostComment() {
    const selectedIssue = getComputed().selectedIssue;
    if (!state.isAuthenticated) {
      state.commentFeedback = "Please log in to post a comment.";
      render();
      return;
    }
    if (!selectedIssue?.id || !state.commentDraft.trim()) {
      return;
    }
    state.isCommentSubmitting = true;
    state.commentFeedback = "";
    render();
    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ body: state.commentDraft.trim() }),
      });
      const responsePayload = await jsonOrEmpty(response);
      if (!response.ok) {
        state.commentFeedback = detailFromPayload(responsePayload, "Comment could not be posted.");
        return;
      }
      state.commentDraft = "";
      state.comments = [...state.comments, responsePayload];
      state.issues = state.issues.map((issue) =>
        issue.id === selectedIssue.id ? { ...issue, comments_count: Number(issue.comments_count || 0) + 1 } : issue,
      );
      setStatus("Comment posted.");
    } finally {
      state.isCommentSubmitting = false;
      render();
    }
  }

  async function handleSaveCommentEdit(commentId) {
    const selectedIssue = getComputed().selectedIssue;
    if (!state.isAuthenticated) {
      state.commentEditFeedback = "Please log in to edit this comment.";
      render();
      return;
    }
    const body = state.commentEditDraft.trim();
    if (!body) {
      state.commentEditFeedback = "Comment body is required.";
      render();
      return;
    }
    state.isCommentEditSubmitting = true;
    state.commentEditFeedback = "";
    render();
    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}/comments/${commentId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ body }),
      });
      const responsePayload = await jsonOrEmpty(response);
      if (!response.ok) {
        state.commentEditFeedback = detailFromPayload(responsePayload, "Comment could not be updated.");
        return;
      }
      state.comments = state.comments.map((item) => (item.id === responsePayload.id ? responsePayload : item));
      state.editingCommentId = null;
      state.commentEditDraft = "";
      state.commentEditFeedback = "";
      setStatus("Comment updated.");
    } finally {
      state.isCommentEditSubmitting = false;
      render();
    }
  }

  async function handleSubmitContact() {
    const trimmedBody = state.contactBody.trim();
    if (!trimmedBody) {
      state.contactFeedback = "Message body is required.";
      state.contactFeedbackTone = "error";
      render();
      return;
    }
    const payload = { body: trimmedBody };
    if (state.selectedProjectSlug) {
      payload.project_slug = state.selectedProjectSlug;
    }
    if (!state.isAuthenticated) {
      const trimmedName = state.contactSenderName.trim();
      const trimmedEmail = state.contactSenderEmail.trim();
      if (!trimmedName || !trimmedEmail) {
        state.contactFeedback = "Name and email are required.";
        state.contactFeedbackTone = "error";
        render();
        return;
      }
      payload.sender_name = trimmedName;
      payload.sender_email = trimmedEmail;
    }
    state.isContactSubmitting = true;
    state.contactFeedback = "Sending...";
    state.contactFeedbackTone = "";
    render();
    try {
      const response = await fetch(`/api/owners/${encodeURIComponent(state.ownerHandle)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify(payload),
      });
      const data = await jsonOrEmpty(response);
      if (!response.ok) {
        state.contactFeedback = detailFromPayload(data, "Message could not be sent.");
        state.contactFeedbackTone = "error";
        return;
      }
      state.contactFeedback = "Message sent.";
      state.contactFeedbackTone = "success";
      state.contactBody = "";
      state.contactSenderName = "";
      state.contactSenderEmail = "";
      setTimeout(() => {
        state.isContactOpen = false;
        state.contactFeedback = "";
        state.contactFeedbackTone = "";
        render();
      }, 500);
    } finally {
      state.isContactSubmitting = false;
      render();
    }
  }

  async function handleSendDirectMessage() {
    const computed = getComputed();
    if (!state.isAuthenticated) {
      openAuth("signIn");
      return;
    }
    const correspondentHandle = normalizeHandle(computed.selectedMessageHandle);
    if (!correspondentHandle) {
      state.messageComposerFeedback = "Select a user to start a conversation.";
      state.messageComposerFeedbackTone = "error";
      render();
      return;
    }
    if (correspondentHandle === normalizeHandle(state.currentUserHandle)) {
      state.messageComposerFeedback = "You cannot message yourself.";
      state.messageComposerFeedbackTone = "error";
      render();
      return;
    }
    const body = state.messageComposerBody.trim();
    if (!body) {
      state.messageComposerFeedback = "Message body is required.";
      state.messageComposerFeedbackTone = "error";
      render();
      return;
    }
    state.isMessageComposerSubmitting = true;
    state.messageComposerFeedback = "Sending...";
    state.messageComposerFeedbackTone = "";
    render();
    try {
      const response = await fetch(`/api/owners/${encodeURIComponent(correspondentHandle)}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ body }),
      });
      const data = await jsonOrEmpty(response);
      if (!response.ok) {
        state.messageComposerFeedback = detailFromPayload(data, "Message could not be sent.");
        state.messageComposerFeedbackTone = "error";
        return;
      }
      state.messageComposerBody = "";
      state.messageComposerFeedback = "Message sent.";
      state.messageComposerFeedbackTone = "success";
      setMessagesThreadAndHistory(messageThreadIdFromHandle(correspondentHandle), true);
      await refreshMessages();
    } finally {
      state.isMessageComposerSubmitting = false;
      render();
    }
  }

  async function handleSubmitNewIssue() {
    if (!state.isAuthenticated) {
      state.newIssueFeedback = "Please log in to create a request.";
      render();
      return;
    }
    if (!state.selectedProjectSlug) {
      return;
    }
    const title = state.newIssueTitle.trim();
    if (!title) {
      state.newIssueFeedback = "Title is required.";
      render();
      return;
    }
    state.isNewIssueSubmitting = true;
    state.newIssueFeedback = "Creating...";
    render();
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(state.ownerHandle)}/${encodeURIComponent(state.selectedProjectSlug)}/issues`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({
          issue_type: state.newIssueType,
          title,
          description: state.newIssueDescription.trim(),
          priority: Number(state.newIssuePriority),
        }),
      });
      const data = await jsonOrEmpty(response);
      if (!response.ok) {
        state.newIssueFeedback = detailFromPayload(data, "Request creation failed.");
        return;
      }
      state.newIssueTitle = "";
      state.newIssueDescription = "";
      state.newIssueType = "feature";
      state.newIssuePriority = "2";
      state.isNewIssueOpen = false;
      state.newIssueFeedback = "";
      await Promise.all([refreshIssues(), refreshProjects()]);
      state.selectedIssueId = data.id;
      state.isIssueDetailOpen = true;
      setStatus("Request created.");
    } finally {
      state.isNewIssueSubmitting = false;
      render();
    }
  }

  async function handleUpgradePlan() {
    state.upgradePlanFeedback = "";
    state.isUpgradePlanSubmitting = true;
    render();
    try {
      await ensureCsrfCookie();
      const response = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ plan_id: PROJECT_UPGRADE_PLAN.id }),
      });
      const payload = await jsonOrEmpty(response);
      if (!response.ok) {
        state.upgradePlanFeedback = detailFromPayload(payload, "Could not create checkout session.");
        return;
      }
      const checkoutUrl = typeof payload.checkout_url === "string" ? payload.checkout_url : "";
      if (!checkoutUrl) {
        state.upgradePlanFeedback = "Checkout URL is unavailable.";
        return;
      }
      window.location.assign(checkoutUrl);
    } catch {
      state.upgradePlanFeedback = "Checkout request failed. Please try again.";
    } finally {
      state.isUpgradePlanSubmitting = false;
      render();
    }
  }

  async function handleRefreshAgentToken() {
    const computed = getComputed();
    if (!state.isAuthenticated) {
      openAuth("signIn");
      return;
    }
    state.isAgentRefreshSubmitting = true;
    state.apiTokenFeedback = "";
    state.apiTokenFeedbackTone = "";
    render();
    try {
      await ensureCsrfCookie();
      const response = await fetch("/api/auth/agent-token/refresh", {
        method: "POST",
        headers: { "X-CSRFToken": csrfTokenFromCookie() },
      });
      const data = await jsonOrEmpty(response);
      if (!response.ok) {
        state.apiTokenFeedback = detailFromPayload(data, "Token refresh failed.");
        state.apiTokenFeedbackTone = "error";
        return;
      }
      const tokenRow = {
        id: data.id,
        name: data.name,
        can_write: Boolean(data.can_write),
        token_prefix: data.token_prefix,
        created_at: data.created_at,
        last_used_at: data.last_used_at,
      };
      const tokenValue = String(data.token || "");
      state.apiTokens = [tokenRow];
      if (tokenValue) {
        writeStoredAgentToken(state.currentUserHandle, tokenValue);
        state.apiTokenSecrets = { ...state.apiTokenSecrets, [tokenRow.id]: tokenValue };
      }
      state.latestCreatedTokenValue = tokenValue;
      state.agentPromptValue = buildAgentPromptText(computed.apiBaseUrl, tokenValue);
      state.apiTokenFeedback = "Agent token refreshed.";
      state.apiTokenFeedbackTone = "success";
    } finally {
      state.isAgentRefreshSubmitting = false;
      render();
    }
  }

  async function copyValueAndNotify(value, successText) {
    const copied = await copyToClipboard(value);
    if (!copied) {
      state.apiTokenFeedback = "Copy failed. Please copy manually.";
      state.apiTokenFeedbackTone = "error";
      render();
      return;
    }
    state.apiTokenFeedback = successText;
    state.apiTokenFeedbackTone = "success";
    render();
  }

  async function handleSubmitNewProject() {
    const computed = getComputed();
    if (!state.isAuthenticated) {
      openAuth("signIn");
      return;
    }
    if (!computed.isOwnerViewer) {
      state.newProjectFeedback = "Only the owner can create projects.";
      state.newProjectFeedbackTone = "error";
      render();
      return;
    }
    const name = state.projectNameDraft.trim();
    if (!name) {
      state.newProjectFeedback = "Project name is required.";
      state.newProjectFeedbackTone = "error";
      render();
      return;
    }
    state.isNewProjectSubmitting = true;
    state.newProjectFeedback = "Creating...";
    state.newProjectFeedbackTone = "";
    render();
    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ name, tagline: state.projectTaglineDraft.trim(), url: state.projectUrlDraft.trim() }),
      });
      const data = await jsonOrEmpty(response);
      if (!response.ok) {
        state.newProjectFeedback = detailFromPayload(data, "Project creation failed.");
        state.newProjectFeedbackTone = "error";
        return;
      }
      state.projectNameDraft = "";
      state.projectTaglineDraft = "";
      state.projectUrlDraft = "";
      state.newProjectFeedback = "Project created.";
      state.newProjectFeedbackTone = "success";
      state.projects = [...state.projects, data];
      state.selectedProjectSlug = data.slug;
      const nextUrl = boardUrl(data.slug);
      if (window.location.pathname !== nextUrl) {
        window.history.pushState({ slug: data.slug }, "", nextUrl);
      }
      await refreshProjects();
      state.view = "issues";
      setStatus("Project created.");
    } finally {
      state.isNewProjectSubmitting = false;
      render();
    }
  }

  async function handleSaveProjectSettings() {
    const computed = getComputed();
    const project = computed.selectedProject;
    if (!project) {
      setStatus("Select a project first.", true);
      render();
      return;
    }
    if (!computed.isOwnerViewer) {
      setStatus("Only the project owner can update settings.", true);
      render();
      return;
    }
    state.isProjectSaving = true;
    state.projectFeedback = "Saving...";
    state.projectFeedbackTone = "";
    render();
    try {
      const response = await fetch(`/api/projects/${project.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({
          name: state.projectNameDraft,
          tagline: state.projectTaglineDraft,
          url: state.projectUrlDraft,
        }),
      });
      const data = await jsonOrEmpty(response);
      if (!response.ok) {
        state.projectFeedback = detailFromPayload(data, "Project update failed.");
        state.projectFeedbackTone = "error";
        return;
      }
      const previousSlug = project.slug;
      state.projects = state.projects.map((item) => (item.id === data.id ? data : item));
      if (previousSlug !== data.slug) {
        state.selectedProjectSlug = data.slug;
        const nextUrl = boardUrl(data.slug);
        if (window.location.pathname !== nextUrl) {
          window.history.replaceState({ slug: data.slug }, "", nextUrl);
        }
      }
      state.projectFeedback = "Project updated.";
      state.projectFeedbackTone = "success";
      setStatus("Project updated.");
    } finally {
      state.isProjectSaving = false;
      render();
    }
  }

  async function handleDeleteProject() {
    const computed = getComputed();
    const project = computed.selectedProject;
    if (!project || !computed.isOwnerViewer || state.deleteSlugConfirm.trim() !== project.slug) {
      return;
    }
    state.isProjectDeleting = true;
    render();
    try {
      const response = await fetch(`/api/projects/${project.id}`, {
        method: "DELETE",
        headers: { "X-CSRFToken": csrfTokenFromCookie() },
      });
      if (!response.ok) {
        setStatus("Project delete failed.", true);
        return;
      }
      const deletedSlug = project.slug;
      state.projects = state.projects.filter((item) => item.id !== project.id);
      if (state.selectedProjectSlug === deletedSlug) {
        state.selectedProjectSlug = "";
        const url = boardUrl("");
        if (window.location.pathname !== url) {
          window.history.replaceState({ slug: "" }, "", url);
        }
      }
      state.deleteSlugConfirm = "";
      state.isDeleteModalOpen = false;
      state.view = "issues";
      setStatus("Project deleted.");
    } finally {
      state.isProjectDeleting = false;
      render();
    }
  }

  async function selectPlan(planId) {
    state.pricingFeedback = "";
    state.isPricingSubmitting = true;
    render();
    try {
      await ensureCsrfCookie();
      const response = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfTokenFromCookie() },
        body: JSON.stringify({ plan_id: planId }),
      });
      const payload = await jsonOrEmpty(response);
      if (!response.ok) {
        state.pricingFeedback = detailFromPayload(payload, "Plan selection failed.");
        return;
      }
      if (payload.checkout_url) {
        window.location.assign(payload.checkout_url);
        return;
      }
      if (state.isAuthenticated && state.currentUserHandle) {
        window.location.assign(`/${state.currentUserHandle}/`);
        return;
      }
      openAuth("signUp");
    } catch {
      state.pricingFeedback = "Plan selection failed. Please try again.";
    } finally {
      state.isPricingSubmitting = false;
      render();
    }
  }

  function handleInput(event) {
    const target = event.target;
    const bind = target?.dataset?.bind;
    if (!bind || !(bind in state)) {
      return;
    }
    state[bind] = target.value;
    if (["typeFilter", "statusFilter", "priorityFilter"].includes(bind)) {
      state.isIssueDetailOpen = false;
      refreshIssues().catch(() => {
        setStatus("Requests could not be loaded.", true);
        render();
      });
      return;
    }
    render();
  }

  root.addEventListener("input", handleInput);
  root.addEventListener("change", (event) => {
    const actionTarget = event.target.closest("[data-patch-issue]");
    if (actionTarget) {
      const field = actionTarget.dataset.field;
      const value = field === "priority" ? Number(actionTarget.value) : actionTarget.value;
      handleIssuePatch({ [field]: value });
      return;
    }
    handleInput(event);
  });

  root.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-form]");
    if (!form) {
      return;
    }
    event.preventDefault();
    if (form.dataset.form === "sign-in") {
      onSignInSubmit();
    } else if (form.dataset.form === "sign-up") {
      onSignUpSubmit();
    }
  });

  root.addEventListener("click", (event) => {
    const actionElement = event.target.closest("[data-action]");
    if (!actionElement) {
      return;
    }
    const action = actionElement.dataset.action;
    if (action !== "modal-backdrop") {
      event.preventDefault();
    } else if (event.target !== actionElement) {
      return;
    }
    handleAction(action, actionElement);
  });

  document.addEventListener("mousedown", (event) => {
    if (!state.isProfileMenuOpen) {
      return;
    }
    if (!event.target.closest("[data-profile-menu]")) {
      state.isProfileMenuOpen = false;
      render();
    }
  });

  window.addEventListener("popstate", () => {
    applyRouteToState();
    render();
    runRouteLoads();
  });

  function handleAction(action, element) {
    const computed = getComputed();
    switch (action) {
      case "open-auth":
        openAuth(element.dataset.mode || "signIn");
        break;
      case "close-auth":
        closeAuth();
        break;
      case "modal-backdrop":
        closeModal(element.dataset.modal);
        break;
      case "open-pricing":
        state.selectedPlanId = "free";
        state.pricingFeedback = "";
        state.isPricingOpen = true;
        render();
        break;
      case "close-pricing":
        state.isPricingOpen = false;
        state.pricingFeedback = "";
        render();
        break;
      case "select-plan":
        state.selectedPlanId = element.dataset.plan || "free";
        state.pricingFeedback = "";
        render();
        break;
      case "submit-pricing":
        selectPlan(state.selectedPlanId);
        break;
      case "landing-create-board":
      case "landing-first-board":
        if (state.isAuthenticated && state.currentUserHandle) {
          window.location.assign(action === "landing-first-board" ? `/${state.currentUserHandle}/projects/new/` : `/${state.currentUserHandle}/`);
        } else {
          openAuth("signUp");
        }
        break;
      case "toggle-profile":
        state.isProfileMenuOpen = !state.isProfileMenuOpen;
        render();
        break;
      case "close-profile":
        state.isProfileMenuOpen = false;
        render();
        break;
      case "logout":
        handleLogout();
        break;
      case "profile-new-project":
        state.isProfileMenuOpen = false;
        openProjectFormForHandle(computed.workspaceOwnerHandle);
        break;
      case "open-project-form":
        openProjectFormForHandle(computed.sidebarProjectsOwnerHandle || state.ownerHandle || state.currentUserHandle);
        break;
      case "toggle-project-section":
        state.projectSidebarSectionsOpen[element.dataset.section || "owned"] =
          state.projectSidebarSectionsOpen[element.dataset.section || "owned"] === false;
        render();
        break;
      case "navigate-project":
        navigateProjectAndHistory(element.dataset.owner || state.ownerHandle, element.dataset.slug || "");
        break;
      case "open-project-settings":
        state.selectedProjectSlug = element.dataset.slug || state.selectedProjectSlug;
        state.view = "projectSettings";
        render();
        break;
      case "select-issue":
        state.selectedIssueId = Number(element.dataset.id);
        state.isIssueDetailOpen = true;
        state.isNewIssueOpen = false;
        render();
        break;
      case "back-to-request-list":
        state.isIssueDetailOpen = false;
        state.isNewIssueOpen = false;
        render();
        break;
      case "open-new-issue":
        if (!state.selectedProjectSlug) {
          setStatus("Select a project first.", true);
        } else if (!state.isAuthenticated) {
          openAuth("signIn");
          return;
        } else {
          state.newIssueFeedback = "";
          state.isNewIssueOpen = true;
          state.isIssueDetailOpen = false;
        }
        render();
        break;
      case "close-new-issue":
        state.isNewIssueOpen = false;
        state.isIssueDetailOpen = false;
        render();
        break;
      case "submit-new-issue":
        handleSubmitNewIssue();
        break;
      case "reset-filters":
        state.typeFilter = "";
        state.statusFilter = "";
        state.priorityFilter = "";
        state.searchQuery = "";
        state.isIssueDetailOpen = false;
        refreshIssues();
        break;
      case "upvote":
        handleUpvote();
        break;
      case "edit-issue":
        if (computed.selectedIssue) {
          state.issueTitleDraft = computed.selectedIssue.title || "";
          state.issueDescriptionDraft = computed.selectedIssue.description || "";
          state.issueEditFeedback = "";
          state.isIssueEditOpen = true;
          render();
        }
        break;
      case "cancel-issue-edit":
        state.issueTitleDraft = computed.selectedIssue?.title || "";
        state.issueDescriptionDraft = computed.selectedIssue?.description || "";
        state.issueEditFeedback = "";
        state.isIssueEditOpen = false;
        render();
        break;
      case "save-issue-edit":
        if (!state.issueTitleDraft.trim()) {
          state.issueEditFeedback = "Title is required.";
          render();
          return;
        }
        handleIssuePatch({ title: state.issueTitleDraft.trim(), description: state.issueDescriptionDraft.trim() }).then((updated) => {
          if (updated) {
            state.isIssueEditOpen = false;
            render();
          } else {
            state.issueEditFeedback = "Request could not be updated.";
            render();
          }
        });
        break;
      case "post-comment":
        handlePostComment();
        break;
      case "edit-comment": {
        const comment = state.comments.find((item) => item.id === Number(element.dataset.id));
        if (comment) {
          state.editingCommentId = comment.id;
          state.commentEditDraft = comment.body || "";
          state.commentEditFeedback = "";
          render();
        }
        break;
      }
      case "cancel-comment-edit":
        state.editingCommentId = null;
        state.commentEditDraft = "";
        state.commentEditFeedback = "";
        render();
        break;
      case "save-comment-edit":
        handleSaveCommentEdit(Number(element.dataset.id));
        break;
      case "open-sidebar-contact":
        if (computed.isSidebarOwnerViewer) {
          openProjectFormForHandle(computed.sidebarProjectsOwnerHandle);
        } else if (computed.sidebarProjectsOwnerHandle) {
          openMessagesForContactHandle(computed.sidebarProjectsOwnerHandle);
        } else {
          state.isContactOpen = true;
          render();
        }
        break;
      case "close-contact":
        state.isContactOpen = false;
        state.contactFeedback = "";
        state.contactFeedbackTone = "";
        render();
        break;
      case "submit-contact":
        handleSubmitContact();
        break;
      case "select-message-thread":
        setMessagesThreadAndHistory(element.dataset.thread || "");
        break;
      case "refresh-messages":
        refreshMessages();
        break;
      case "send-direct-message":
        handleSendDirectMessage();
        break;
      case "settings-nav":
        setSettingsSectionAndHistory(element.dataset.section || "general");
        break;
      case "copy-base-url":
        copyValueAndNotify(computed.apiBaseUrl, "Base URL copied.");
        break;
      case "copy-agent-token":
        copyValueAndNotify(computed.activeAgentTokenSecret, "Token copied.");
        break;
      case "refresh-agent-token":
        handleRefreshAgentToken();
        break;
      case "select-agent-prompt-preset":
        state.agentPromptPreset = normalizeAgentPromptPreset(element.dataset.preset);
        if (isProjectAgentPromptPreset(state.agentPromptPreset) && !state.agentPromptProjectSlug && computed.agentPromptProjects.length) {
          state.agentPromptProjectSlug = computed.agentPromptProjects[0].slug;
        }
        state.agentPromptCopyFeedback = "";
        state.agentPromptCopyFeedbackTone = "";
        render();
        break;
      case "copy-agent-prompt":
        handleCopyAgentPromptFromSettings();
        break;
      case "copy-project-agent-prompt":
        if (computed.isOwnerViewer) {
          handleCopyProjectAgentPrompt(computed.selectedProject);
        }
        break;
      case "copy-api-token":
        copyValueAndNotify(state.apiTokenSecrets[element.dataset.id], "Token copied.");
        break;
      case "close-new-project":
        state.isNewProjectSubmitting = false;
        state.newProjectFeedback = "";
        state.newProjectFeedbackTone = "";
        state.view = "issues";
        if (window.location.pathname !== boardUrl("")) {
          window.history.pushState({ slug: "" }, "", boardUrl(""));
        }
        render();
        break;
      case "submit-new-project":
        handleSubmitNewProject();
        break;
      case "save-project":
        handleSaveProjectSettings();
        break;
      case "open-delete-modal":
        state.isDeleteModalOpen = true;
        render();
        break;
      case "close-delete-modal":
        state.isDeleteModalOpen = false;
        render();
        break;
      case "confirm-delete-project":
        handleDeleteProject();
        break;
      case "close-upgrade":
        state.isUpgradePlanOpen = false;
        state.upgradePlanFeedback = "";
        render();
        break;
      case "upgrade-plan":
        handleUpgradePlan();
        break;
      default:
        break;
    }
  }

  function closeModal(modalName) {
    if (modalName === "auth") {
      closeAuth();
      return;
    }
    if (modalName === "pricing") {
      state.isPricingOpen = false;
    }
    if (modalName === "contact") {
      state.isContactOpen = false;
      state.contactFeedback = "";
      state.contactFeedbackTone = "";
    }
    if (modalName === "upgrade") {
      state.isUpgradePlanOpen = false;
      state.upgradePlanFeedback = "";
    }
    if (modalName === "delete") {
      state.isDeleteModalOpen = false;
    }
    render();
  }

  async function runRouteLoads() {
    if (isLandingRoute()) {
      render();
      return;
    }
    const route = parseRoute();
    if (route.kind === "notFound") {
      state.isRouteNotFound = true;
      render();
      return;
    }
    if (route.kind === "board") {
      await refreshProjects();
      if (!state.isRouteNotFound) {
        await refreshInteractedProjects();
      }
      if (!state.isRouteNotFound && state.view === "issues") {
        await refreshIssues();
      }
      return;
    }
    if (route.kind === "messages") {
      if (state.isAuthenticated) {
        await refreshMessages();
      }
      await refreshMessageSidebarProjects();
      return;
    }
    if (route.kind === "settings" && (state.view === "settingsApi" || state.view === "settingsConnectAgent")) {
      await refreshApiTokens();
      if (state.view === "settingsConnectAgent") {
        await refreshAgentPromptProjects();
      }
    }
  }

  async function init() {
    applyRouteToState();
    state.authMode = initialAuthModeFromRoute();
    render();
    try {
      await refreshSession();
    } catch {
      state.isAuthenticated = false;
      state.currentUserHandle = "";
      state.currentUserAvatarUrl = "";
    }
    if (state.isAuthenticated && isLandingRoute()) {
      state.authMode = null;
    }
    render();
    await runRouteLoads();
  }

  init();
})();
