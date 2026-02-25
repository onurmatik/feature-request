import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowBigUpDash,
  Folder,
  LayoutGrid,
  Layers,
  Mail,
  LogOut,
  Plus,
  Search,
  ChevronDown,
  Settings,
} from "lucide-react";

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

const PROJECT_UPGRADE_PLAN = {
  id: "pro_30",
  title: "Growth",
  name: "Pro",
  description: "$3/mo for up to 30 projects",
  cta: "Upgrade",
};

function cls(...values) {
  return values.filter(Boolean).join(" ");
}

function parseBootstrap() {
  const value = window.__FR_BOOTSTRAP__ || {};
  const pathParts = window.location.pathname.split("/").filter(Boolean);
  const ownerFromPath = pathParts[0] || "";
  const slugFromPath = pathParts[1] || "";
  const isProjectFormRoute = pathParts[0] === ownerFromPath && pathParts[1] === "projects" && pathParts[2] === "new";
  const initialProjectSlug = isProjectFormRoute ? "" : String(value.initialProjectSlug || slugFromPath);
  return {
    ownerHandle: String(value.ownerHandle || ownerFromPath).toLowerCase(),
    initialProjectSlug,
    isProjectFormRoute,
    isAuthenticated: Boolean(value.isAuthenticated),
    currentUserHandle: String(value.currentUserHandle || "").trim(),
    subscriptionTier: String(value.subscription_tier || "free").toLowerCase(),
    subscriptionStatus: String(value.subscription_status || "").toLowerCase(),
    projectLimit: Number(value.project_limit || 1),
  };
}

function csrfTokenFromCookie() {
  const tokenPart = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith("csrftoken="));

  return tokenPart ? decodeURIComponent(tokenPart.slice("csrftoken=".length)) : "";
}

function toReadableStatus(status) {
  const mapped = {
    in_progress: "In Progress",
  };

  if (mapped[status]) {
    return mapped[status];
  }

  return String(status || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function toReadableType(value) {
  return value === "bug" ? "Bug" : "Feature";
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
    const minutes = Math.max(1, Math.round(diff / minute));
    return `${minutes}m ago`;
  }

  if (diff < day) {
    const hours = Math.round(diff / hour);
    return `${hours}h ago`;
  }

  const days = Math.round(diff / day);
  return `${days}d ago`;
}

function formatLongDate(isoString) {
  if (!isoString) {
    return "-";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  }).format(new Date(isoString));
}

function getSlugFromPath(ownerHandle) {
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts[0] !== ownerHandle) {
    return "";
  }

  return parts[1] || "";
}

function isProjectFormPath(ownerHandle) {
  const parts = window.location.pathname.split("/").filter(Boolean);
  return parts[0] === ownerHandle && parts[1] === "projects" && parts[2] === "new";
}

