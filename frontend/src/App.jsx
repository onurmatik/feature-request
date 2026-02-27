/* global __FR_ADMIN_PATH__ */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  ThumbsUp,
  Copy,
  Folder,
  KeyRound,
  MessageCircle,
  LayoutDashboard,
  ListTodo,
  LogOut,
  ExternalLink,
  Plus,
  Search,
  ChevronDown,
  Settings,
} from "lucide-react";
import AuthModal from "./components/AuthModal.jsx";
import { authSignInEndpoint, csrfTokenFromCookie, getPostAuthRedirect } from "./utils/authClient.js";

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
const APP_NAME = "Feature Request";
const APP_BASE_DESCRIPTION =
  "Feature Request helps you collect, prioritize, and manage feedback, feature requests, and bug reports for your projects.";

const PROJECT_UPGRADE_PLAN = {
  id: "pro_30",
  title: "Growth",
  name: "Pro",
  description: "$3/mo for up to 30 projects",
  cta: "Upgrade",
};
const FEATURE_REQUEST_SKILL_PATH = ".agents/skills/feature-request/SKILL.md";

function cls(...values) {
  return values.filter(Boolean).join(" ");
}

function UserAvatar({
  imageUrl,
  label,
  sizeClass = "w-8 h-8",
  fallbackClassName = "bg-cyan-50 border border-cyan-100 text-[#06B6D4]",
  fallbackTextClassName = "text-[10px] font-bold",
  imageClassName = "rounded-full border border-cyan-100 object-cover",
}) {
  const safeLabel = String(label || "").trim();
  const fallback = safeLabel.slice(0, 2).toUpperCase() || "??";
  const safeImageUrl = String(imageUrl || "").trim();

  if (!safeImageUrl) {
    return (
      <div
        className={cls(
          sizeClass,
          "rounded-full flex items-center justify-center shrink-0",
          fallbackClassName,
          fallbackTextClassName,
        )}
      >
        {fallback}
      </div>
    );
  }

  return (
    <img
      src={safeImageUrl}
      alt={`${safeLabel || "user"} avatar`}
      className={cls(sizeClass, "rounded-full object-cover shrink-0", imageClassName)}
    />
  );
}

function SidebarProjectsHeader({ title, isOwnerViewer, ownerHandle, onCreateProject, onContactOwner }) {
  return (
    <div className="px-3 pb-2 flex items-center justify-between relative">
      <h3 className="text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider">{title}</h3>
      {isOwnerViewer ? (
        <button
          type="button"
          onClick={onCreateProject}
          className="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors"
          aria-label="Add new project"
          title="Add new project"
        >
          <Plus size={14} />
        </button>
      ) : ownerHandle ? (
        <button
          type="button"
          onClick={onContactOwner}
          className="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors"
          aria-label={`Contact @${ownerHandle}`}
          title={`Contact @${ownerHandle}`}
        >
          <MessageCircle size={14} />
        </button>
      ) : null}
      <span className="pointer-events-none absolute left-[-0.5rem] right-[-0.5rem] bottom-0 h-px bg-[#e5e7eb]" />
    </div>
  );
}

function ProfileMenu({
  menuRef,
  isOpen,
  onToggle,
  currentUserHandle,
  currentUserAvatarUrl,
  canCreateProject,
  onCreateProject,
  onClose,
  onLogout,
}) {
  const handleMenuClose = typeof onClose === "function" ? onClose : () => {};
  const dashboardHandle = String(currentUserHandle || "").trim();
  const dashboardUrl = dashboardHandle ? `/${dashboardHandle.toLowerCase()}` : "";

  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-2 rounded-sm-ds border border-transparent px-2 py-1 transition-colors hover:border-[#e5e7eb] hover:bg-[#f8fafc]"
      >
        <span className="text-xs font-mono text-[#6b7280]">{currentUserHandle || "user"}</span>
        <UserAvatar
          imageUrl={currentUserAvatarUrl}
          label={currentUserHandle || "user"}
          sizeClass="w-8 h-8"
        />
        <ChevronDown size={14} className="text-[#6b7280]" />
      </button>

      {isOpen ? (
        <div className="absolute right-0 top-full mt-2 w-44 rounded-sm-ds border border-[#e5e7eb] bg-white shadow-sm overflow-hidden z-50">
          {dashboardUrl ? (
            <a
              href={dashboardUrl}
              onClick={handleMenuClose}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
            >
              <LayoutDashboard size={16} />
              Dashboard
            </a>
          ) : null}
          {dashboardUrl ? <div className="h-px bg-[#e5e7eb] my-1" /> : null}
          <div className="px-3 pt-2 pb-1">
            <p className="text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider">settings</p>
          </div>
          <a
            href="/settings/api"
            onClick={handleMenuClose}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
          >
            <KeyRound size={16} />
            API Access
          </a>
          <a
            href="/settings/connect-agent"
            onClick={handleMenuClose}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
          >
            <Bot size={16} />
            Agent Integration
          </a>
          <div className="h-px bg-[#e5e7eb] my-1" />
          <a
            href="/messages"
            onClick={handleMenuClose}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
          >
            <MessageCircle size={16} />
            Messages
          </a>
          {canCreateProject ? (
            <button
              type="button"
              onClick={onCreateProject}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
            >
              <Plus size={16} />
              New Project
            </button>
          ) : null}
          <div className="h-px bg-[#e5e7eb] my-1" />
          <button
            type="button"
            onClick={onLogout}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm text-[#111827] hover:bg-[#f3f4f6]"
          >
            <LogOut size={16} />
            Logout
          </button>
        </div>
      ) : null}
    </div>
  );
}

function normalizeHandle(value) {
  return String(value || "").trim().toLowerCase();
}

const HANDLE_REGEX = /^[a-z0-9_]+$/;
const NOT_FOUND_ERROR_CODE = "route_not_found";
const ADMIN_PATH = (() => {
  const raw = typeof __FR_ADMIN_PATH__ === "string" ? __FR_ADMIN_PATH__ : "/admin/";
  const segment = String(raw || "").trim().replace(/^\/+|\/+$/g, "");
  return segment ? `/${segment}/` : "/admin/";
})();
const ADMIN_PATH_PARTS = ADMIN_PATH.split("/").filter(Boolean).map((segment) => normalizeHandle(segment));
const RESERVED_HANDLES = new Set(["messages", "settings", ADMIN_PATH_PARTS[0]].filter(Boolean));
const SETTINGS_SECTIONS = new Set(["general", "api", "connect-agent"]);

function settingsSectionToView(section) {
  if (section === "api") {
    return "settingsApi";
  }
  if (section === "connect-agent") {
    return "settingsConnectAgent";
  }
  return "settingsGeneral";
}

function agentTokenStorageKey(handle) {
  const normalized = normalizeHandle(handle || "anonymous");
  return `fr_agent_token_secret:${normalized}`;
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
    // ignore storage failures
  }
}

function buildAgentPromptText(baseUrl, tokenValue) {
  const baseOrigin = String(baseUrl || "").replace(/\/+$/, "");
  const skillCatalogUrl = `${baseOrigin}/${FEATURE_REQUEST_SKILL_PATH}`;
  return [
    "Please manage the projects and requests using FeatureRequest skill as requested.",
    "",
    `API token: ${tokenValue}`,
    "",
    `If no skill added yet, read from ${skillCatalogUrl}`,
  ].join("\n");
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

function createNotFoundError(message = "Page not found.") {
  const error = new Error(message);
  error.code = NOT_FOUND_ERROR_CODE;
  return error;
}

function isNotFoundError(error) {
  return error instanceof Error && error.code === NOT_FOUND_ERROR_CODE;
}

function parseRoute(pathname = window.location.pathname) {
  const pathParts = String(pathname || "").split("/").filter(Boolean);
  if (!pathParts.length) {
    return { kind: "notFound" };
  }

  const first = normalizeHandle(pathParts[0]);
  if (first === "messages") {
    if (pathParts.length > 2) {
      return { kind: "notFound" };
    }

    const selectedMessageHandle = normalizeHandle(pathParts[1] || "");
    if (selectedMessageHandle && (!isValidHandle(selectedMessageHandle) || isReservedHandle(selectedMessageHandle))) {
      return { kind: "notFound" };
    }

    return {
      kind: "messages",
      selectedMessageHandle,
    };
  }

  if (first === "settings") {
    if (pathParts.length === 1) {
      return {
        kind: "settings",
        section: "general",
      };
    }

    if (pathParts.length === 2 && SETTINGS_SECTIONS.has(normalizeHandle(pathParts[1]))) {
      return {
        kind: "settings",
        section: normalizeHandle(pathParts[1]),
      };
    }

    return { kind: "notFound" };
  }

  if (isAdminRoute(pathname)) {
    return { kind: "reserved" };
  }

  if (!isValidHandle(first) || isReservedHandle(first)) {
    return { kind: "notFound" };
  }

  if (pathParts.length === 1) {
    return {
      kind: "board",
      ownerHandle: first,
      projectSlug: "",
      isProjectFormRoute: false,
    };
  }

  if (pathParts.length === 2) {
    return {
      kind: "board",
      ownerHandle: first,
      projectSlug: String(pathParts[1] || ""),
      isProjectFormRoute: false,
    };
  }

  if (pathParts.length === 3 && pathParts[1] === "projects" && pathParts[2] === "new") {
    return {
      kind: "board",
      ownerHandle: first,
      projectSlug: "",
      isProjectFormRoute: true,
    };
  }

  return { kind: "notFound" };
}

function getMessagesRouteState(pathname = window.location.pathname) {
  const route = parseRoute(pathname);
  const isMessagesRoute = route.kind === "messages";
  return {
    isMessagesRoute,
    selectedMessageHandle: isMessagesRoute ? route.selectedMessageHandle : "",
  };
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

function parseBootstrap() {
  const value = window.__FR_BOOTSTRAP__ || {};
  const route = parseRoute();
  const isMessagesRoute = route.kind === "messages";
  const isBoardRoute = route.kind === "board";
  const isSettingsRoute = route.kind === "settings";
  const initialProjectSlug =
    isBoardRoute && !route.isProjectFormRoute
      ? String(value.initialProjectSlug || route.projectSlug || "")
      : "";

  return {
    ownerHandle: isBoardRoute ? normalizeHandle(value.ownerHandle || route.ownerHandle) : "",
    initialProjectSlug,
    initialView: isMessagesRoute
      ? "messages"
      : isSettingsRoute
        ? settingsSectionToView(route.section)
        : isBoardRoute && route.isProjectFormRoute
          ? "newProject"
          : "issues",
    initialMessageThreadId: messageThreadIdFromHandle(isMessagesRoute ? route.selectedMessageHandle : ""),
    isProjectFormRoute: isBoardRoute ? route.isProjectFormRoute : false,
    isNotFoundRoute: route.kind === "notFound" || route.kind === "reserved",
    isAuthenticated: Boolean(value.isAuthenticated),
    currentUserHandle: String(value.currentUserHandle || "").trim(),
    currentUserAvatarUrl: String(value.currentUserAvatarUrl || "").trim(),
    subscriptionTier: String(value.subscription_tier || "free").toLowerCase(),
    subscriptionStatus: String(value.subscription_status || "").toLowerCase(),
    projectLimit: Number(value.project_limit || 1),
  };
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

function toReadablePriority(priority) {
  const map = {
    1: "Low",
    2: "Medium",
    3: "High",
    4: "Critical",
  };

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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function parseInlineMarkdown(line) {
  const safeLine = escapeHtml(line);
  const pattern = /\*\*([^\*\n]+)\*\*|__([^_\n]+)__|`([^`\n]+)`|~~([^~\n]+)~~|\[([^\]\n]+)\]\(([^)\n]+)\)|\*([^*\n]+)\*|_([^_\n]+)_/g;

  const elements = [];
  let cursor = 0;
  let match;
  let index = 0;

  while ((match = pattern.exec(safeLine)) !== null) {
    if (match.index > cursor) {
      elements.push(safeLine.slice(cursor, match.index));
    }

    if (match[1] || match[2]) {
      elements.push(<strong key={`markdown-strong-${index++}`}>{match[1] || match[2]}</strong>);
    } else if (match[3]) {
      elements.push(<code key={`markdown-code-${index++}`}>{match[3]}</code>);
    } else if (match[4]) {
      elements.push(<del key={`markdown-del-${index++}`}>{match[4]}</del>);
    } else if (match[5] && match[6]) {
      const href = String(match[6]).trim();
      const isSafeUrl = href.startsWith("http://") || href.startsWith("https://") || href.startsWith("/");
      const safeHref = isSafeUrl ? href : "#";

      elements.push(
        <a
          key={`markdown-link-${index++}`}
          href={safeHref}
          target={safeHref.startsWith("http") ? "_blank" : undefined}
          rel={safeHref.startsWith("http") ? "noopener noreferrer" : undefined}
          className="text-[#06B6D4] underline underline-offset-2"
        >
          {match[5]}
        </a>,
      );
    } else if (match[7] || match[8]) {
      elements.push(<em key={`markdown-em-${index++}`}>{match[7] || match[8]}</em>);
    }

    cursor = pattern.lastIndex;
  }

  if (cursor < safeLine.length) {
    elements.push(safeLine.slice(cursor));
  }

  return elements;
}

function parseMarkdownBlocks(value) {
  const lines = String(value || "").replaceAll("\r\n", "\n").split("\n");
  const blocks = [];
  let paragraphLines = [];
  let listContext = null;

  function flushParagraph() {
    if (!paragraphLines.length) {
      return;
    }

    const blockIndex = blocks.length;
    const linesToRender = [...paragraphLines];
    paragraphLines = [];

    blocks.push(
      <p key={`markdown-paragraph-${blockIndex}`} className="mb-4 leading-relaxed">
        {linesToRender.map((line, lineIndex) => (
          <span key={`markdown-paragraph-line-${blockIndex}-${lineIndex}`} className={lineIndex ? "block mt-1" : "block"}>
            {parseInlineMarkdown(line)}
          </span>
        ))}
      </p>,
    );
  }

  function flushList() {
    if (!listContext || !listContext.items.length) {
      return;
    }

    const listIndex = blocks.length;
    const listItems = listContext.items.map((item, itemIndex) => (
      <li key={`markdown-list-item-${listIndex}-${itemIndex}`}>{parseInlineMarkdown(item)}</li>
    ));

    if (listContext.ordered) {
      blocks.push(
        <ol key={`markdown-ol-${listIndex}`} className="pl-5 mb-4 list-decimal space-y-2">
          {listItems}
        </ol>,
      );
    } else {
      blocks.push(
        <ul key={`markdown-ul-${listIndex}`} className="pl-5 mb-4 list-disc space-y-2">
          {listItems}
        </ul>,
      );
    }

    listContext = null;
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
        const codeLine = lines[i];
        if (codeLine.trim() === "```") {
          break;
        }
        codeLines.push(codeLine);
      }

      blocks.push(
        <pre
          key={`markdown-code-${blocks.length}`}
          className="bg-[#0b1220] text-[#e5e7eb] p-3 rounded-sm-ds mb-4 overflow-x-auto"
        >
          <code className="font-mono text-xs leading-relaxed">{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (headingMatch) {
      flushParagraph();
      flushList();

      const level = Math.min(headingMatch[1].length, 6);
      const text = headingMatch[2].trim();
      const HeadingTag = `h${level}`;

      blocks.push(
        <HeadingTag
          key={`markdown-heading-${blocks.length}`}
          className="font-bold text-[#111827] mt-1 mb-2 last:mb-0"
        >
          {parseInlineMarkdown(text)}
        </HeadingTag>,
      );
      continue;
    }

    if (unorderedListMatch || orderedListMatch) {
      if (!listContext || listContext.ordered !== Boolean(orderedListMatch)) {
        flushList();
        listContext = { ordered: Boolean(orderedListMatch), items: [] };
      }

      listContext.items.push(unorderedListMatch ? unorderedListMatch[1] : orderedListMatch[1]);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    paragraphLines.push(line);
  }

  flushParagraph();
  flushList();

  return blocks;
}

function MarkdownContent({ value, fallback }) {
  const content = String(value || "").trim();
  const fallbackText = String(fallback || "");

  if (!content) {
    return <p>{fallbackText}</p>;
  }

  try {
    return (
      <div className="prose prose-sm max-w-none space-y-1">
        {parseMarkdownBlocks(content)}
      </div>
    );
  } catch {
    return <p className="whitespace-pre-wrap text-[#6b7280]">{content}</p>;
  }
}

function ProjectSidebarIcon({ faviconUrl, projectName }) {
  const [isError, setIsError] = useState(false);

  if (!faviconUrl || isError) {
    return <Folder size={18} />;
  }

  return (
    <img
      src={faviconUrl}
      alt={`${projectName} icon`}
      onError={() => setIsError(true)}
      className="h-[18px] w-[18px] rounded-sm-ds object-contain bg-white border border-[#e5e7eb] shrink-0"
      referrerPolicy="no-referrer"
    />
  );
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

function safeEpoch(value) {
  const timestamp = Date.parse(String(value || ""));
  return Number.isFinite(timestamp) ? timestamp : 0;
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
  if (thread.correspondentHandle) {
    return `@${thread.correspondentHandle}`;
  }

  if (thread.correspondentName) {
    return thread.correspondentName;
  }

  if (thread.correspondentEmail) {
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
    const email = threadId.replace("email:", "");
    return email || "Guest";
  }

  return "Guest";
}

function trimForPreview(value, maxLength = 100) {
  const text = String(value || "").trim();
  if (!text || text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength).trimEnd()}...`;
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
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(textarea);
    return copied;
  } catch {
    return false;
  }
}

function isProjectFormPath(ownerHandle) {
  const route = parseRoute();
  return route.kind === "board" && route.ownerHandle === normalizeHandle(ownerHandle) && route.isProjectFormRoute;
}

export default function App() {
  const bootstrap = useMemo(parseBootstrap, []);

  const [projects, setProjects] = useState([]);
  const [issues, setIssues] = useState([]);
  const [selectedProjectSlug, setSelectedProjectSlug] = useState(bootstrap.initialProjectSlug || "");
  const [selectedIssueId, setSelectedIssueId] = useState(null);

  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("open");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const [statusLine, setStatusLine] = useState("");
  const [statusError, setStatusError] = useState(false);

  const [view, setView] = useState(bootstrap.initialView);
  const [isRouteNotFound, setIsRouteNotFound] = useState(Boolean(bootstrap.isNotFoundRoute));

  const [comments, setComments] = useState([]);
  const [commentDraft, setCommentDraft] = useState("");
  const [commentFeedback, setCommentFeedback] = useState("");
  const [isCommentSubmitting, setIsCommentSubmitting] = useState(false);
  const [isIssueUpdating, setIsIssueUpdating] = useState(false);
  const [messages, setMessages] = useState([]);
  const [isMessagesLoading, setIsMessagesLoading] = useState(false);
  const [selectedMessageThreadId, setSelectedMessageThreadId] = useState(
    bootstrap.initialMessageThreadId || "",
  );
  const [messageSidebarProjects, setMessageSidebarProjects] = useState([]);
  const [isMessageSidebarProjectsLoading, setIsMessageSidebarProjectsLoading] = useState(false);
  const [messageComposerBody, setMessageComposerBody] = useState("");
  const [messageComposerFeedback, setMessageComposerFeedback] = useState("");
  const [messageComposerFeedbackTone, setMessageComposerFeedbackTone] = useState("");
  const [isMessageComposerSubmitting, setIsMessageComposerSubmitting] = useState(false);
  const [apiTokens, setApiTokens] = useState([]);
  const [apiTokenSecrets, setApiTokenSecrets] = useState({});
  const [isApiTokensLoading, setIsApiTokensLoading] = useState(false);
  const [apiTokenFeedback, setApiTokenFeedback] = useState("");
  const [apiTokenFeedbackTone, setApiTokenFeedbackTone] = useState("");
  const [agentPromptCopyFeedback, setAgentPromptCopyFeedback] = useState("");
  const [agentPromptCopyFeedbackTone, setAgentPromptCopyFeedbackTone] = useState("");
  const [latestCreatedTokenValue, setLatestCreatedTokenValue] = useState("");
  const [agentPromptValue, setAgentPromptValue] = useState("");
  const [isAgentRefreshSubmitting, setIsAgentRefreshSubmitting] = useState(false);

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
  const [currentUserAvatarUrl, setCurrentUserAvatarUrl] = useState(bootstrap.currentUserAvatarUrl);
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
  const hasActivePaidPlan =
    projectLimitToUse > 1 || (subscriptionTier === "pro_30" && !subscriptionStatus);
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

  const messageThreads = useMemo(() => {
    const viewerHandle = normalizeHandle(currentUserHandle);
    const grouped = new Map();

    for (const message of messages) {
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

      existing.messages.push({
        ...message,
        isOutgoing,
      });
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

    const selectedHandle = getHandleFromThreadId(selectedMessageThreadId);
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
  }, [messages, currentUserHandle, selectedMessageThreadId]);

  const selectedMessageThread = useMemo(() => {
    if (!selectedMessageThreadId) {
      return null;
    }

    return messageThreads.find((thread) => thread.threadId === selectedMessageThreadId) || null;
  }, [messageThreads, selectedMessageThreadId]);

  const selectedMessageHandle = useMemo(() => {
    if (selectedMessageThread?.correspondentHandle) {
      return selectedMessageThread.correspondentHandle;
    }

    return getHandleFromThreadId(selectedMessageThreadId);
  }, [selectedMessageThread, selectedMessageThreadId]);

  const messageSidebarProjectsOwnerHandle = useMemo(() => {
    const routeState = getMessagesRouteState();
    const routeHandle = normalizeHandle(routeState.selectedMessageHandle || "");
    return routeHandle || normalizeHandle(currentUserHandle);
  }, [currentUserHandle, selectedMessageThreadId]);

  const sidebarProjectsOwnerHandle = useMemo(() => {
    if (view === "messages") {
      return normalizeHandle(messageSidebarProjectsOwnerHandle);
    }

    return normalizeHandle(bootstrap.ownerHandle);
  }, [bootstrap.ownerHandle, messageSidebarProjectsOwnerHandle, view]);

  const isSidebarOwnerViewer = useMemo(
    () =>
      isAuthenticated &&
      normalizeHandle(currentUserHandle) === sidebarProjectsOwnerHandle,
    [currentUserHandle, isAuthenticated, sidebarProjectsOwnerHandle],
  );
  const workspaceOwnerHandle =
    normalizeHandle(currentUserHandle) || normalizeHandle(bootstrap.ownerHandle);
  const canCreateWorkspaceProject = Boolean(isAuthenticated && workspaceOwnerHandle);
  const isGlobalSettingsView =
    view === "settingsGeneral" || view === "settingsApi" || view === "settingsConnectAgent";
  const isApiAccessView = view === "settingsApi";
  const isConnectAgentView = view === "settingsConnectAgent";
  const isSettingsGeneralView = view === "settingsGeneral";
  const apiBaseUrl = useMemo(() => window.location.origin.replace(/\/+$/, ""), []);
  const activeAgentToken = useMemo(
    () => (Array.isArray(apiTokens) && apiTokens.length ? apiTokens[0] : null),
    [apiTokens],
  );
  const activeAgentTokenSecret = activeAgentToken ? String(apiTokenSecrets[activeAgentToken.id] || "") : "";
  const visibleAgentTokenValue =
    activeAgentTokenSecret ||
    latestCreatedTokenValue ||
    (activeAgentToken ? `${activeAgentToken.token_prefix}••••••••` : "");
  const canCopyActiveAgentToken = Boolean(activeAgentTokenSecret);
  const promptTextValue =
    String(agentPromptValue || "").trim();

  useEffect(() => {
    setAgentPromptCopyFeedback("");
    setAgentPromptCopyFeedbackTone("");
  }, [promptTextValue]);

  const sidebarProjectsTitle = useMemo(() => {
    if (isSidebarOwnerViewer) {
      return "My projects";
    }

    if (sidebarProjectsOwnerHandle) {
      return `${sidebarProjectsOwnerHandle}'s projects`;
    }

    return "Projects";
  }, [isSidebarOwnerViewer, sidebarProjectsOwnerHandle]);

  const canSendDirectMessage = useMemo(() => {
    const correspondentHandle = normalizeHandle(selectedMessageHandle);
    return Boolean(
      isAuthenticated &&
      correspondentHandle &&
      correspondentHandle !== normalizeHandle(currentUserHandle),
    );
  }, [currentUserHandle, isAuthenticated, selectedMessageHandle]);

  const messagesNavbarHandle = normalizeHandle(getMessagesRouteState().selectedMessageHandle);

  useEffect(() => {
    if (selectedMessageThreadId || !messageThreads.length) {
      return;
    }

    setSelectedMessageThreadId(messageThreads[0].threadId);
  }, [messageThreads, selectedMessageThreadId]);

  useEffect(() => {
    setMessageComposerBody("");
    setMessageComposerFeedback("");
    setMessageComposerFeedbackTone("");
  }, [selectedMessageThreadId]);

  const pageTitle = useMemo(() => {
    if (isRouteNotFound) {
      return `404 | ${APP_NAME}`;
    }

    if (view === "settingsApi") {
      return `API Access | ${APP_NAME}`;
    }

    if (view === "settingsConnectAgent") {
      return `Connect Agent | ${APP_NAME}`;
    }

    if (view === "settingsGeneral") {
      return `Settings | ${APP_NAME}`;
    }

    if (view === "messages") {
      return `Messages | ${APP_NAME}`;
    }

    if (view === "projectSettings" && selectedProject?.name) {
      return `${selectedProject.name} Settings | ${APP_NAME}`;
    }

    if (view === "newProject") {
      return `New Project | ${APP_NAME}`;
    }

    if (selectedIssue?.title && selectedProject?.name) {
      return `${selectedIssue.title} - ${selectedProject.name} | ${APP_NAME}`;
    }

    if (selectedProject?.name) {
      return `${selectedProject.name} | ${APP_NAME}`;
    }

    if (bootstrap.ownerHandle && !selectedProjectSlug) {
      return `${bootstrap.ownerHandle}'s projects | ${APP_NAME}`;
    }

    if (selectedProjectSlug) {
      return `${selectedProjectSlug} | ${APP_NAME}`;
    }

    return APP_NAME;
  }, [bootstrap.ownerHandle, isRouteNotFound, selectedIssue?.title, selectedProject?.name, selectedProjectSlug, view]);

  const pageDescription = useMemo(() => {
    if (isRouteNotFound) {
      return "The requested page could not be found.";
    }

    if (view === "settingsApi") {
      return "Manage API bearer tokens and endpoint quickstart guides for agent integrations.";
    }

    if (view === "settingsConnectAgent") {
      return "Connect your agent, rotate token, and copy integration prompt.";
    }

    if (view === "settingsGeneral") {
      return "Manage global account settings for your workspace.";
    }

    if (view === "messages") {
      return "Review direct messages from people who contacted this board.";
    }

    if (view === "projectSettings" && selectedProject?.name) {
      return `Manage project settings for ${selectedProject.name} on ${APP_NAME}.`;
    }

    if (selectedIssue?.title && selectedProject?.name) {
      return `View discussion and details for "${selectedIssue.title}" in ${selectedProject.name} on ${APP_NAME}.`;
    }

    if (selectedProject?.name) {
      return `${selectedProject.name}: ${selectedProject.tagline || "Feature request board and bug tracker."}`;
    }

    if (bootstrap.ownerHandle) {
      return `${APP_NAME} board for ${bootstrap.ownerHandle} with public projects and requests.`;
    }

    return APP_BASE_DESCRIPTION;
  }, [
    bootstrap.ownerHandle,
    isRouteNotFound,
    selectedIssue?.title,
    selectedProject?.name,
    selectedProject?.tagline,
    view,
  ]);

  useEffect(() => {
    document.title = pageTitle;

    const descriptionMeta = document.querySelector('meta[name="description"]');
    const descriptionTag = descriptionMeta || document.createElement("meta");
    descriptionTag.setAttribute("name", "description");
    descriptionTag.setAttribute("content", pageDescription);
    if (!descriptionMeta) {
      document.head.appendChild(descriptionTag);
    }

    const ogTitleMeta = document.querySelector('meta[property="og:title"]');
    const ogTitleTag = ogTitleMeta || document.createElement("meta");
    ogTitleTag.setAttribute("property", "og:title");
    ogTitleTag.setAttribute("content", pageTitle);
    if (!ogTitleMeta) {
      document.head.appendChild(ogTitleTag);
    }

    const ogDescriptionMeta = document.querySelector('meta[property="og:description"]');
    const ogDescriptionTag = ogDescriptionMeta || document.createElement("meta");
    ogDescriptionTag.setAttribute("property", "og:description");
    ogDescriptionTag.setAttribute("content", pageDescription);
    if (!ogDescriptionMeta) {
      document.head.appendChild(ogDescriptionTag);
    }
  }, [pageTitle, pageDescription]);

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

  const messagesUrl = useCallback((handle = "") => {
    const normalized = normalizeHandle(handle);
    return normalized ? `/messages/${normalized}/` : "/messages/";
  }, []);

  const settingsUrl = useCallback((section = "general") => {
    if (section === "api") {
      return "/settings/api";
    }
    if (section === "connect-agent") {
      return "/settings/connect-agent";
    }
    return "/settings/";
  }, []);

  const setStatus = useCallback((text, isError = false) => {
    setStatusLine(text);
    setStatusError(isError);
  }, []);

  const refreshSession = useCallback(async () => {
    const response = await fetch("/auth/me");
    if (!response.ok) {
      setIsAuthenticated(false);
      setCurrentUserHandle("");
      setCurrentUserAvatarUrl("");
      setSubscriptionTier("free");
      setSubscriptionStatus("");
      setProjectLimit(1);
      return;
    }

    const data = await response.json();
    setIsAuthenticated(Boolean(data.is_authenticated));
    setCurrentUserHandle(String(data.current_user_handle || ""));
    setCurrentUserAvatarUrl(String(data.current_user_avatar_url || ""));
    setSubscriptionTier(String(data.subscription_tier || "free").toLowerCase());
    setSubscriptionStatus(String(data.subscription_status || "").toLowerCase());
    setProjectLimit(Number(data.project_limit || 1));
  }, []);

  const refreshMessages = useCallback(async () => {
    if (!isAuthenticated) {
      setMessages([]);
      return;
    }

    setIsMessagesLoading(true);
    try {
      const response = await fetch("/api/me/messages");
      if (!response.ok) {
        setMessages([]);
        setStatus("Messages could not be loaded.", true);
        return;
      }

      const data = await response.json();
      setMessages(data);
    } finally {
      setIsMessagesLoading(false);
    }
  }, [isAuthenticated, setStatus]);

  const refreshApiTokens = useCallback(async () => {
    if (!isAuthenticated) {
      setApiTokens([]);
      setLatestCreatedTokenValue("");
      setAgentPromptValue("");
      return;
    }

    setIsApiTokensLoading(true);
    try {
      const response = await fetch("/api/auth/agent-token");
      if (!response.ok) {
        setApiTokens([]);
        setApiTokenFeedback("API tokens could not be loaded.");
        setApiTokenFeedbackTone("error");
        return;
      }

      const data = await response.json();
      if (data && data.exists) {
        setApiTokens([
          {
            id: data.id,
            name: data.name,
            can_write: Boolean(data.can_write),
            token_prefix: data.token_prefix,
            created_at: data.created_at,
            last_used_at: data.last_used_at,
          },
        ]);
        const storedTokenValue = readStoredAgentToken(currentUserHandle);
        if (storedTokenValue && storedTokenValue.slice(0, 12) === String(data.token_prefix || "")) {
          setApiTokenSecrets((previous) => ({ ...previous, [data.id]: storedTokenValue }));
          setLatestCreatedTokenValue(storedTokenValue);
          setAgentPromptValue(buildAgentPromptText(apiBaseUrl, storedTokenValue));
        } else {
          await ensureCsrfCookie();
          const connectResponse = await fetch("/api/auth/agent-token/connect", {
            method: "POST",
            headers: {
              "X-CSRFToken": csrfTokenFromCookie(),
            },
          });
          const connectPayload = await connectResponse.json().catch(() => ({}));
          if (!connectResponse.ok) {
            setApiTokenFeedback("Agent token could not be loaded.");
            setApiTokenFeedbackTone("error");
            setLatestCreatedTokenValue("");
            setAgentPromptValue("");
            return;
          }

          const tokenRow = {
            id: connectPayload.id,
            name: connectPayload.name,
            can_write: Boolean(connectPayload.can_write),
            token_prefix: connectPayload.token_prefix,
            created_at: connectPayload.created_at,
            last_used_at: connectPayload.last_used_at,
          };
          const tokenValue = String(connectPayload.token || "");
          setApiTokens([tokenRow]);
          setLatestCreatedTokenValue(tokenValue);
          if (tokenValue) {
            writeStoredAgentToken(currentUserHandle, tokenValue);
            setApiTokenSecrets((previous) => ({ ...previous, [tokenRow.id]: tokenValue }));
            setAgentPromptValue(buildAgentPromptText(apiBaseUrl, tokenValue));
          } else {
            setAgentPromptValue("");
          }
        }
      } else {
        await ensureCsrfCookie();
        const connectResponse = await fetch("/api/auth/agent-token/connect", {
          method: "POST",
          headers: {
            "X-CSRFToken": csrfTokenFromCookie(),
          },
        });
        const connectPayload = await connectResponse.json().catch(() => ({}));
        if (!connectResponse.ok) {
          setApiTokens([]);
          const detail =
            typeof connectPayload.detail === "string"
              ? connectPayload.detail
              : "Agent token could not be created.";
          setApiTokenFeedback(detail);
          setApiTokenFeedbackTone("error");
          return;
        }

        const tokenRow = {
          id: connectPayload.id,
          name: connectPayload.name,
          can_write: Boolean(connectPayload.can_write),
          token_prefix: connectPayload.token_prefix,
          created_at: connectPayload.created_at,
          last_used_at: connectPayload.last_used_at,
        };
        const tokenValue = String(connectPayload.token || "");
        setApiTokens([tokenRow]);
        setLatestCreatedTokenValue(tokenValue);
        if (tokenValue) {
          writeStoredAgentToken(currentUserHandle, tokenValue);
          setApiTokenSecrets((previous) => ({ ...previous, [tokenRow.id]: tokenValue }));
          setAgentPromptValue(buildAgentPromptText(apiBaseUrl, tokenValue));
        } else {
          setAgentPromptValue("");
        }
        setApiTokenFeedback("");
        setApiTokenFeedbackTone("");
      }
      if (data && data.exists) {
        setApiTokenFeedback("");
        setApiTokenFeedbackTone("");
      }
    } finally {
      setIsApiTokensLoading(false);
    }
  }, [apiBaseUrl, currentUserHandle, isAuthenticated]);

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
      const routeState = getMessagesRouteState();
      const response = await fetch(authSignInEndpoint({ useCurrentPathAsNext: routeState.isMessagesRoute }), {
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
      setCurrentUserAvatarUrl(String(payload.current_user_avatar_url || ""));
      setSubscriptionTier(String(payload.subscription_tier || "free").toLowerCase());
      setSubscriptionStatus(String(payload.subscription_status || "").toLowerCase());
      setProjectLimit(Number(payload.project_limit || 1));
      window.location.assign(
        getPostAuthRedirect(handle, { useCurrentPathAsFallback: routeState.isMessagesRoute }),
      );
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
    setCurrentUserAvatarUrl("");
    setSubscriptionTier("free");
    setSubscriptionStatus("");
    setProjectLimit(1);
    setAuthMode(null);
    setMessages([]);
    setSelectedMessageThreadId("");
    setIsMessagesLoading(false);
    setMessageSidebarProjects([]);
    setIsMessageSidebarProjectsLoading(false);
    window.location.assign("/");
  }

  const refreshProjects = useCallback(async () => {
    if (!bootstrap.ownerHandle) {
      throw new Error("Owner handle is missing in URL.");
    }

    const response = await fetch(`/api/owners/${encodeURIComponent(bootstrap.ownerHandle)}/projects`);
    if (response.status === 404) {
      throw createNotFoundError("Board could not be found.");
    }
    if (!response.ok) {
      throw new Error("Projects could not be loaded.");
    }

    const data = await response.json();
    const route = parseRoute();
    if (
      route.kind === "board" &&
      route.ownerHandle === bootstrap.ownerHandle &&
      route.projectSlug &&
      !route.isProjectFormRoute &&
      !data.some((project) => project.slug === route.projectSlug)
    ) {
      throw createNotFoundError("Project could not be found.");
    }

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

    if (response.status === 404) {
      setIssues([]);
      setIsRouteNotFound(true);
      return;
    }

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
      setCurrentUserAvatarUrl("");
      setMessages([]);
      setSelectedMessageThreadId("");
      setIsMessagesLoading(false);
      setMessageSidebarProjects([]);
      setIsMessageSidebarProjectsLoading(false);
    });
  }, [refreshSession]);

  useEffect(() => {
    if (view !== "messages") {
      return;
    }

    if (!isAuthenticated) {
      return;
    }

    refreshMessages().catch(() => {
      setStatus("Messages could not be loaded.", true);
    });
  }, [isAuthenticated, refreshMessages, setStatus, view]);

  useEffect(() => {
    if (!isApiAccessView && !isConnectAgentView) {
      return;
    }

    if (!isAuthenticated) {
      setApiTokens([]);
      setApiTokenFeedback("");
      setApiTokenFeedbackTone("");
      setAgentPromptValue("");
      return;
    }

    refreshApiTokens().catch(() => {
      setApiTokenFeedback("API tokens could not be loaded.");
      setApiTokenFeedbackTone("error");
    });
  }, [isApiAccessView, isAuthenticated, isConnectAgentView, refreshApiTokens]);

  useEffect(() => {
    if (view !== "messages") {
      return;
    }

    if (!messageSidebarProjectsOwnerHandle) {
      setMessageSidebarProjects([]);
      setIsMessageSidebarProjectsLoading(false);
      return;
    }

    let cancelled = false;
    setIsMessageSidebarProjectsLoading(true);

    async function loadMessageSidebarProjects() {
      try {
        const response = await fetch(
          `/api/owners/${encodeURIComponent(messageSidebarProjectsOwnerHandle)}/projects`,
        );

        if (!response.ok) {
          if (!cancelled) {
            setMessageSidebarProjects([]);
          }
          return;
        }

        const data = await response.json();
        if (!cancelled) {
          setMessageSidebarProjects(Array.isArray(data) ? data : []);
        }
      } catch {
        if (!cancelled) {
          setMessageSidebarProjects([]);
        }
      } finally {
        if (!cancelled) {
          setIsMessageSidebarProjectsLoading(false);
        }
      }
    }

    loadMessageSidebarProjects();
    return () => {
      cancelled = true;
    };
  }, [messageSidebarProjectsOwnerHandle, view]);

  useEffect(() => {
    if (!bootstrap.ownerHandle) {
      return;
    }

    let cancelled = false;
    setIsRouteNotFound(false);

    async function boot() {
      try {
        await refreshProjects();
        if (!cancelled) {
          await refreshIssues();
          setIsRouteNotFound(false);
        }
      } catch (error) {
        if (!cancelled) {
          if (isNotFoundError(error)) {
            setIsRouteNotFound(true);
            return;
          }
          setStatus(error instanceof Error ? error.message : "Board could not be loaded.", true);
        }
      }
    }

    boot();

    return () => {
      cancelled = true;
    };
  }, [bootstrap.ownerHandle, refreshProjects, refreshIssues, setStatus]);

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
    if (isRouteNotFound || !bootstrap.ownerHandle) {
      return;
    }

    refreshIssues().catch(() => {
      setStatus("Requests could not be loaded.", true);
    });
  }, [bootstrap.ownerHandle, isRouteNotFound, refreshIssues, setStatus]);

  useEffect(() => {
    if (!selectedIssue?.id) {
      setComments([]);
      setCommentFeedback("");
      return;
    }

    refreshComments(selectedIssue.id).catch(() => {
      setComments([]);
    });
  }, [selectedIssue?.id, refreshComments]);

  useEffect(() => {
    function onPopState() {
      const route = parseRoute();
      if (route.kind === "messages") {
        setIsRouteNotFound(false);
        setView("messages");
        setSelectedMessageThreadId(messageThreadIdFromHandle(route.selectedMessageHandle));
        return;
      }

      if (route.kind === "board" && route.ownerHandle === bootstrap.ownerHandle) {
        setIsRouteNotFound(false);
        setView(route.isProjectFormRoute ? "newProject" : "issues");
        setSelectedProjectSlug(route.isProjectFormRoute ? "" : route.projectSlug || "");
        return;
      }

      if (route.kind === "settings") {
        setIsRouteNotFound(false);
        setView(settingsSectionToView(route.section));
        return;
      }

      if (route.kind === "board" && route.ownerHandle !== bootstrap.ownerHandle) {
        window.location.assign(`${window.location.pathname}${window.location.search}${window.location.hash}`);
        return;
      }

      setIsRouteNotFound(true);
    }

    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
    };
  }, [bootstrap.ownerHandle]);

  useEffect(() => {
    if (!bootstrap.ownerHandle) {
      return;
    }

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
  }, [bootstrap.ownerHandle, boardUrl, isRouteNotFound, shouldShowUpgradeForProjects]);

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

  function setSettingsSectionAndHistory(section, replaceHistory = false) {
    const normalizedSection = SETTINGS_SECTIONS.has(section) ? section : "general";
    const nextView = settingsSectionToView(normalizedSection);
    setView(nextView);

    const nextUrl = settingsUrl(normalizedSection);
    if (window.location.pathname !== nextUrl) {
      const historyMethod = replaceHistory ? "replaceState" : "pushState";
      window.history[historyMethod]({ view: nextView }, "", nextUrl);
    }
  }

  function setProjectSlugAndHistory(nextSlug) {
    setView("issues");
    setSelectedProjectSlug(nextSlug);

    const url = boardUrl(nextSlug);
    if (window.location.pathname !== url) {
      window.history.pushState({ slug: nextSlug }, "", url);
    }
  }

  function setMessagesThreadAndHistory(nextThreadId, replaceHistory = false) {
    const normalizedThreadId = String(nextThreadId || "");
    const targetHandle = getHandleFromThreadId(normalizedThreadId);
    setView("messages");
    setSelectedMessageThreadId(normalizedThreadId);
    const nextUrl = messagesUrl(targetHandle);
    if (window.location.pathname !== nextUrl) {
      const historyMethod = replaceHistory ? "replaceState" : "pushState";
      window.history[historyMethod](
        { view: "messages", selectedMessageHandle: targetHandle },
        "",
        nextUrl,
      );
    }
  }

  function openProjectFormForHandle(handle) {
    const ownerHandle = normalizeHandle(handle);
    if (!ownerHandle) {
      return;
    }

    const targetUrl = `/${ownerHandle}/projects/new/`;
    if (ownerHandle !== normalizeHandle(bootstrap.ownerHandle)) {
      window.location.assign(targetUrl);
      return;
    }

    if (shouldShowUpgradeForProjects) {
      openUpgradePlanModal();
      return;
    }

    setProjectNameDraft("");
    setProjectTaglineDraft("");
    setProjectUrlDraft("");
    setNewProjectFeedback("");
    setNewProjectFeedbackTone("");
    setView("newProject");
    if (window.location.pathname !== targetUrl) {
      window.history.pushState({ slug: "projects", isProjectForm: true }, "", targetUrl);
    }
  }

  function openMessagesForContactHandle(handle) {
    const ownerHandle = normalizeHandle(handle);
    if (!ownerHandle) {
      return;
    }

    setMessagesThreadAndHistory(messageThreadIdFromHandle(ownerHandle));
    if (!isAuthenticated) {
      return;
    }

    refreshMessages().catch(() => {
      setStatus("Messages could not be loaded.", true);
    });
  }

  function openMessagesForOwnerContact() {
    openMessagesForContactHandle(bootstrap.ownerHandle);
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
      setCommentFeedback("Please log in to post a comment.");
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
    setCommentFeedback("");

    try {
      const response = await fetch(`/api/issues/${selectedIssue.id}/comments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({ body }),
      });

      const responsePayload = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail =
          typeof responsePayload.detail === "string"
            ? responsePayload.detail
            : "Comment could not be posted.";
        setCommentFeedback(detail);
        return;
      }

      const created = responsePayload;
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

  async function handleSendDirectMessage() {
    if (!isAuthenticated) {
      openAuth("signIn");
      return;
    }

    const correspondentHandle = normalizeHandle(selectedMessageHandle);
    if (!correspondentHandle) {
      setMessageComposerFeedback("Select a user to start a conversation.");
      setMessageComposerFeedbackTone("error");
      return;
    }

    if (correspondentHandle === normalizeHandle(currentUserHandle)) {
      setMessageComposerFeedback("You cannot message yourself.");
      setMessageComposerFeedbackTone("error");
      return;
    }

    const body = messageComposerBody.trim();
    if (!body) {
      setMessageComposerFeedback("Message body is required.");
      setMessageComposerFeedbackTone("error");
      return;
    }

    setIsMessageComposerSubmitting(true);
    setMessageComposerFeedback("Sending...");
    setMessageComposerFeedbackTone("");

    try {
      const response = await fetch(`/api/owners/${encodeURIComponent(correspondentHandle)}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfTokenFromCookie(),
        },
        body: JSON.stringify({
          body,
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Message could not be sent.";
        setMessageComposerFeedback(detail);
        setMessageComposerFeedbackTone("error");
        return;
      }

      setMessageComposerBody("");
      setMessageComposerFeedback("Message sent.");
      setMessageComposerFeedbackTone("success");
      setMessagesThreadAndHistory(messageThreadIdFromHandle(correspondentHandle), true);
      await refreshMessages();
    } finally {
      setIsMessageComposerSubmitting(false);
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

  function handleProfileProjectCreation() {
    setIsProfileMenuOpen(false);
    if (!workspaceOwnerHandle) {
      return;
    }
    openProjectFormForHandle(workspaceOwnerHandle);
  }

  function handleProjectFormNavigation(event) {
    event.preventDefault();
    openProjectFormForHandle(bootstrap.ownerHandle);
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
    if (!isAuthenticated) {
      setNewIssueFeedback("Please log in to create a request.");
      return;
    }

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

      await Promise.all([refreshIssues(), refreshProjects()]);
      setSelectedIssueId(data.id);
      setStatus("Request created.");
    } finally {
      setIsNewIssueSubmitting(false);
    }
  }

  async function handleRefreshAgentToken() {
    if (!isAuthenticated) {
      openAuth("signIn");
      return;
    }

    setIsAgentRefreshSubmitting(true);
    setApiTokenFeedback("");
    setApiTokenFeedbackTone("");

    try {
      await ensureCsrfCookie();
      const response = await fetch("/api/auth/agent-token/refresh", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfTokenFromCookie(),
        },
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string" ? data.detail : "Token refresh failed.";
        setApiTokenFeedback(detail);
        setApiTokenFeedbackTone("error");
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
      setApiTokens([tokenRow]);
      if (tokenValue) {
        writeStoredAgentToken(currentUserHandle, tokenValue);
        setApiTokenSecrets((previous) => ({ ...previous, [tokenRow.id]: tokenValue }));
      }
      setLatestCreatedTokenValue(tokenValue);
      setAgentPromptValue(buildAgentPromptText(apiBaseUrl, tokenValue));
      setApiTokenFeedback("Agent token refreshed.");
      setApiTokenFeedbackTone("success");
    } finally {
      setIsAgentRefreshSubmitting(false);
    }
  }

  async function copyValueAndNotify(value, successText) {
    const copied = await copyToClipboard(value);
    if (!copied) {
      setApiTokenFeedback("Copy failed. Please copy manually.");
      setApiTokenFeedbackTone("error");
      return;
    }

    setApiTokenFeedback(successText);
    setApiTokenFeedbackTone("success");
  }

  async function handleCopyAgentPrompt() {
    const copied = await copyToClipboard(promptTextValue);
    if (!copied) {
      setAgentPromptCopyFeedback("Copy failed. Please copy manually.");
      setAgentPromptCopyFeedbackTone("error");
      return;
    }

    setAgentPromptCopyFeedback("Agent prompt copied.");
    setAgentPromptCopyFeedbackTone("success");
  }

  async function handleCopyApiToken(tokenId) {
    const tokenValue = apiTokenSecrets[tokenId];
    if (!tokenValue) {
      setApiTokenFeedback("Token value is only available after connect/refresh. Refresh token to copy.");
      setApiTokenFeedbackTone("error");
      return;
    }

    await copyValueAndNotify(tokenValue, "Token copied.");
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

  if (isRouteNotFound) {
    return (
      <div className="min-h-screen bg-[#f3f4f6] text-[#111827] flex items-center justify-center px-4">
        <div className="w-full max-w-lg rounded-md-ds border border-[#e5e7eb] bg-white p-8 shadow-sm">
          <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#6b7280]">404</p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight text-[#111827]">Page not found</h1>
          <p className="mt-3 text-sm text-[#6b7280]">
            The requested URL does not match a valid board or route.
          </p>
          <a
            href="/"
            className="mt-6 inline-flex items-center rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-black"
          >
            Go Home
          </a>
        </div>
      </div>
    );
  }

  function renderNoProjectsFound() {
    return <p className="px-3 text-xs text-[#6b7280]">No public projects found.</p>;
  }

  function renderBoardProjectsList() {
    if (!projects.length) {
      return renderNoProjectsFound();
    }

    return projects.map((project) => (
      <div key={project.id} className="relative">
        <button
          type="button"
          data-project={project.slug}
          onClick={() => setProjectSlugAndHistory(project.slug)}
          className={cls(
            "sidebar-project-btn w-full flex items-start gap-3 px-3 py-2 rounded-sm-ds font-medium text-sm transition-colors",
            selectedProjectSlug === project.slug
              ? "bg-cyan-50 text-[#06B6D4]"
              : "text-[#6b7280] hover:bg-[#f3f4f6]",
          )}
        >
          <ProjectSidebarIcon faviconUrl={project.favicon_url} projectName={project.name} />
          <span className="flex-1 min-w-0 text-left">
            <span className="block font-medium leading-tight pr-12 truncate">{project.name}</span>
            {getProjectListMetaText(project) ? (
              <span className="block w-full text-[11px] leading-tight text-[#6b7280] pt-2">
                {getProjectListMetaText(project)}
              </span>
            ) : null}
          </span>
        </button>
        <span className="absolute top-2 right-2 flex items-center gap-1">
          {isOwnerViewer ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setProjectSlugAndHistory(project.slug);
                setView("projectSettings");
              }}
              className="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors"
              title="Project Settings"
              aria-label={`Project settings for ${project.name}`}
            >
              <Settings size={16} />
            </button>
          ) : null}
          {project.url ? (
            <a
              href={project.url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
              className="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors"
              aria-label={`Open ${project.name} website`}
              title="Open project site"
            >
              <ExternalLink size={16} />
            </a>
          ) : null}
        </span>
      </div>
    ));
  }

  function renderBoardProjectsSection() {
    return (
      <div className="space-y-1">
        <SidebarProjectsHeader
          title={sidebarProjectsTitle}
          isOwnerViewer={isSidebarOwnerViewer}
          ownerHandle={sidebarProjectsOwnerHandle}
          onCreateProject={() => openProjectFormForHandle(sidebarProjectsOwnerHandle)}
          onContactOwner={() => openMessagesForContactHandle(sidebarProjectsOwnerHandle)}
        />
        {renderBoardProjectsList()}
      </div>
    );
  }

  const projectButtons = renderBoardProjectsSection();

  const messageProjectButtons = (
    <div className="space-y-1">
      <SidebarProjectsHeader
        title={sidebarProjectsTitle}
        isOwnerViewer={isSidebarOwnerViewer}
        ownerHandle={sidebarProjectsOwnerHandle}
        onCreateProject={() => openProjectFormForHandle(sidebarProjectsOwnerHandle)}
        onContactOwner={() => openMessagesForContactHandle(sidebarProjectsOwnerHandle)}
      />
      {!messageSidebarProjectsOwnerHandle ? (
        <p className="px-3 text-xs text-[#6b7280]">
          {isAuthenticated ? "No projects found." : "Sign in to see your projects."}
        </p>
      ) : isMessageSidebarProjectsLoading ? (
        <p className="px-3 text-xs text-[#6b7280]">Loading projects...</p>
      ) : messageSidebarProjects.length ? (
        messageSidebarProjects.map((project) => (
          <div key={project.id} className="relative">
            <a
              href={`/${messageSidebarProjectsOwnerHandle}/${project.slug}/`}
              className="sidebar-project-btn w-full flex items-start gap-3 px-3 py-2 rounded-sm-ds font-medium text-sm transition-colors text-[#6b7280] hover:bg-[#f3f4f6]"
            >
              <ProjectSidebarIcon faviconUrl={project.favicon_url} projectName={project.name} />
              <span className="flex-1 min-w-0 text-left">
                <span className="block font-medium leading-tight pr-10 truncate">{project.name}</span>
                {getProjectListMetaText(project) ? (
                  <span className="block w-full text-[11px] leading-tight text-[#6b7280] pt-2">
                    {getProjectListMetaText(project)}
                  </span>
                ) : null}
              </span>
            </a>
            {project.url ? (
              <span className="absolute top-2 right-2">
                <a
                  href={project.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[#9ca3af] hover:text-[#111827] p-1 rounded-sm-ds transition-colors"
                  aria-label={`Open ${project.name} website`}
                  title="Open project site"
                >
                  <ExternalLink size={16} />
                </a>
              </span>
            ) : null}
          </div>
        ))
      ) : renderNoProjectsFound()}
    </div>
  );

  const settingsNavItems = [
    { key: "general", label: "General", href: settingsUrl("general"), icon: Settings },
    { key: "api", label: "API Access", href: settingsUrl("api"), icon: KeyRound },
    { key: "connect-agent", label: "Agent Integration", href: settingsUrl("connect-agent"), icon: Bot },
  ];
  const settingsBackHref = workspaceOwnerHandle ? `/${workspaceOwnerHandle}/` : "/";

  const apiQuickstartEndpoints = [
    {
      method: "GET",
      path: "/api/projects",
      description: "List current user's projects",
      curl: `curl -X GET "${apiBaseUrl}/api/projects" -H "Authorization: Bearer <API_TOKEN>"`,
    },
    {
      method: "POST",
      path: "/api/projects/<owner_handle>/<project_slug>/issues",
      description: "Create an issue in a project",
      curl: `curl -X POST "${apiBaseUrl}/api/projects/<owner_handle>/<project_slug>/issues" -H "Authorization: Bearer <API_TOKEN>" -H "Content-Type: application/json" -d '{"title":"Need better search","issue_type":"feature","priority":2}'`,
    },
    {
      method: "GET",
      path: "/api/issues/<issue_id>",
      description: "Get issue details",
      curl: `curl -X GET "${apiBaseUrl}/api/issues/<issue_id>" -H "Authorization: Bearer <API_TOKEN>"`,
    },
    {
      method: "GET",
      path: "/api/auth/agent-token",
      description: "Get single agent-token status",
      curl: `curl -X GET "${apiBaseUrl}/api/auth/agent-token" -H "Authorization: Bearer <API_TOKEN>"`,
    },
    {
      method: "POST",
      path: "/api/auth/agent-token/connect",
      description: "Create single token if missing (or rotate existing)",
      curl: `curl -X POST "${apiBaseUrl}/api/auth/agent-token/connect" -H "Authorization: Bearer <API_TOKEN>"`,
    },
    {
      method: "POST",
      path: "/api/auth/agent-token/refresh",
      description: "Rotate existing agent token",
      curl: `curl -X POST "${apiBaseUrl}/api/auth/agent-token/refresh" -H "Authorization: Bearer <API_TOKEN>"`,
    },
  ];

  const settingsSidebarNavigation = (
    <>
      <div className="space-y-1">
        <div className="px-3 pb-2 flex items-center justify-between relative">
          <h3 className="text-[10px] font-mono font-bold text-[#9ca3af] uppercase tracking-wider">
            Settings
          </h3>
          <span className="p-1 rounded-sm-ds invisible shrink-0" aria-hidden="true">
            <Plus size={14} />
          </span>
          <span className="pointer-events-none absolute left-[-0.5rem] right-[-0.5rem] bottom-0 h-px bg-[#e5e7eb]" />
        </div>
        <div className="space-y-1 px-1">
          {settingsNavItems.map((item) => {
            const isActive =
              (item.key === "api" && isApiAccessView) ||
              (item.key === "connect-agent" && isConnectAgentView) ||
              (item.key === "general" && isSettingsGeneralView);
            const Icon = item.icon;
            return (
              <a
                key={item.key}
                href={item.href}
                onClick={(event) => {
                  event.preventDefault();
                  setSettingsSectionAndHistory(item.key);
                }}
                className={cls(
                  "w-full flex items-center gap-3 px-2 py-1.5 rounded-sm-ds font-medium text-sm transition-colors",
                  isActive ? "bg-cyan-50 text-[#06B6D4]" : "text-[#6b7280] hover:bg-[#f3f4f6]",
                )}
              >
                <Icon size={15} />
                {item.label}
              </a>
            );
          })}
        </div>
      </div>
    </>
  );

  const settingsMobileNavigation = (
    <div className="space-y-2 md:hidden">
      <p className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#9ca3af]">Settings</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {settingsNavItems.map((item) => {
          const isActive =
            (item.key === "api" && isApiAccessView) ||
            (item.key === "connect-agent" && isConnectAgentView) ||
            (item.key === "general" && isSettingsGeneralView);
          const Icon = item.icon;
          return (
            <a
              key={`mobile-${item.key}`}
              href={item.href}
              onClick={(event) => {
                event.preventDefault();
                setSettingsSectionAndHistory(item.key);
              }}
              className={cls(
                "rounded-sm-ds border px-3 py-2 text-xs font-bold uppercase tracking-wide text-center transition-colors",
                isActive
                  ? "border-cyan-200 bg-cyan-50 text-[#06B6D4]"
                  : "border-[#e5e7eb] text-[#6b7280] hover:text-[#111827]",
              )}
            >
              <span className="inline-flex items-center justify-center mr-1.5 align-middle">
                <Icon size={12} />
              </span>
              {item.label}
            </a>
          );
        })}
      </div>
    </div>
  );

  const sidebarBottomActionLabel = isSidebarOwnerViewer
    ? "Add new project"
    : sidebarProjectsOwnerHandle
      ? `Contact @${sidebarProjectsOwnerHandle}`
      : "Contact";

  const sidebarBottomActionIcon = isSidebarOwnerViewer ? <Plus size={18} /> : <MessageCircle size={18} />;

  const projectButtonsMobile = renderBoardProjectsSection();

  return (
    <div className="h-screen flex flex-col bg-[#f3f4f6] text-[#111827]">
      <header className="h-[56px] bg-white border-b border-[#e5e7eb] flex items-center justify-between px-4 md:px-6 shrink-0 z-50">
        <div className="flex items-center gap-4 md:gap-6 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            <a href="/" className="flex items-center gap-2">
              <div className="w-8 h-8 bg-[#06B6D4] rounded-sm-ds flex items-center justify-center text-white shadow-sm">
                <ListTodo size={20} />
              </div>
              <span className="font-bold text-lg tracking-tight">FeatureRequest</span>
            </a>
          </div>

          <nav className="hidden md:flex items-center text-sm font-medium text-[#6b7280] gap-2 truncate">
            {isGlobalSettingsView ? (
              <>
                <a href={settingsUrl("general")} className="hover:text-[#111827]">
                  settings
                </a>
                <span className="text-[#d1d5db] font-mono">/</span>
                <span className="text-[#111827] font-semibold truncate">
                  {isApiAccessView ? "api access" : isConnectAgentView ? "connect agent" : "general"}
                </span>
              </>
            ) : view === "messages" && messagesNavbarHandle ? (
              <>
                <a href={`/${messagesNavbarHandle}/`} className="hover:text-[#111827]">
                  {messagesNavbarHandle}
                </a>
                <span className="text-[#d1d5db] font-mono">/</span>
                <span className="text-[#111827] font-semibold truncate">Contact</span>
              </>
            ) : (
              <>
                {view === "messages" ? (
                  <span className="text-[#111827] font-semibold">messages</span>
                ) : (
                  <>
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
                  </>
                )}
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
              </>
            )}
          </nav>
        </div>

        <div className="flex items-center gap-3">
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
            <ProfileMenu
              menuRef={profileMenuRef}
              isOpen={isProfileMenuOpen}
              onToggle={() => setIsProfileMenuOpen((value) => !value)}
              currentUserHandle={currentUserHandle}
              currentUserAvatarUrl={currentUserAvatarUrl}
              canCreateProject={canCreateWorkspaceProject}
              onCreateProject={handleProfileProjectCreation}
              onClose={() => setIsProfileMenuOpen(false)}
              onLogout={handleLogout}
            />
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
        {bootstrap.ownerHandle || view === "messages" || isGlobalSettingsView ? (
          <aside className="w-72 bg-white border-r border-[#e5e7eb] flex-col shrink-0 hidden md:flex">
            <div className="flex-1 p-2 space-y-4 overflow-y-auto">
              {isGlobalSettingsView ? settingsSidebarNavigation : view === "messages" ? messageProjectButtons : projectButtons}
            </div>

            {isGlobalSettingsView ? (
              <div className="p-2 border-t border-[#e5e7eb]">
                <a
                  href={settingsBackHref}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds text-[#6b7280] hover:bg-[#f3f4f6] font-medium text-sm transition-colors"
                >
                  <LayoutDashboard size={18} />
                  Back to Workspace
                </a>
              </div>
            ) : (
              <div className="p-2 border-t border-[#e5e7eb]">
                <button
                  type="button"
                  onClick={() => {
                    if (isSidebarOwnerViewer) {
                      openProjectFormForHandle(sidebarProjectsOwnerHandle);
                      return;
                    }

                    setContactFeedback("");
                    setContactFeedbackTone("");
                    if (sidebarProjectsOwnerHandle) {
                      openMessagesForContactHandle(sidebarProjectsOwnerHandle);
                      return;
                    }

                    openMessagesForOwnerContact();
                  }}
                  className="w-full flex items-center gap-3 px-3 py-2 rounded-sm-ds text-[#6b7280] hover:bg-[#f3f4f6] font-medium text-sm transition-colors"
                >
                  {sidebarBottomActionIcon}
                  {sidebarBottomActionLabel}
                </button>
              </div>
            )}
          </aside>
        ) : null}

        <div className="flex-1 flex overflow-hidden">
          {view === "issues" ? (
                <div className="flex-1 flex overflow-hidden">
                  <section className="w-full md:w-[380px] border-r border-[#e5e7eb] bg-white flex flex-col shrink-0">
                <div className="p-4 border-b border-[#e5e7eb] space-y-3">
                  <div className="md:hidden space-y-3">{projectButtonsMobile}</div>

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
                                priorityTone(issue.priority),
                              )}
                            >
                              {toReadablePriority(issue.priority)}
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
                              <ThumbsUp size={14} />
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
                  <ThumbsUp size={18} className="text-[#06B6D4]" />
                  Upvote ({selectedIssue.upvotes_count})
                </button>
                <div className="h-4 w-[1px] bg-[#e5e7eb]" />
                <div className="flex items-center gap-2">
                  <UserAvatar
                    imageUrl={selectedIssue.author_avatar_url}
                    label={selectedIssue.author_handle || `user-${selectedIssue.author_id}`}
                    sizeClass="w-6 h-6"
                    fallbackClassName="bg-cyan-50 border border-cyan-100 text-[#06B6D4]"
                    fallbackTextClassName="text-[9px] font-bold"
                    imageClassName="rounded-full border border-cyan-100 object-cover"
                  />
                  <span className="text-[10px] font-mono text-[#6b7280] uppercase">
                    Created by @{selectedIssue.author_handle || `user-${selectedIssue.author_id}`} • {formatLongDate(selectedIssue.created_at)}
                  </span>
                </div>
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

                    <div className="flex-1 overflow-hidden flex flex-col">
                      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-8">
                        <div>
                          <h1 className="text-2xl font-bold text-[#111827] mb-4">{selectedIssue.title}</h1>
                          <div className="text-[#6b7280]">
                            <MarkdownContent
                              value={selectedIssue.description}
                              fallback="No description provided."
                            />
                          </div>
                        </div>

                        <div className="border-t border-[#e5e7eb] pt-8">
                          <h4 className="text-xs font-bold text-[#6b7280] uppercase tracking-widest mb-6">
                            Activity & Comments ({comments.length})
                          </h4>

                          <div className="space-y-6">
                            {comments.length === 0 ? (
                              <p className="text-sm text-[#6b7280]">No comments yet.</p>
                            ) : (
                              comments.map((comment) => (
                                <div key={comment.id} className="flex gap-4">
                                  <UserAvatar
                                    imageUrl={comment.author_avatar_url}
                                    label={comment.author_handle}
                                    sizeClass="w-8 h-8"
                                    fallbackTextClassName="text-[10px] font-bold"
                                  />
                                  <div className="flex-1">
                                    <div className="flex items-center justify-between mb-1">
                                      <span className="text-xs font-bold">@{comment.author_handle}</span>
                                      <span className="text-[10px] font-mono text-[#d1d5db]">
                                        {formatRelativeDate(comment.created_at)}
                                      </span>
                                    </div>
                                    <div className="p-3 bg-[#f9fafb] border border-[#e5e7eb] rounded-sm-ds text-sm text-[#6b7280]">
                                      <MarkdownContent value={comment.body} />
                                    </div>
                                  </div>
                                </div>
                              ))
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="border-t border-[#e5e7eb] bg-[#f9fafb] p-4 space-y-3">
                        <textarea
                          rows={3}
                          value={commentDraft}
                          onChange={(event) => setCommentDraft(event.target.value)}
                          className="w-full bg-white border border-[#e5e7eb] rounded-sm-ds p-3 text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none"
                          placeholder={isAuthenticated ? "Type your comment..." : "Login to post a comment."}
                          disabled={!isAuthenticated || isCommentSubmitting}
                        />
                        <div className="flex items-center justify-between">
                          {commentFeedback ? (
                            <span
                              className={`text-[10px] font-mono ${
                                commentFeedback.toLowerCase().includes("rejected by moderation")
                                  ? "text-[#b91c1c]"
                                  : "text-[#d1d5db]"
                              }`}
                            >
                              {commentFeedback}
                            </span>
                          ) : String(selectedIssue?.status || "").toLowerCase() === "closed" ? (
                            <span className="text-[10px] font-mono text-[#b45309]">
                              This item is closed. You can still post here but I suggest creating a new request.
                            </span>
                          ) : (
                            <span className="text-[10px] font-mono text-[#d1d5db]">Markdown supported</span>
                          )}
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
                  </>
                ) : (
                  <div className="p-10 text-[#6b7280]">Select a request to view details.</div>
                )}
              </main>
            </div>
          ) : view === "messages" ? (
            <div className="flex-1 flex overflow-hidden">
              <section className="w-full md:w-[360px] border-r border-[#e5e7eb] bg-white flex flex-col shrink-0">
                <div className="p-4 border-b border-[#e5e7eb] space-y-2">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-bold uppercase tracking-widest text-[#6b7280]">Messages</h2>
                    {isAuthenticated ? (
                      <button
                        type="button"
                        onClick={() => {
                          refreshMessages().catch(() => {
                            setStatus("Messages could not be loaded.", true);
                          });
                        }}
                        className="text-[10px] font-mono font-bold text-[#6b7280] hover:text-[#111827] uppercase"
                      >
                        Refresh
                      </button>
                    ) : null}
                  </div>
                  <p className="text-xs text-[#6b7280]">
                    {isMessagesLoading
                      ? "Loading conversations..."
                      : messageThreads.length
                        ? "Select a conversation to view messages."
                        : "No conversations found yet."}
                  </p>
                </div>

                <div className="flex-1 overflow-y-auto divide-y divide-[#e5e7eb]">
                  {isMessagesLoading ? (
                    <p className="p-4 text-sm text-[#6b7280]">Loading messages...</p>
                  ) : messageThreads.length ? (
                    messageThreads.map((thread) => {
                      const isActive = thread.threadId === selectedMessageThreadId;
                      return (
                        <button
                          type="button"
                          key={thread.threadId}
                          onClick={() => setMessagesThreadAndHistory(thread.threadId)}
                          className={cls(
                            "w-full text-left px-4 py-3 transition-colors",
                            isActive
                              ? "bg-cyan-50 border-l-4 border-[#06B6D4]"
                              : "hover:bg-[#f9fafb] border-l-4 border-transparent",
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className={cls("text-sm font-semibold", isActive ? "text-[#06B6D4]" : "text-[#111827]")}>
                              {getMessageThreadLabel(thread)}
                            </span>
                            <span className="text-[10px] text-[#6b7280]">
                              {thread.isNewConversation ? "new" : formatRelativeDate(thread.latestMessageAt)}
                            </span>
                          </div>
                          <p className="text-xs text-[#6b7280] mt-1">
                            {thread.isNewConversation
                              ? "Start a new conversation."
                              : trimForPreview(thread.latestMessageText)}
                          </p>
                        </button>
                      );
                    })
                  ) : (
                    <p className="p-4 text-sm text-[#6b7280]">No messages found yet.</p>
                  )}
                </div>
              </section>

              <main className="flex-1 bg-white flex flex-col overflow-hidden">
                <div className="border-b border-[#e5e7eb] px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-sm font-bold uppercase tracking-widest text-[#6b7280]">
                      {selectedMessageThread ? getMessageThreadLabel(selectedMessageThread) : getMessageThreadLabelById(selectedMessageThreadId)}
                    </h2>
                    {selectedMessageHandle ? (
                      <span className="text-[10px] font-mono text-[#6b7280]">
                        {selectedMessageThread ? selectedMessageThread.messages.length : 0} message
                        {selectedMessageThread?.messages.length === 1 ? "" : "s"}
                      </span>
                    ) : (
                      <span className="text-[10px] font-mono text-[#6b7280]">No conversation selected</span>
                    )}
                  </div>
                  {!isAuthenticated ? (
                    <p className="mt-2 text-xs text-[#6b7280]">Sign in to open your message inbox.</p>
                  ) : null}
                </div>
                <div className="flex-1 overflow-y-auto space-y-3 px-4 py-4">
                  {selectedMessageThread && selectedMessageThread.messages.length ? (
                    selectedMessageThread.messages.map((message) => (
                      <div
                        key={message.id}
                        className={cls("flex", message.isOutgoing ? "justify-end" : "justify-start")}
                      >
                        <div
                          className={cls(
                            "max-w-[88%] rounded-sm-ds border p-3 text-sm break-words space-y-1",
                            message.isOutgoing
                              ? "bg-cyan-50 border-cyan-100 text-[#0f172a]"
                              : "bg-[#f9fafb] border-[#e5e7eb] text-[#6b7280]",
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[10px] font-mono font-bold uppercase text-[#6b7280]">
                              {message.isOutgoing
                                ? `@${normalizeHandle(currentUserHandle) || "you"}`
                                : getMessageThreadLabel(selectedMessageThread)}
                            </span>
                            <span className="text-[10px] text-[#9ca3af]">{formatRelativeDate(message.created_at)}</span>
                          </div>
                          <div>{message.body}</div>
                        </div>
                      </div>
                    ))
                  ) : selectedMessageHandle ? (
                    <div className="text-sm text-[#6b7280]">
                      Start a new conversation with {getMessageThreadLabelById(selectedMessageThreadId)}.
                    </div>
                  ) : (
                    <div className="text-sm text-[#6b7280]">
                      Select a user from the left to open a conversation.
                    </div>
                  )}
                </div>
                <div className="border-t border-[#e5e7eb] bg-[#f9fafb] p-4 space-y-3">
                  {!selectedMessageHandle ? (
                    <p className="text-xs text-[#6b7280]">Select a conversation to send a message.</p>
                  ) : !isAuthenticated ? (
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs text-[#6b7280]">Sign in to send a direct message.</p>
                      <button
                        type="button"
                        onClick={() => openAuth("signIn")}
                        className="px-3 py-1.5 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors"
                      >
                        Sign In
                      </button>
                    </div>
                  ) : !canSendDirectMessage ? (
                    <p className="text-xs text-[#6b7280]">Select another user to start a conversation.</p>
                  ) : (
                    <>
                      <textarea
                        rows={3}
                        value={messageComposerBody}
                        onChange={(event) => setMessageComposerBody(event.target.value)}
                        placeholder={`Message ${getMessageThreadLabelById(selectedMessageThreadId)}...`}
                        className="w-full bg-white border border-[#e5e7eb] rounded-sm-ds p-3 text-sm focus:ring-1 focus:ring-[#06B6D4] outline-none resize-none"
                        disabled={isMessageComposerSubmitting}
                      />
                      <div className="flex items-center justify-between gap-3">
                        {messageComposerFeedback ? (
                          <span
                            className={cls(
                              "text-xs",
                              messageComposerFeedbackTone === "error"
                                ? "text-[#dc2626]"
                                : messageComposerFeedbackTone === "success"
                                  ? "text-[#16a34a]"
                                  : "text-[#6b7280]",
                            )}
                          >
                            {messageComposerFeedback}
                          </span>
                        ) : (
                          <span className="text-xs text-[#6b7280]">Press send to deliver instantly.</span>
                        )}
                        <button
                          type="button"
                          onClick={handleSendDirectMessage}
                          disabled={isMessageComposerSubmitting || !messageComposerBody.trim()}
                          className="px-4 py-1.5 bg-[#06B6D4] text-white text-xs font-bold rounded-sm-ds hover:bg-cyan-600 transition-colors disabled:opacity-45"
                        >
                          {isMessageComposerSubmitting ? "Sending..." : "Send"}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </main>
            </div>
          ) : isGlobalSettingsView ? (
            <div className="flex-1 bg-white flex flex-col overflow-hidden">
              {isSettingsGeneralView ? (
                <div className="flex-1 overflow-y-auto">
                  <div className="max-w-6xl mx-auto w-full px-6 md:px-8 py-10 space-y-8">
                    {settingsMobileNavigation}
                <div>
                      <h2 className="text-2xl font-bold text-[#111827] mb-2">General Settings</h2>
                      <p className="text-sm text-[#6b7280]">
                        Global workspace settings live here. API access applies to all of your projects.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                      <section className="rounded-md-ds border border-[#e5e7eb] bg-white p-6 space-y-4">
                        <h3 className="text-sm font-bold uppercase tracking-widest text-[#6b7280]">API Access</h3>
                        {isAuthenticated ? (
                          <div className="space-y-1">
                            <p className="text-sm text-[#111827]">
                              Generate and manage tokens for programmatic access.
                            </p>
                            <p className="text-xs text-[#6b7280]">
                              Your API tokens inherit your account permissions and can access all of your projects.
                            </p>
                            <a
                              href={settingsUrl("api")}
                              onClick={(event) => {
                                event.preventDefault();
                                setSettingsSectionAndHistory("api");
                              }}
                              className="inline-flex items-center gap-2 rounded-sm-ds bg-[#111827] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-black transition-colors"
                            >
                              <KeyRound size={14} />
                              Open API Access
                            </a>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            <p className="text-sm text-[#6b7280]">Sign in to manage settings and API tokens.</p>
                            <button
                              type="button"
                              onClick={() => openAuth("signIn")}
                              className="px-4 py-2 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors"
                            >
                              Sign In
                            </button>
                          </div>
                        )}
                      </section>

                      <section className="rounded-md-ds border border-[#e5e7eb] bg-white p-6 space-y-4">
                        <h3 className="text-sm font-bold uppercase tracking-widest text-[#6b7280]">Agent Integration</h3>
                        <div className="space-y-2 text-sm text-[#6b7280]">
                          <p>One agent token is maintained per user.</p>
                          <p>It is write-enabled and only rotates when you refresh it.</p>
                        </div>
                        <a
                          href={settingsUrl("connect-agent")}
                          onClick={(event) => {
                            event.preventDefault();
                            setSettingsSectionAndHistory("connect-agent");
                          }}
                          className="inline-flex items-center gap-2 rounded-sm-ds bg-[#06B6D4] px-4 py-2 text-xs font-bold uppercase tracking-wide text-white hover:bg-cyan-600 transition-colors"
                        >
                          <Bot size={14} />
                          Open Agent Integration
                        </a>
                      </section>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div className="p-4 border-b border-[#e5e7eb] bg-white md:hidden">
                    {settingsMobileNavigation}
                  </div>
                  <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
                    <section className="flex-1 flex flex-col min-w-0 bg-white md:border-r border-[#e5e7eb]">
                      <div className={cls("p-6 space-y-4", isConnectAgentView ? "" : "border-b border-[#e5e7eb]")}>
                        <div className="flex items-start justify-between gap-4">
                          <h1 className="text-xl font-bold tracking-tight text-[#111827]">
                            {isConnectAgentView ? "Connect Agent" : "API Access"}
                          </h1>
                        </div>
                        {isConnectAgentView ? (
                          <>
                            <p className="text-sm text-[#6b7280]">
                              Connect your agent once so it can work with your feature requests automatically.
                            </p>
                            <div className="rounded-sm-ds border border-[#fde68a] bg-[#fffbeb] p-3 text-sm text-[#92400e] flex items-start gap-2">
                              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                              <span>
                                The agents can act on your behalf without any permission restriction. In other words, they can do
                                whatever you can do on this platform. Only use agents you trust.
                              </span>
                            </div>
                            <div className="rounded-sm-ds border border-[#e5e7eb] bg-[#f9fafb] p-3 space-y-2">
                              <p className="text-[10px] font-mono font-bold uppercase tracking-wider text-[#6b7280]">
                                Agent Token
                              </p>
                              <div className="flex flex-col md:flex-row md:items-center gap-2">
                                <code className="flex-1 block w-full overflow-x-auto rounded-sm-ds bg-white border border-[#e5e7eb] px-2 py-1 text-[11px] text-[#111827]">
                                  {visibleAgentTokenValue || "Preparing token..."}
                                </code>
                                <div className="flex items-center gap-2">
                                  <button
                                    type="button"
                                    onClick={() => copyValueAndNotify(activeAgentTokenSecret, "Token copied.")}
                                    disabled={!canCopyActiveAgentToken}
                                    className="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1 text-[10px] font-bold text-[#111827] hover:bg-[#f3f4f6] disabled:opacity-45"
                                    title={canCopyActiveAgentToken ? "Copy token" : "Refresh token to copy"}
                                  >
                                    <Copy size={12} />
                                    Copy
                                  </button>
                                  <button
                                    type="button"
                                    onClick={handleRefreshAgentToken}
                                    disabled={!isAuthenticated || isApiTokensLoading || isAgentRefreshSubmitting}
                                    className="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1 text-[10px] font-bold text-[#111827] hover:bg-[#f3f4f6] disabled:opacity-45"
                                  >
                                    {isAgentRefreshSubmitting ? "Refreshing..." : "Refresh"}
                                  </button>
                                </div>
                              </div>
                              <p className="text-[11px] text-[#6b7280]">
                                The token does not expire. Refresh if you want to revoke the current token and issue a new one.
                              </p>
                            </div>
                          </>
                        ) : (
                          <p className="text-sm text-[#6b7280]">
                            Manage API endpoints and authentication details for integrations.
                          </p>
                        )}
                        {apiTokenFeedback ? (
                          <p
                            className={cls(
                              "text-xs",
                              apiTokenFeedbackTone === "error"
                                ? "text-[#dc2626]"
                                : apiTokenFeedbackTone === "success"
                                  ? "text-[#16a34a]"
                                  : "text-[#6b7280]",
                            )}
                          >
                            {apiTokenFeedback}
                          </p>
                        ) : null}
                      </div>

                      <div className="flex-1 overflow-y-auto">
                        {isConnectAgentView ? null : (
                          !isAuthenticated ? (
                            <div className="p-6">
                              <div className="rounded-sm-ds border border-[#e5e7eb] bg-[#f9fafb] p-4 space-y-3">
                                <p className="text-sm text-[#6b7280]">Sign in to manage your API tokens.</p>
                                <button
                                  type="button"
                                  onClick={() => openAuth("signIn")}
                                  className="px-4 py-2 bg-[#111827] text-white text-xs font-bold rounded-sm-ds hover:bg-black transition-colors"
                                >
                                  Sign In
                                </button>
                              </div>
                            </div>
                          ) : isApiTokensLoading ? (
                            <p className="p-6 text-sm text-[#6b7280]">Loading tokens...</p>
                          ) : (
                            <div className="overflow-x-auto">
                              <table className="min-w-full divide-y divide-[#e5e7eb]">
                                <thead className="bg-[#f9fafb] border-b border-[#e5e7eb]">
                                  <tr>
                                    <th className="px-6 py-3 text-left text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">
                                      Name
                                    </th>
                                    <th className="px-6 py-3 text-left text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">
                                      Key
                                    </th>
                                    <th className="px-6 py-3 text-center text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">
                                      Write
                                    </th>
                                    <th className="px-6 py-3 text-left text-[10px] font-mono font-bold text-[#6b7280] uppercase tracking-wider">
                                      Created
                                    </th>
                                  </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-[#e5e7eb]">
                                  {!apiTokens.length ? (
                                    <tr>
                                      <td colSpan={4} className="px-6 py-6 text-sm text-[#6b7280]">
                                        No API tokens yet.
                                      </td>
                                    </tr>
                                  ) : (
                                    apiTokens.map((token) => {
                                      const hasSecret = Boolean(apiTokenSecrets[token.id]);
                                      return (
                                        <tr key={token.id} className="group hover:bg-[#f9fafb] transition-colors">
                                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-[#111827]">
                                            <div>
                                              <p>{token.name}</p>
                                            </div>
                                          </td>
                                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                                            <div className="flex items-center gap-2">
                                              <code className="bg-[#f3f4f6] px-2 py-0.5 rounded-sm-ds font-mono text-xs text-[#6b7280]">
                                                {token.token_prefix}••••••••
                                              </code>
                                              <button
                                                type="button"
                                                onClick={() => handleCopyApiToken(token.id)}
                                                disabled={!hasSecret}
                                                title={hasSecret ? "Copy Token" : "Token value unavailable"}
                                                className={cls(
                                                  "text-[#9ca3af] hover:text-[#06B6D4] transition-all",
                                                  hasSecret
                                                    ? "opacity-0 group-hover:opacity-100"
                                                    : "opacity-35 cursor-not-allowed",
                                                )}
                                              >
                                                <Copy size={14} />
                                              </button>
                                            </div>
                                          </td>
                                          <td className="px-6 py-4 whitespace-nowrap text-center text-sm">
                                            <span
                                              className={cls(
                                                "inline-flex items-center justify-center text-xs font-mono font-bold rounded-sm-ds w-6 h-6",
                                                token.can_write
                                                  ? "text-[#16a34a] bg-[#f0fdf4]"
                                                  : "text-[#dc2626] bg-[#fef2f2]",
                                              )}
                                              aria-label={token.can_write ? "Writable token" : "Read-only token"}
                                            >
                                              {token.can_write ? "✓" : "✕"}
                                            </span>
                                          </td>
                                          <td className="px-6 py-4 whitespace-nowrap text-xs text-[#6b7280] font-mono">
                                            {formatLongDate(token.created_at)}
                                          </td>
                                        </tr>
                                      );
                                    })
                                  )}
                                </tbody>
                              </table>
                            </div>
                          )
                        )}
                      </div>
                    </section>

                    <aside className="w-full md:w-[460px] flex flex-col bg-[#f9fafb] border-t border-[#e5e7eb] md:border-t-0">
                      <div className="p-6 border-b border-[#e5e7eb] bg-white">
                        <h2 className="text-sm font-bold uppercase tracking-widest text-[#6b7280] flex items-center gap-2">
                          <KeyRound size={14} />
                          {isConnectAgentView ? "Agent Prompt" : "API Quickstart"}
                        </h2>
                      </div>
                      {isConnectAgentView ? (
                        <div className="flex-1 overflow-y-auto p-6 space-y-4">
                          <p className="text-sm text-[#6b7280]">
                            Give this prompt to your agent to manage your feature requests.
                          </p>
                          <div className="rounded-sm-ds border border-[#e5e7eb] bg-white p-3 space-y-3">
                            <pre className="block w-full overflow-x-auto whitespace-pre-wrap rounded-sm-ds bg-[#f9fafb] border border-[#e5e7eb] px-2 py-2 text-[11px] text-[#111827]">
                              {promptTextValue}
                            </pre>
                            <div
                              className={cls(
                                "flex items-center border-t border-[#e5e7eb] pt-2",
                                agentPromptCopyFeedback ? "justify-between" : "justify-end",
                              )}
                            >
                              {agentPromptCopyFeedback ? (
                                <p
                                  className={cls(
                                    "text-[11px]",
                                    agentPromptCopyFeedbackTone === "error" ? "text-[#dc2626]" : "text-[#16a34a]",
                                  )}
                                >
                                  {agentPromptCopyFeedback}
                                </p>
                              ) : null}
                              <button
                                type="button"
                                onClick={handleCopyAgentPrompt}
                                className="inline-flex items-center gap-1 rounded-sm-ds border border-[#e5e7eb] bg-white px-2 py-1 text-[10px] font-bold text-[#111827] hover:bg-[#f3f4f6]"
                              >
                                <Copy size={12} />
                                Copy Prompt
                              </button>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex-1 overflow-y-auto p-6 space-y-6">
                          <div className="space-y-3">
                            <h3 className="text-xs font-bold uppercase font-mono text-[#6b7280] tracking-wider">
                              Endpoint URL
                            </h3>
                            <div className="bg-[#111827] text-white p-3 rounded-sm-ds font-mono text-xs break-all">
                              {apiBaseUrl}
                            </div>
                            <button
                              type="button"
                              onClick={() => copyValueAndNotify(apiBaseUrl, "Base URL copied.")}
                              className="text-[10px] font-mono font-bold uppercase text-[#6b7280] hover:text-[#111827]"
                            >
                              Copy base URL
                            </button>
                          </div>

                          <div className="space-y-4">
                            <h3 className="text-xs font-bold uppercase font-mono text-[#6b7280] tracking-wider">
                              Authentication
                            </h3>
                            <p className="text-xs text-[#6b7280] leading-relaxed">
                              Include your API token in the <code className="bg-[#e5e7eb] px-1 rounded text-[#111827]">Authorization</code>{" "}
                              header as a Bearer token.
                            </p>
                            <div className="bg-[#111827] text-gray-300 p-3 rounded-sm-ds font-mono text-[11px] overflow-x-auto">
                              curl -H "Authorization: Bearer YOUR_TOKEN" \
                              {"\n"}
                              {apiBaseUrl}/api/projects
                            </div>
                          </div>

                          <div className="space-y-4">
                            <h3 className="text-xs font-bold uppercase font-mono text-[#6b7280] tracking-wider">
                              Common Endpoints
                            </h3>
                            <div className="space-y-2">
                              {apiQuickstartEndpoints.slice(0, 3).map((item) => (
                                <div
                                  key={`summary-${item.path}`}
                                  className="flex items-center justify-between text-[11px] font-mono border-b border-[#e5e7eb] pb-2"
                                >
                                  <span className={cls("font-bold", methodTone(item.method))}>{item.method}</span>
                                  <span className="text-[#111827]">{item.path.replace("<token_id>", ":token_id")}</span>
                                </div>
                              ))}
                            </div>
                          </div>

                          <div className="bg-white border border-[#e5e7eb] p-4 rounded-md-ds space-y-2">
                            <p className="text-[11px] text-[#6b7280]">Need the full API spec?</p>
                            <a
                              href="/api/docs"
                              target="_blank"
                              rel="noreferrer"
                              className="text-xs font-bold text-[#06B6D4] hover:underline flex items-center gap-1"
                            >
                              View Full Docs
                              <ExternalLink size={12} />
                            </a>
                          </div>
                        </div>
                      )}
                    </aside>
                  </div>
                </>
              )}
            </div>
          ) : view === "projectSettings" ? (
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

      <AuthModal
        authMode={authMode}
        onOpenAuth={openAuth}
        onClose={closeAuth}
        onSignInSubmit={onSignInSubmit}
        onSignUpSubmit={onSignUpSubmit}
        signInIdentity={signInIdentity}
        onSignInIdentityChange={(event) => setSignInIdentity(event.target.value)}
        signUpHandle={signUpHandle}
        onSignUpHandleChange={(event) => setSignUpHandle(event.target.value)}
        signUpEmail={signUpEmail}
        onSignUpEmailChange={(event) => setSignUpEmail(event.target.value)}
        authFeedback={authFeedback}
        isAuthSubmitting={isAuthSubmitting}
        signUpHandlePlaceholder="your_team"
        signUpEmailPlaceholder="you@company.com"
        overlayClassName="z-[120]"
      />

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