export default function App() {
  const bootstrap = useMemo(parseBootstrap, []);

  const [projects, setProjects] = useState([]);
  const [issues, setIssues] = useState([]);
  const [selectedProjectSlug, setSelectedProjectSlug] = useState(bootstrap.initialProjectSlug || "");
  const [selectedIssueId, setSelectedIssueId] = useState(null);

  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const [statusLine, setStatusLine] = useState("");
  const [statusError, setStatusError] = useState(false);

  const [view, setView] = useState(bootstrap.isProjectFormRoute ? "newProject" : "issues");

  const [comments, setComments] = useState([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [isCommentSubmitting, setIsCommentSubmitting] = useState(false);
  const [isIssueUpdating, setIsIssueUpdating] = useState(false);

  const [isContactOpen, setIsContactOpen] = useState(false);
  const [contactSenderName, setContactSenderName] = useState("");
  const [contactSenderEmail, setContactSenderEmail] = useState("");
  const [contactBody, setContactBody] = useState("");
  const [contactFeedback, setContactFeedback] = useState("");
  const [contactFeedbackTone, setContactFeedbackTone] = useState("");
  const [isContactSubmitting, setIsContactSubmitting] = useState(false);

  const [isNewIssueOpen, setIsNewIssueOpen] = useState(false);
  const [newIssueTitle, setNewIssueTitle] = useState("");
  const [newIssueDescription, setNewIssueDescription] = useState("");
  const [newIssueType, setNewIssueType] = useState("feature");
  const [newIssuePriority, setNewIssuePriority] = useState("2");
  const [newIssueFeedback, setNewIssueFeedback] = useState("");
  const [isNewIssueSubmitting, setIsNewIssueSubmitting] = useState(false);

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteSlugConfirm, setDeleteSlugConfirm] = useState("");
  const [projectNameDraft, setProjectNameDraft] = useState("");
  const [projectTaglineDraft, setProjectTaglineDraft] = useState("");
  const [projectUrlDraft, setProjectUrlDraft] = useState("");
  const [projectFeedback, setProjectFeedback] = useState("");
  const [projectFeedbackTone, setProjectFeedbackTone] = useState("");
  const [isProjectSaving, setIsProjectSaving] = useState(false);
  const [isNewProjectSubmitting, setIsNewProjectSubmitting] = useState(false);
  const [newProjectFeedback, setNewProjectFeedback] = useState("");
  const [newProjectFeedbackTone, setNewProjectFeedbackTone] = useState("");
  const [isProjectDeleting, setIsProjectDeleting] = useState(false);
  const [isUpgradePlanOpen, setIsUpgradePlanOpen] = useState(false);
  const [isUpgradePlanSubmitting, setIsUpgradePlanSubmitting] = useState(false);
  const [upgradePlanFeedback, setUpgradePlanFeedback] = useState("");
  const [isAuthenticated, setIsAuthenticated] = useState(bootstrap.isAuthenticated);
  const [currentUserHandle, setCurrentUserHandle] = useState(bootstrap.currentUserHandle);
  const [subscriptionTier, setSubscriptionTier] = useState(bootstrap.subscriptionTier);
  const [subscriptionStatus, setSubscriptionStatus] = useState(bootstrap.subscriptionStatus);
  const [projectLimit, setProjectLimit] = useState(Number(bootstrap.projectLimit || 1));
  const [signInIdentity, setSignInIdentity] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [signUpHandle, setSignUpHandle] = useState("");
  const [authMode, setAuthMode] = useState(null);
  const [authFeedback, setAuthFeedback] = useState("");
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef(null);

  const selectedProject = useMemo(
    () => projects.find((project) => project.slug === selectedProjectSlug) || null,
    [projects, selectedProjectSlug],
  );
  const isOwnerViewer = useMemo(
    () =>
      isAuthenticated &&
      String(currentUserHandle || "").toLowerCase() === bootstrap.ownerHandle,
    [currentUserHandle, isAuthenticated, bootstrap.ownerHandle],
  );
  const projectLimitToUse = Number(projectLimit || 1);
  const hasActivePaidPlan = subscriptionTier === "pro_30" && subscriptionStatus === "active";
  const isAtProjectLimit = isOwnerViewer && !hasActivePaidPlan && projects.length >= projectLimitToUse;
  const projectFormUrl = useMemo(() => {
    if (!bootstrap.ownerHandle) {
      return "/projects/new/";
    }

    return `/${bootstrap.ownerHandle}/projects/new/`;
  }, [bootstrap.ownerHandle]);

  const shouldShowUpgradeForProjects = isAtProjectLimit && isOwnerViewer;

  const filteredIssues = useMemo(() => {
    if (!searchQuery.trim()) {
      return issues;
    }

    const query = searchQuery.trim().toLowerCase();
    return issues.filter((issue) => {
      const title = String(issue.title || "").toLowerCase();
      const description = String(issue.description || "").toLowerCase();
      return title.includes(query) || description.includes(query);
    });
  }, [issues, searchQuery]);

  const selectedIssue = useMemo(
    () => filteredIssues.find((issue) => issue.id === selectedIssueId) || null,
    [filteredIssues, selectedIssueId],
  );

  useEffect(() => {
    if (!filteredIssues.length) {
      setSelectedIssueId(null);
      return;
    }

    if (!filteredIssues.some((issue) => issue.id === selectedIssueId)) {
      setSelectedIssueId(filteredIssues[0].id);
    }
  }, [filteredIssues, selectedIssueId]);

  const boardUrl = useCallback(
    (slug) => {
      if (!bootstrap.ownerHandle) {
        return "/";
      }
      return slug ? `/${bootstrap.ownerHandle}/${slug}/` : `/${bootstrap.ownerHandle}/`;
    },
    [bootstrap.ownerHandle],
  );

  const setStatus = useCallback((text, isError = false) => {
    setStatusLine(text);
    setStatusError(isError);
  }, []);

  const refreshSession = useCallback(async () => {
    const response = await fetch("/auth/me");
    if (!response.ok) {
      setIsAuthenticated(false);
      setCurrentUserHandle("");
      setSubscriptionTier("free");
      setSubscriptionStatus("");
      setProjectLimit(1);
      return;
    }

    const data = await response.json();
    setIsAuthenticated(Boolean(data.is_authenticated));
    setCurrentUserHandle(String(data.current_user_handle || ""));
    setSubscriptionTier(String(data.subscription_tier || "free").toLowerCase());
    setSubscriptionStatus(String(data.subscription_status || "").toLowerCase());
    setProjectLimit(Number(data.project_limit || 1));
  }, []);

  async function ensureCsrfCookie() {
    await fetch("/auth/me");
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
        setAuthFeedback(
          typeof payload.detail === "string"
            ? payload.detail
            : "Sign in link sent. Check your email.",
        );
        return;
      }
      setIsAuthenticated(true);
      setCurrentUserHandle(handle);
      setSubscriptionTier(String(payload.subscription_tier || "free").toLowerCase());
      setSubscriptionStatus(String(payload.subscription_status || "").toLowerCase());
      setProjectLimit(Number(payload.project_limit || 1));
      closeAuth();
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
    setAuthFeedback("Sending sign-up link...");

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
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : "Sign up failed.";
        setAuthFeedback(detail);
        return;
      }

      setAuthFeedback(
        typeof payload.detail === "string"
          ? payload.detail
          : "Sign-up link sent. Check your email.",
      );
    } catch {
      setAuthFeedback("Sign up failed. Please try again.");
    } finally {
      setIsAuthSubmitting(false);
    }
  }

  async function handleLogout() {
    if (!isAuthenticated) {
      setIsProfileMenuOpen(false);
      return;
    }

    try {
      const response = await fetch("/auth/logout", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfTokenFromCookie(),
        },
      });

      if (!response.ok) {
        setStatus("Logout failed.", true);
        setIsProfileMenuOpen(false);
        return;
      }
    } catch {
      setStatus("Logout failed. Please try again.", true);
      setIsProfileMenuOpen(false);
      return;
    }

    setIsProfileMenuOpen(false);
    setIsAuthenticated(false);
    setCurrentUserHandle("");
    setSubscriptionTier("free");
    setSubscriptionStatus("");
    setProjectLimit(1);
    setAuthMode(null);
    window.location.assign("/");
  }

  const refreshProjects = useCallback(async () => {
    if (!bootstrap.ownerHandle) {
      throw new Error("Owner handle is missing in URL.");
    }

    const response = await fetch(`/api/owners/${encodeURIComponent(bootstrap.ownerHandle)}/projects`);
    if (!response.ok) {
      throw new Error("Projects could not be loaded.");
    }

    const data = await response.json();
    setProjects(data);
    setSelectedProjectSlug((previousSlug) => {
      if (!previousSlug) {
        return "";
      }

      return data.some((project) => project.slug === previousSlug) ? previousSlug : "";
    });
  }, [bootstrap.ownerHandle]);

  const refreshIssues = useCallback(async () => {
    if (!bootstrap.ownerHandle) {
      setIssues([]);
      setStatus("Owner handle is missing in URL.", true);
      return;
    }

    const params = new URLSearchParams();

    if (selectedProjectSlug) {
      params.set("project_slug", selectedProjectSlug);
    }
    if (typeFilter) {
      params.set("issue_type", typeFilter);
    }
    if (statusFilter) {
      params.set("status", statusFilter);
    }
    if (priorityFilter) {
      params.set("priority", priorityFilter);
    }

    setStatus("Requests loading...");

    const url = `/api/owners/${encodeURIComponent(bootstrap.ownerHandle)}/issues${
      params.toString() ? `?${params.toString()}` : ""
    }`;
    const response = await fetch(url);

    if (!response.ok) {
      setIssues([]);
      setStatus("Requests could not be loaded.", true);
      return;
    }

    const data = await response.json();
    setIssues(data);
    setStatus(`${data.length} requests listed.`);
  }, [bootstrap.ownerHandle, selectedProjectSlug, typeFilter, statusFilter, priorityFilter, setStatus]);

  const refreshComments = useCallback(async (issueId) => {
    if (!issueId) {
      setComments([]);
      return;
    }

    const response = await fetch(`/api/issues/${issueId}/comments`);
    if (!response.ok) {
      setComments([]);
      return;
    }

    const data = await response.json();
    setComments(data);
  }, []);

  useEffect(() => {
    refreshSession().catch(() => {
      setIsAuthenticated(false);
      setCurrentUserHandle("");
    });
  }, [refreshSession]);

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      try {
        await refreshProjects();
        if (!cancelled) {
          await refreshIssues();
        }
      } catch (error) {
        if (!cancelled) {
          setStatus(error instanceof Error ? error.message : "Board could not be loaded.", true);
        }
      }
    }

    boot();

    return () => {
      cancelled = true;
    };
  }, [refreshProjects, refreshIssues, setStatus]);

  useEffect(() => {
    if (!isProfileMenuOpen) {
      return;
    }

    function onDocumentMouseDown(event) {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
        setIsProfileMenuOpen(false);
      }
    }

    window.addEventListener("mousedown", onDocumentMouseDown);
    return () => {
      window.removeEventListener("mousedown", onDocumentMouseDown);
    };
  }, [isProfileMenuOpen]);

  useEffect(() => {
    refreshIssues().catch(() => {
      setStatus("Requests could not be loaded.", true);
    });
  }, [refreshIssues, setStatus]);

  useEffect(() => {
    if (!selectedIssue?.id) {
      setComments([]);
      return;
    }

    refreshComments(selectedIssue.id).catch(() => {
      setComments([]);
    });
  }, [selectedIssue?.id, refreshComments]);

  useEffect(() => {
    function onPopState() {
      const isProjectForm = isProjectFormPath(bootstrap.ownerHandle);
      const slug = isProjectForm ? "" : getSlugFromPath(bootstrap.ownerHandle);
      setView(isProjectForm ? "newProject" : "issues");
      setSelectedProjectSlug(slug);
    }

    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, [bootstrap.ownerHandle]);

  useEffect(() => {
    const onProjectFormRoute = isProjectFormPath(bootstrap.ownerHandle);
    if (!onProjectFormRoute || !shouldShowUpgradeForProjects) {
      return;
    }

    openUpgradePlanModal();
    setView("issues");
    const url = boardUrl("");
    if (window.location.pathname !== url) {
      window.history.replaceState({ slug: "" }, "", url);
    }
  }, [bootstrap.ownerHandle, boardUrl, shouldShowUpgradeForProjects]);

  useEffect(() => {
    if (!selectedProject) {
      setDeleteSlugConfirm("");
      setProjectNameDraft("");
      setProjectTaglineDraft("");
      setProjectUrlDraft("");
      setProjectFeedback("");
      setProjectFeedbackTone("");
      return;
    }

    setProjectNameDraft(selectedProject.name || "");
    setProjectTaglineDraft(selectedProject.tagline || "");
    setProjectUrlDraft(selectedProject.url || "");
    setProjectFeedback("");
    setProjectFeedbackTone("");
  }, [selectedProject]);

  function setProjectSlugAndHistory(nextSlug) {
    setView("issues");
    setSelectedProjectSlug(nextSlug);

    const url = boardUrl(nextSlug);
    if (window.location.pathname !== url) {
      window.history.pushState({ slug: nextSlug }, "", url);
    }
  }

  async function handleIssuePatch(payload) {
    if (!isAuthenticated) {
      setStatus("Authentication required for this action.", true);
      return;
    }

    if (!selectedIssue?.id) {
      return;
    }

    setIsIssueUpdating(true);

    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        setStatus("Issue update failed.", true);
        return;
      }

      const updated = await response.json();
      setIssues((previous) => previous.map((issue) => (issue.id === updated.id ? updated : issue)));
      setStatus("Issue updated.");
    } finally {
      setIsIssueUpdating(false);
    }
  }

  async function handleUpvote() {
    if (!isAuthenticated) {
      setStatus("Login required for upvote.", true);
      return;
    }

    if (!selectedIssue?.id) {
      return;
    }

    setIsIssueUpdating(true);

    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}/upvote/toggle`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
      });

      if (!response.ok) {
        setStatus("Upvote action failed.", true);
        return;
      }

      const data = await response.json();
      setIssues((previous) =>
        previous.map((issue) =>
          issue.id === data.issue_id ? { ...issue, upvotes_count: data.upvotes_count } : issue,
        ),
      );
      setStatus(data.upvoted ? "Upvoted." : "Upvote removed.");
    } finally {
      setIsIssueUpdating(false);
    }
  }

  async function handlePostComment() {
    if (!isAuthenticated) {
      setStatus("Login required for commenting.", true);
      return;
    }

    if (!selectedIssue?.id) {
      return;
    }

    const body = commentDraft.trim();
    if (!body) {
      return;
    }

    setIsCommentSubmitting(true);

    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}/comments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({ body }),
      });

      if (!response.ok) {
        setStatus("Comment could not be posted.", true);
        return;
      }

      const created = await response.json();
      setCommentDraft("");
      setComments((previous) => [...previous, created]);
      setIssues((previous) =>
        previous.map((issue) =>
          issue.id === selectedIssue.id
            ? { ...issue, comments_count: Number(issue.comments_count || 0) + 1 }
            : issue,
        ),
      );
      setStatus("Comment posted.");
    } finally {
      setIsCommentSubmitting(false);
    }
  }

  async function handleSubmitContact() {
    const trimmedBody = contactBody.trim();
    if (!trimmedBody) {
      setContactFeedback("Message body is required.");
      setContactFeedbackTone("error");
      return;
    }

    const payload = {
      body: trimmedBody,
    };

    if (selectedProjectSlug) {
      payload.project_slug = selectedProjectSlug;
    }

    if (!isAuthenticated) {
      const trimmedName = contactSenderName.trim();
      const trimmedEmail = contactSenderEmail.trim();

      if (!trimmedName || !trimmedEmail) {
        setContactFeedback("Name and email are required.");
        setContactFeedbackTone("error");
        return;
      }

      payload.sender_name = trimmedName;
      payload.sender_email = trimmedEmail;
    }

    setIsContactSubmitting(true);
    setContactFeedback("Sending...");
    setContactFeedbackTone("");

    try {
      const response = await fetch(`/api/owners/${encodeURIComponent(bootstrap.ownerHandle)}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Message could not be sent.";
        setContactFeedback(detail);
        setContactFeedbackTone("error");
        return;
      }

      setContactFeedback("Message sent.");
      setContactFeedbackTone("success");
      setContactBody("");
      setContactSenderName("");
      setContactSenderEmail("");
      setTimeout(() => {
        setIsContactOpen(false);
        setContactFeedback("");
        setContactFeedbackTone("");
      }, 500);
    } finally {
      setIsContactSubmitting(false);
    }
  }

  function openNewIssueModal() {
    if (!selectedProjectSlug) {
      setStatus("Select a project first.", true);
      return;
    }

    if (!isAuthenticated) {
      openAuth("signIn");
      return;
    }

    setNewIssueFeedback("");
    setIsNewIssueOpen(true);
  }

  function openUpgradePlanModal() {
    setUpgradePlanFeedback("");
    setIsUpgradePlanSubmitting(false);
    setIsUpgradePlanOpen(true);
  }

  function closeUpgradePlanModal() {
    setIsUpgradePlanOpen(false);
    setUpgradePlanFeedback("");
    setIsUpgradePlanSubmitting(false);
  }

  async function handleUpgradePlan() {
    setUpgradePlanFeedback("");
    setIsUpgradePlanSubmitting(true);

    try {
      await ensureCsrfCookie();
      const response = await fetch("/api/billing/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({ plan_id: PROJECT_UPGRADE_PLAN.id }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail =
          typeof payload.detail === "string" ? payload.detail : "Could not create checkout session.";
        setUpgradePlanFeedback(detail);
        return;
      }

      const checkoutUrl = typeof payload.checkout_url === "string" ? payload.checkout_url : "";
      if (!checkoutUrl) {
        setUpgradePlanFeedback("Checkout URL is unavailable.");
        return;
      }

      window.location.assign(checkoutUrl);
    } catch {
      setUpgradePlanFeedback("Checkout request failed. Please try again.");
    } finally {
      setIsUpgradePlanSubmitting(false);
    }
  }

  function handleProjectMenuNavigation(event) {
    setIsProfileMenuOpen(false);
    if (shouldShowUpgradeForProjects) {
      event.preventDefault();
      openUpgradePlanModal();
      return;
    }

    event.preventDefault();
    setProjectNameDraft("");
    setProjectTaglineDraft("");
    setProjectUrlDraft("");
    setNewProjectFeedback("");
    setNewProjectFeedbackTone("");
    setView("newProject");
    if (window.location.pathname !== projectFormUrl) {
      window.history.pushState({ slug: "projects", isProjectForm: true }, "", projectFormUrl);
    }
  }

  function handleProjectFormNavigation(event) {
    if (shouldShowUpgradeForProjects) {
      event.preventDefault();
      openUpgradePlanModal();
      return;
    }

    event.preventDefault();
    setProjectNameDraft("");
    setProjectTaglineDraft("");
    setProjectUrlDraft("");
    setNewProjectFeedback("");
    setNewProjectFeedbackTone("");
    setView("newProject");
    if (window.location.pathname !== projectFormUrl) {
      window.history.pushState({ slug: "projects", isProjectForm: true }, "", projectFormUrl);
    }
  }

  function closeNewProjectForm() {
    setIsNewProjectSubmitting(false);
    setNewProjectFeedback("");
    setNewProjectFeedbackTone("");
    setView("issues");
    const url = boardUrl("");
    if (window.location.pathname !== url) {
      window.history.pushState({ slug: "" }, "", url);
    }
  }

  async function handleSubmitNewProject() {
    if (!isAuthenticated) {
      openAuth("signIn");
      return;
    }

    if (!isOwnerViewer) {
      setNewProjectFeedback("Only the owner can create projects.");
      setNewProjectFeedbackTone("error");
      return;
    }

    const name = projectNameDraft.trim();
    if (!name) {
      setNewProjectFeedback("Project name is required.");
      setNewProjectFeedbackTone("error");
      return;
    }

    setIsNewProjectSubmitting(true);
    setNewProjectFeedback("Creating...");
    setNewProjectFeedbackTone("");

    try {
      const response = await fetch("/api/projects", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({
          name,
          tagline: projectTaglineDraft.trim(),
          url: projectUrlDraft.trim(),
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Project creation failed.";
        setNewProjectFeedback(detail);
        setNewProjectFeedbackTone("error");
        return;
      }

      setProjectNameDraft("");
      setProjectTaglineDraft("");
      setProjectUrlDraft("");
      setNewProjectFeedback("Project created.");
      setNewProjectFeedbackTone("success");
      setProjects((previous) => [...previous, data]);
      setSelectedProjectSlug(data.slug);
      const nextUrl = boardUrl(data.slug);
      if (window.location.pathname !== nextUrl) {
        window.history.pushState({ slug: data.slug }, "", nextUrl);
      }
      await refreshProjects();
      setView("issues");
      setStatus("Project created.");
    } finally {
      setIsNewProjectSubmitting(false);
    }
  }

  async function handleSubmitNewIssue() {
    if (!selectedProjectSlug) {
      return;
    }

    const title = newIssueTitle.trim();
    if (!title) {
      setNewIssueFeedback("Title is required.");
      return;
    }

    setIsNewIssueSubmitting(true);
    setNewIssueFeedback("Creating...");

    try {
      const response = await fetch(
        `/api/projects/${encodeURIComponent(bootstrap.ownerHandle)}/${encodeURIComponent(selectedProjectSlug)}/issues`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfTokenFromCookie(),
          },
          body: JSON.stringify({
            issue_type: newIssueType,
            title,
            description: newIssueDescription.trim(),
            priority: Number(newIssuePriority),
          }),
        },
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Request creation failed.";
        setNewIssueFeedback(detail);
        return;
      }

      setNewIssueTitle("");
      setNewIssueDescription("");
      setNewIssueType("feature");
      setNewIssuePriority("2");
      setIsNewIssueOpen(false);
      setNewIssueFeedback("");

      await refreshIssues();
      setSelectedIssueId(data.id);
      setStatus("Request created.");
    } finally {
      setIsNewIssueSubmitting(false);
    }
  }

  async function handleSaveProjectSettings() {
    if (!selectedProject) {
      setStatus("Select a project first.", true);
      return;
    }

    if (!isOwnerViewer) {
      setStatus("Only the project owner can update settings.", true);
      return;
    }

    const payload = {
      name: projectNameDraft,
      tagline: projectTaglineDraft,
      url: projectUrlDraft,
    };

    setIsProjectSaving(true);
    setProjectFeedback("Saving...");
    setProjectFeedbackTone("");

    try {
      const response = await fetch(`/api/projects/${selectedProject.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Project update failed.";
        setProjectFeedback(detail);
        setProjectFeedbackTone("error");
        return;
      }

      const previousSlug = selectedProject.slug;
      setProjects((previous) =>
        previous.map((project) => (project.id === data.id ? data : project)),
      );
      if (previousSlug !== data.slug) {
        setSelectedProjectSlug(data.slug);
        const nextUrl = boardUrl(data.slug);
        if (window.location.pathname !== nextUrl) {
          window.history.replaceState({ slug: data.slug }, "", nextUrl);
        }
      }

      setProjectFeedback("Project updated.");
      setProjectFeedbackTone("success");
      setStatus("Project updated.");
    } finally {
      setIsProjectSaving(false);
    }
  }

  async function handleDeleteProject() {
    if (!selectedProject) {
      return;
    }

    if (!isOwnerViewer) {
      setStatus("Only the project owner can delete projects.", true);
      return;
    }

    if (deleteSlugConfirm.trim() !== selectedProject.slug) {
      return;
    }

    setIsProjectDeleting(true);
    try {
      const response = await fetch(`/api/projects/${selectedProject.id}`, {
        method: "DELETE",
        headers: {
          "X-CSRFToken": csrfTokenFromCookie(),
        },
      });

      if (!response.ok) {
        setStatus("Project delete failed.", true);
        return;
      }

      const deletedSlug = selectedProject.slug;
      setProjects((previous) => previous.filter((project) => project.id !== selectedProject.id));
      if (selectedProjectSlug === deletedSlug) {
        setSelectedProjectSlug("");
        const url = boardUrl("");
        if (window.location.pathname !== url) {
          window.history.replaceState({ slug: "" }, "", url);
        }
      }
      setDeleteSlugConfirm("");
      setIsDeleteModalOpen(false);
      setView("issues");
      setStatus("Project deleted.");
    } finally {
      setIsProjectDeleting(false);
    }
  }

  const projectButtons = (
    <>
      <button
        type="button"
        data-project="All Projects"
        onClick={() => setProjectSlugAndHistory("")}
        className={cls(
          "sidebar-project-btn w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds font-medium text-sm transition-colors",
          !selectedProjectSlug
            ? "bg-cyan-50 text-[#06B6D4]"
            : "text-[#6b7280] hover:bg-[#f3f4f6]",
        )}
      >
        <LayoutGrid size={18} />
        All Projects
      </button>
      <div className="space-y-1">
        <h3 className="px-3 text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider mb-2">
          Projects
        </h3>
        {projects.map((project) => (
          <button
            key={project.id}
            type="button"
            data-project={project.slug}
            onClick={() => setProjectSlugAndHistory(project.slug)}
            className={cls(
              "sidebar-project-btn w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds font-medium text-sm transition-colors",
              selectedProjectSlug === project.slug
                ? "bg-cyan-50 text-[#06B6D4]"
                : "text-[#6b7280] hover:bg-[#f3f4f6]",
            )}
          >
            <Folder size={18} />
            {project.name}
          </button>
        ))}
      </div>
    </>
  );

  return (
    <div className="h-screen flex flex-col bg-[#f3f4f6] text-[#111827]">
      <header className="h-[56px] bg-white border-b border-[#e5e7eb] flex items-center justify-between px-4 md:px-6 shrink-0 z-50">
        <div className="flex items-center gap-4 md:gap-6 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            <a href="/" className="flex items-center gap-2">
              <div className="w-8 h-8 bg-[#06B6D4] rounded-sm-ds flex items-center justify-center text-white shadow-sm">
                <Layers size={20} />
              </div>
              <span className="font-bold text-lg tracking-tight">FeatureRequest</span>
            </a>
          </div>

          <nav className="hidden md:flex items-center text-sm font-medium text-[#6b7280] gap-2 truncate">
            <a
              href={`/${bootstrap.ownerHandle || ""}/`}
              className="hover:text-[#111827]"
            >
              {bootstrap.ownerHandle || "owner"}
            </a>
            <span className="text-[#d1d5db] font-mono">/</span>
            <span className="text-[#111827] font-semibold truncate">
              {selectedProject ? selectedProject.name : "All Projects"}
            </span>
            {isOwnerViewer ? (
              <button
                type="button"
                onClick={() => setView((current) => (current === "issues" ? "settings" : "issues"))}
                disabled={!selectedProjectSlug}
                className={cls(
                  "ml-2 p-1 rounded text-[#6b7280] transition-colors flex items-center",
                  selectedProjectSlug
                    ? view === "settings"
                      ? "bg-cyan-50 text-[#06B6D4] hover:text-[#111827] hover:bg-[#f3f4f6]"
                      : "hover:text-[#111827] hover:bg-[#f3f4f6]"
                    : "cursor-not-allowed opacity-45",
                  view === "settings" ? "bg-cyan-50 text-[#06B6D4]" : "",
                )}
                title="Project Settings"
                aria-label="Project Settings"
              >
                <Settings size={18} />
              </button>
            ) : null}
            {isOwnerViewer ? (
              <a
                href={projectFormUrl}
                onClick={handleProjectFormNavigation}
                aria-label="Create New Project"
                className="ml-2 p-1 rounded flex items-center text-[#6b7280] hover:text-[#111827] hover:bg-[#f3f4f6] transition-colors"
                title="Create New Project"
              >
                <Plus size={18} />
              </a>
            ) : null}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {isOwnerViewer ? (
            <button
              type="button"
              onClick={() => setView((current) => (current === "issues" ? "settings" : "issues"))}
              disabled={!selectedProjectSlug}
              className={cls(
                "md:hidden p-1 rounded text-[#6b7280] transition-colors flex items-center",
                selectedProjectSlug
                  ? view === "settings"
                    ? "bg-cyan-50 text-[#06B6D4] hover:text-[#111827] hover:bg-[#f3f4f6]"
                    : "hover:text-[#111827] hover:bg-[#f3f4f6]"
                  : "cursor-not-allowed opacity-45",
              )}
              title="Project Settings"
              aria-label="Project Settings"
            >
              <Settings size={18} />
            </button>
          ) : null}
          {isOwnerViewer ? (
            <a
              href={projectFormUrl}
              onClick={handleProjectFormNavigation}
              aria-label="Create New Project"
              className="md:hidden p-1 rounded flex items-center text-[#6b7280] hover:text-[#111827] hover:bg-[#f3f4f6] transition-colors"
              title="Create New Project"
            >
              <Plus size={18} />
            </a>
          ) : null}
          {isAuthenticated ? (
            <div ref={profileMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setIsProfileMenuOpen((value) => !value)}
                className="flex items-center gap-2 rounded-sm-ds border border-transparent px-2 py-1 transition-colors hover:border-[#e5e7eb] hover:bg-[#f8fafc]"
              >
                <span className="text-xs font-mono text-[#6b7280]">{currentUserHandle || "user"}</span>
                <div className="w-8 h-8 rounded-full bg-cyan-50 flex items-center justify-center text-[#06B6D4] font-bold text-xs border border-cyan-100">
                  {(currentUserHandle || "US").slice(0, 2).toUpperCase()}
                </div>
                <ChevronDown size={14} className="text-[#6b7280]" />
              </button>

              {isProfileMenuOpen ? (
                <div className="absolute right-0 top-full mt-2 w-44 rounded-sm-ds border border-[#e5e7eb] bg-white shadow-sm overflow-hidden z-50">
                  {isOwnerViewer ? (
                    <a
                      href={projectFormUrl}
                      onClick={(event) => {
                        handleProjectMenuNavigation(event);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
                    >
                      <Plus size={16} />
                      New Project
                    </a>
                  ) : null}
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
                  >
                    <LogOut size={16} />
                    Logout
                  </button>
                </div>
              ) : null}
            </div>
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

      <div className="flex-1 flex overflow-hidden">
        <aside className="w-60 bg-white border-r border-[#e5e7eb] flex-col shrink-0 hidden md:flex">
          <div className="flex-1 p-2 space-y-4 overflow-y-auto">{projectButtons}</div>

          <div className="p-2 border-t border-[#e5e7eb]">
            <button
              type="button"
              onClick={() => {
                setContactFeedback("");
                setContactFeedbackTone("");
                setIsContactOpen(true);
              }}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds text-[#6b7280] hover:bg-[#f3f4f6] font-medium text-sm transition-colors"
            >
              <Mail size={18} />
              Contact @{bootstrap.ownerHandle || "owner"}
            </button>
          </div>
        </aside>

        <div className="flex-1 flex overflow-hidden">
          {view === "issues" ? (
                <div className="flex-1 flex overflow-hidden">
                  <section className="w-full md:w-[380px] border-r border-[#e5e7eb] bg-white flex flex-col shrink-0">
                <div className="p-4 border-b border-[#e5e7eb] space-y-3">
                  <div className="md:hidden space-y-3">{projectButtons}</div>

                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold uppercase tracking-widest text-[#6b7280]">Requests</h2>
                    <button
                      type="button"
                      onClick={openNewIssueModal}
                      className="px-3 py-1.5 bg-[#06B6D4] text-white text-[10px] font-bold rounded-sm-ds hover:bg-cyan-600 shadow-sm transition-all uppercase tracking-wide disabled:opacity-45 disabled:cursor-not-allowed"
                      disabled={!selectedProjectSlug}
                    >
                      New Request
                    </button>
                  </div>

                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#d1d5db]" size={16} />
                    <input
                      value={searchQuery}
                      onChange={(event) => setSearchQuery(event.target.value)}
                      type="text"
                      placeholder="Filter issues..."
                      className="w-full pl-9 pr-3 py-2 bg-[#f3f4f6] border border-[#e5e7eb] text-xs rounded-sm-ds focus:ring-1 focus:ring-[#06B6D4] outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <select
                      value={typeFilter}
                      onChange={(event) => setTypeFilter(event.target.value)}
                      className="text-[11px] font-medium bg-white border border-[#e5e7eb] rounded-sm-ds px-2 py-1 outline-none"
                    >
                      {TYPE_OPTIONS.map((option) => (
                        <option key={option.label} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={statusFilter}
                      onChange={(event) => setStatusFilter(event.target.value)}
                      className="text-[11px] font-medium bg-white border border-[#e5e7eb] rounded-sm-ds px-2 py-1 outline-none"
                    >
                      {STATUS_OPTIONS.map((option) => (
                        <option key={option.label} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={priorityFilter}
                      onChange={(event) => setPriorityFilter(event.target.value)}
                      className="text-[11px] font-medium bg-white border border-[#e5e7eb] rounded-sm-ds px-2 py-1 outline-none"
                    >
                      {PRIORITY_OPTIONS.map((option) => (
                        <option key={option.label} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className={cls("text-xs", statusError ? "text-[#dc2626]" : "text-[#6b7280]")}>{statusLine}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setTypeFilter("");
                        setStatusFilter("");
                        setPriorityFilter("");
                        setSearchQuery("");
                      }}
                      className="text-[10px] font-mono font-bold text-[#6b7280] hover:text-[#111827] uppercase"
                    >
                      Reset
                    </button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto divide-y divide-[#e5e7eb]">
                  {!filteredIssues.length ? (
                    <div className="p-4 text-sm text-[#6b7280]">No requests found for this filter.</div>
                  ) : (
                    filteredIssues.map((issue) => {
                      const active = issue.id === selectedIssueId;

                      return (
                        <button
                          key={issue.id}
                          type="button"
                          onClick={() => setSelectedIssueId(issue.id)}
                          className={cls(
                            "issue-list-item w-full text-left p-4 cursor-pointer transition-colors group",
                            active
                              ? "bg-cyan-50/50 border-l-4 border-[#06B6D4]"
                              : "hover:bg-[#f9fafb] border-l-4 border-transparent",
                          )}
                        >
                          <div className="flex justify-between items-start mb-1">
                            <span className={cls("text-[10px] font-mono font-bold", active ? "text-[#06B6D4]" : "text-[#d1d5db]")}>
                              #{issue.id}
                            </span>
                            <span className="text-[10px] text-[#6b7280]">{formatRelativeDate(issue.created_at)}</span>
                          </div>
                          <h3
                            className={cls(
                              "text-sm leading-tight mb-2",
                              active
                                ? "font-semibold text-[#111827] group-hover:text-[#06B6D4]"
                                : "font-medium text-[#111827]",
                            )}
                          >
                            {issue.title}
                          </h3>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span
                              className={cls(
                                "px-1.5 py-0.5 bg-white border text-[9px] font-mono font-bold rounded uppercase",
                                typeTone(issue.issue_type),
                              )}
                            >
                              {toReadableType(issue.issue_type)}
                            </span>
                            <span
                              className={cls(
                                "px-1.5 py-0.5 bg-white border text-[9px] font-mono font-bold rounded uppercase",
                                statusTone(issue.status),
                              )}
                            >
                              {toReadableStatus(issue.status)}
                            </span>
                            <div className="flex-1" />
                            <div className="flex items-center gap-1 text-[#6b7280]">
                              <ArrowBigUpDash size={14} />
                              <span className="text-[10px] font-mono font-bold">{issue.upvotes_count}</span>
                            </div>
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
                  </section>

              <main className="hidden lg:flex flex-1 bg-white flex-col overflow-hidden">
                {isNewIssueOpen ? (
                  <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
                    <h1 className="text-2xl font-bold text-[#111827]">Create New Request</h1>
                    <p className="text-sm text-[#6b7280]">Describe your issue in detail below.</p>

                    <div className="space-y-1.5">
                      <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Title</label>
                      <input
                        value={newIssueTitle}
                        onChange={(event) => setNewIssueTitle(event.target.value)}
                        type="text"
                        className="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Description</label>
                      <textarea
                        rows={5}
                        value={newIssueDescription}
                        onChange={(event) => setNewIssueDescription(event.target.value)}
                        className="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-y"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Issue Type</label>
                        <select
                          value={newIssueType}
                          onChange={(event) => setNewIssueType(event.target.value)}
                          className="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"
                        >
                          <option value="feature">Feature</option>
                          <option value="bug">Bug</option>
                        </select>
                      </div>

                      <div className="space-y-1.5">
                        <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Priority</label>
                        <select
                          value={newIssuePriority}
                          onChange={(event) => setNewIssuePriority(event.target.value)}
                          className="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"
                        >
                          <option value="1">Low</option>
                          <option value="2">Medium</option>
                          <option value="3">High</option>
                          <option value="4">Critical</option>
                        </select>
                      </div>
                    </div>

                    {newIssueFeedback ? (
                      <p
                        className={
                          newIssueFeedback.toLowerCase().includes("rejected by moderation")
                            ? "text-xs text-[#b91c1c]"
                            : "text-xs text-[#6b7280]"
                        }
                      >
                        {newIssueFeedback}
                      </p>
                    ) : null}

                    <div className="flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => setIsNewIssueOpen(false)}
                        className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={handleSubmitNewIssue}
                        disabled={isNewIssueSubmitting}
                        className="px-4 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all shadow-sm disabled:opacity-45"
                      >
                        Create Request
                      </button>
                    </div>
                  </div>
                ) : selectedIssue ? (
                  <>
                    <header className="px-8 py-4 border-b border-[#e5e7eb] flex items-center justify-between shrink-0">
                      <div className="flex items-center gap-4">
                        <button
                          type="button"
                          onClick={handleUpvote}
                          disabled={isIssueUpdating}
                          className="flex items-center gap-1.5 px-3 py-1.5 border border-[#e5e7eb] rounded-sm-ds text-[#111827] font-semibold text-xs hover:bg-[#f3f4f6] transition-colors disabled:opacity-50"
                        >
                          <ArrowBigUpDash size={18} className="text-[#06B6D4]" />
                          Upvote ({selectedIssue.upvotes_count})
                        </button>
                        <div className="h-4 w-[1px] bg-[#e5e7eb]" />
                        <span className="text-[10px] font-mono text-[#6b7280] uppercase">
                          Created by user #{selectedIssue.author_id} • {formatLongDate(selectedIssue.created_at)}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2 border border-[#e5e7eb] rounded-sm-ds px-2 py-1">
                          <label className="text-[10px] font-mono text-[#6b7280] uppercase">Status</label>
                          <select
                            value={selectedIssue.status}
                            disabled={!isAuthenticated || isIssueUpdating}
                            onChange={(event) => handleIssuePatch({ status: event.target.value })}
                            className="text-xs font-bold text-[#16a34a] bg-transparent outline-none cursor-pointer disabled:cursor-not-allowed"
                          >
                            {DETAIL_STATUS_OPTIONS.map((option) => (
                              <option key={option.label} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="flex items-center gap-2 border border-[#e5e7eb] rounded-sm-ds px-2 py-1">
                          <label className="text-[10px] font-mono text-[#6b7280] uppercase">Priority</label>
                          <select
                            value={String(selectedIssue.priority)}
                            disabled={!isAuthenticated || isIssueUpdating}
                            onChange={(event) => handleIssuePatch({ priority: Number(event.target.value) })}
                            className="text-xs font-bold text-[#f59e0b] bg-transparent outline-none cursor-pointer disabled:cursor-not-allowed"
                          >
                            {PRIORITY_OPTIONS.filter((option) => option.value).map((option) => (
                              <option key={option.label} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </header>

                    <div className="flex-1 overflow-y-auto px-8 py-6 space-y-8">
                      <div>
                        <h1 className="text-2xl font-bold text-[#111827] mb-4">{selectedIssue.title}</h1>
                        <div className="prose prose-sm max-w-none text-[#6b7280] space-y-4">
                          {selectedIssue.description ? (
                            <p>{selectedIssue.description}</p>
                          ) : (
                            <p>No description provided.</p>
                          )}
                        </div>
                      </div>

                      <div className="border-t border-[#e5e7eb] pt-8">
                        <h4 className="text-xs font-bold text-[#6b7280] uppercase tracking-widest mb-6">
                          Activity & Comments ({comments.length})
                        </h4>

                        <div className="space-y-6 mb-8">
                          {comments.length === 0 ? (
                            <p className="text-sm text-[#6b7280]">No comments yet.</p>
                          ) : (
                            comments.map((comment) => (
                              <div key={comment.id} className="flex gap-4">
                                <div className="w-8 h-8 rounded-full bg-cyan-50 flex items-center justify-center text-[#06B6D4] font-bold text-[10px] shrink-0">
                                  {String(comment.author_handle || "??").slice(0, 2).toUpperCase()}
                                </div>
                                <div className="flex-1">
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="text-xs font-bold">@{comment.author_handle}</span>
                                    <span className="text-[10px] font-mono text-[#d1d5db]">
                                      {formatRelativeDate(comment.created_at)}
                                    </span>
                                  </div>
                                  <div className="p-3 bg-[#f9fafb] border border-[#e5e7eb] rounded-sm-ds text-sm text-[#6b7280]">
                                    {comment.body}
                                  </div>
                                </div>
                              </div>
                            ))
                          )}
                        </div>

                        <div className="bg-[#f9fafb] border border-[#e5e7eb] rounded-md-ds p-4">
                          <textarea
                            rows={3}
                            value={commentDraft}
                            onChange={(event) => setCommentDraft(event.target.value)}
                            className="w-full bg-white border border-[#e5e7eb] rounded-sm-ds p-3 text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none mb-3"
                            placeholder={isAuthenticated ? "Type your comment..." : "Login to post a comment."}
                            disabled={!isAuthenticated || isCommentSubmitting}
                          />
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-mono text-[#d1d5db]">Markdown supported</span>
                            <button
                              type="button"
                              onClick={handlePostComment}
                              disabled={!isAuthenticated || isCommentSubmitting || !commentDraft.trim()}
                              className="px-4 py-1.5 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors disabled:opacity-45 disabled:cursor-not-allowed"
                            >
                              Post Comment
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="p-10 text-[#6b7280]">Select a request to view details.</div>
                )}
              </main>
            </div>
          ) : view === "settings" ? (
            <div className="flex-1 bg-white flex flex-col overflow-y-auto">
              <div className="max-w-3xl mx-auto w-full px-6 md:px-8 py-10 space-y-12">
                <div>
                  <h2 className="text-2xl font-bold text-[#111827] mb-2">Project Settings</h2>
                  <p className="text-sm text-[#6b7280]">
                    Manage your project metadata and administrative controls.
                  </p>
                </div>

                <section className="space-y-6">
                  <div className="pb-4 border-b border-[#e5e7eb]">
                    <h3 className="text-sm font-bold uppercase tracking-widest text-[#6b7280]">General Information</h3>
                  </div>
                  {!isOwnerViewer ? (
                    <p className="text-xs text-[#6b7280]">
                      You are viewing this board as a visitor. Only @{bootstrap.ownerHandle} can edit project settings.
                    </p>
                  ) : null}

                  {selectedProject ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-1.5">
                        <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">
                          Project Name
                        </label>
                        <input
                          type="text"
                          value={projectNameDraft}
                          onChange={(event) => setProjectNameDraft(event.target.value)}
                          disabled={!isOwnerViewer || isProjectSaving}
                          className={cls(
                            "w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm",
                            isOwnerViewer ? "bg-white" : "bg-[#f9fafb]",
                          )}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Project URL</label>
                        <input
                          type="url"
                          value={projectUrlDraft}
                          onChange={(event) => setProjectUrlDraft(event.target.value)}
                          disabled={!isOwnerViewer || isProjectSaving}
                          placeholder="https://example.com"
                          className={cls(
                            "w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm",
                            isOwnerViewer ? "bg-white" : "bg-[#f9fafb]",
                          )}
                        />
                      </div>
                      <div className="md:col-span-2 space-y-1.5">
                        <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Tagline</label>
                        <input
                          type="text"
                          value={projectTaglineDraft}
                          onChange={(event) => setProjectTaglineDraft(event.target.value)}
                          disabled={!isOwnerViewer || isProjectSaving}
                          className={cls(
                            "w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm",
                            isOwnerViewer ? "bg-white" : "bg-[#f9fafb]",
                          )}
                        />
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-[#6b7280]">Select a project from sidebar and open settings.</p>
                  )}

                  {projectFeedback ? (
                    <p
                      className={cls(
                        "text-xs",
                        projectFeedbackTone === "error"
                          ? "text-[#dc2626]"
                          : projectFeedbackTone === "success"
                            ? "text-[#16a34a]"
                            : "text-[#6b7280]",
                      )}
                    >
                      {projectFeedback}
                    </p>
                  ) : null}

                  <div className="flex justify-end">
                    <button
                      type="button"
                      onClick={handleSaveProjectSettings}
                      disabled={!selectedProject || !isOwnerViewer || isProjectSaving}
                      className="px-6 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 shadow-sm transition-all disabled:opacity-45"
                    >
                      {isProjectSaving ? "Saving..." : "Save Changes"}
                    </button>
                  </div>
                </section>

                <section className="space-y-6">
                  <div className="pb-4 border-b border-[#e5e7eb]">
                    <h3 className="text-sm font-bold uppercase tracking-widest text-[#dc2626]">Danger Zone</h3>
                  </div>

                  <div className="p-4 border border-rose-100 bg-rose-50 rounded-md-ds flex flex-col md:flex-row gap-4 md:items-center md:justify-between">
                    <div className="space-y-1">
                      <p className="text-sm font-bold text-[#111827]">Delete this project</p>
                      <p className="text-xs text-[#6b7280]">
                        Once deleted, all data including issues and comments will be permanently removed.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsDeleteModalOpen(true)}
                      className="px-4 py-2 bg-[#dc2626] text-white text-xs font-bold rounded-sm-ds hover:bg-red-700 transition-all shadow-sm"
                      disabled={!selectedProject || !isOwnerViewer || isProjectDeleting}
                    >
                      Delete Project
                    </button>
                  </div>
                </section>
              </div>
            </div>
          ) : (
            <div className="flex-1 bg-white flex flex-col overflow-y-auto">
              <div className="max-w-3xl mx-auto w-full px-6 md:px-8 py-10 space-y-12">
                <div>
                  <h2 className="text-2xl font-bold text-[#111827] mb-2">New Project</h2>
                  <p className="text-sm text-[#6b7280]">Create a new project under your workspace.</p>
                </div>

                {!isOwnerViewer ? <p className="text-sm text-[#6b7280]">Only the board owner can create a project.</p> : null}

                <section className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-1.5">
                      <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Project Name</label>
                      <input
                        type="text"
                        value={projectNameDraft}
                        onChange={(event) => setProjectNameDraft(event.target.value)}
                        disabled={!isOwnerViewer || isNewProjectSubmitting}
                        className={cls(
                          "w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm",
                          isOwnerViewer ? "bg-white" : "bg-[#f9fafb]",
                        )}
                      />
                    </div>
                      <div className="space-y-1.5">
                        <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Project URL</label>
                        <input
                          type="url"
                          value={projectUrlDraft}
                          onChange={(event) => setProjectUrlDraft(event.target.value)}
                          disabled={!isOwnerViewer || isNewProjectSubmitting}
                          placeholder="https://example.com"
                          className={cls(
                            "w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm",
                            isOwnerViewer ? "bg-white" : "bg-[#f9fafb]",
                          )}
                        />
                    </div>
                    <div className="md:col-span-2 space-y-1.5">
                      <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Tagline</label>
                      <input
                        type="text"
                        value={projectTaglineDraft}
                        onChange={(event) => setProjectTaglineDraft(event.target.value)}
                        disabled={!isOwnerViewer || isNewProjectSubmitting}
                        className={cls(
                          "w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm",
                          isOwnerViewer ? "bg-white" : "bg-[#f9fafb]",
                        )}
                      />
                    </div>
                  </div>

                  {newProjectFeedback ? (
                    <p
                      className={cls(
                        "text-xs",
                        newProjectFeedbackTone === "error"
                          ? "text-[#dc2626]"
                          : newProjectFeedbackTone === "success"
                            ? "text-[#16a34a]"
                            : "text-[#6b7280]",
                      )}
                    >
                      {newProjectFeedback}
                    </p>
                  ) : null}

                  <div className="flex justify-end gap-3">
                    <button
                      type="button"
                      onClick={closeNewProjectForm}
                      className="px-6 py-2 border border-[#e5e7eb] text-[#6b7280] text-sm font-bold rounded-sm-ds hover:bg-[#f3f4f6] transition-all"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleSubmitNewProject}
                      disabled={!isOwnerViewer || isNewProjectSubmitting}
                      className="px-6 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 shadow-sm transition-all disabled:opacity-45"
                    >
                      {isNewProjectSubmitting ? "Creating..." : "Create Project"}
                    </button>
                  </div>
                </section>
              </div>
            </div>
          )}
        </div>
      </div>

      {isContactOpen ? (
        <div
          className="fixed inset-0 bg-[#111827]/60 backdrop-blur-[2px] z-[100] flex items-center justify-center p-4"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setIsContactOpen(false);
              setContactFeedback("");
              setContactFeedbackTone("");
            }
          }}
        >
          <div className="bg-white rounded-md-ds shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <h3 className="text-lg font-bold text-[#111827] mb-2">Message @{bootstrap.ownerHandle || "owner"}</h3>
              <p className="text-sm text-[#6b7280] mb-6">
                Have a question or feedback? Send a direct message to the project maintainer.
              </p>

              {!isAuthenticated ? (
                <div className="space-y-3 mb-4">
                  <div>
                    <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Name</label>
                    <input
                      value={contactSenderName}
                      onChange={(event) => setContactSenderName(event.target.value)}
                      type="text"
                      className="mt-1 w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Email</label>
                    <input
                      value={contactSenderEmail}
                      onChange={(event) => setContactSenderEmail(event.target.value)}
                      type="email"
                      className="mt-1 w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none"
                    />
                  </div>
                </div>
              ) : null}

              <div className="space-y-3">
                <label className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">Your Message</label>
                <textarea
                  rows={4}
                  placeholder="How can we help?"
                  value={contactBody}
                  onChange={(event) => setContactBody(event.target.value)}
                  className="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none"
                />
                {contactFeedback ? (
                  <p
                    className={cls(
                      "text-xs",
                      contactFeedbackTone === "error"
                        ? "text-[#dc2626]"
                        : contactFeedbackTone === "success"
                          ? "text-[#16a34a]"
                          : "text-[#6b7280]",
                    )}
                  >
                    {contactFeedback}
                  </p>
                ) : null}
              </div>
            </div>
            <div className="bg-[#f9fafb] px-6 py-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setIsContactOpen(false);
                  setContactFeedback("");
                  setContactFeedbackTone("");
                }}
                className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmitContact}
                disabled={isContactSubmitting}
                className="px-4 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all shadow-sm disabled:opacity-45"
              >
                Send Message
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {authMode ? (
        <div
          className="fixed inset-0 z-[120] flex items-center justify-center bg-[#111827]/60 p-4"
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
                  <div className="flex justify-end gap-3 border-t border-[#e5e7eb] bg-[#f9fafb] p-3">
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
                    {authFeedback ? <p className="text-xs text-[#6b7280]">{authFeedback}</p> : null}
                  </div>
                  <div className="flex justify-end gap-3 border-t border-[#e5e7eb] bg-[#f9fafb] p-3">
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

      {isUpgradePlanOpen ? (
        <div
          className="fixed inset-0 z-[110] flex items-center justify-center bg-[#111827]/60 p-4"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              closeUpgradePlanModal();
            }
          }}
        >
          <div className="w-full max-w-md overflow-hidden rounded-md-ds border border-[#e5e7eb] bg-white shadow-2xl">
            <div className="px-6 py-5 border-b border-[#e5e7eb] bg-[#f9fafb]">
              <h3 className="text-lg font-bold text-[#111827]">Project limit reached</h3>
              <p className="text-sm text-[#6b7280]">
                You have reached your plan&apos;s project limit. Upgrade to add another project.
              </p>
            </div>
            <div className="p-6">
              <div className="border rounded-sm-ds border-[#e5e7eb] p-4">
                <p className="text-xs font-mono text-[#6b7280] uppercase tracking-wide">
                  {PROJECT_UPGRADE_PLAN.title}
                </p>
                <p className="mt-1 text-lg font-bold text-[#111827]">{PROJECT_UPGRADE_PLAN.name}</p>
                <p className="mt-2 text-sm text-[#6b7280]">{PROJECT_UPGRADE_PLAN.description}</p>
              </div>

              {upgradePlanFeedback ? (
                <p className="mt-3 text-xs text-[#dc2626]">{upgradePlanFeedback}</p>
              ) : null}
            </div>
            <div className="bg-[#f9fafb] px-6 py-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={closeUpgradePlanModal}
                className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
              >
                Maybe later
              </button>
              <button
                type="button"
                onClick={handleUpgradePlan}
                disabled={isUpgradePlanSubmitting}
                className="px-4 py-2 bg-[#06B6D4] text-white text-sm font-bold rounded-sm-ds hover:bg-cyan-600 transition-all shadow-sm disabled:opacity-45"
              >
                {isUpgradePlanSubmitting ? "Please wait..." : PROJECT_UPGRADE_PLAN.cta}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {isDeleteModalOpen ? (
        <div
          className="fixed inset-0 bg-[#111827]/60 backdrop-blur-[2px] z-[100] flex items-center justify-center p-4"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setIsDeleteModalOpen(false);
            }
          }}
        >
          <div className="bg-white rounded-md-ds shadow-2xl max-w-md w-full overflow-hidden">
            <div className="p-6">
              <div className="w-12 h-12 bg-rose-100 rounded-full flex items-center justify-center text-[#dc2626] mb-4">
                <AlertTriangle size={24} />
              </div>

              <h3 className="text-lg font-bold text-[#111827] mb-2">Are you absolutely sure?</h3>
              <p className="text-sm text-[#6b7280] mb-6">
                This action cannot be undone. This will permanently delete the
                <span className="font-mono font-bold text-[#111827]"> {selectedProject?.slug || "project"}</span>
                project and all associated data.
              </p>
              <div className="space-y-3">
                <p className="text-[10px] font-mono font-bold text-[#6b7280] uppercase">
                  Type project slug to confirm
                </p>
                <input
                  type="text"
                  value={deleteSlugConfirm}
                  onChange={(event) => setDeleteSlugConfirm(event.target.value)}
                  placeholder={selectedProject?.slug || "project-slug"}
                  className="w-full px-3 py-2 border border-[#e5e7eb] rounded-sm-ds text-sm focus:ring-1 focus:ring-red-500 outline-none"
                />
              </div>
            </div>
            <div className="bg-[#f9fafb] px-6 py-4 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(false)}
                className="px-4 py-2 text-sm font-bold text-[#6b7280] hover:text-[#111827]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteProject}
                disabled={
                  !selectedProject ||
                  !isOwnerViewer ||
                  isProjectDeleting ||
                  deleteSlugConfirm.trim() !== selectedProject.slug
                }
                className="px-4 py-2 bg-[#dc2626] text-white text-sm font-bold rounded-sm-ds hover:bg-red-700 transition-all disabled:opacity-45"
              >
                {isProjectDeleting ? "Deleting..." : "Confirm Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

    </div>
  );
}
