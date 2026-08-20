---
name: feature-request
description: Manage feature request intake, normalization, triage, queue operations, and API-only lifecycle workflows.
---

# Skills (Agent Task Catalog)

This file is the repository's downstream skill registry. Each section is an actionable skill
with a deterministic flow, but normative agent semantics live only in `agent/contract.yaml`.
Tool schemas, scopes, capabilities, ownership, approvals, errors, side effects, and retry rules
must be referenced or mechanically projected from that Contract rather than redefined here.

Agent Contract 1.1.0 names `get_account_capabilities` as the bootstrap tool. The repository now
implements its exact 30-tool projection, while MCP production conformance is `pending`
until the immutable MCP release, PostgreSQL concurrency, deployment, observation, and real-client
acceptance gates pass. The MCP and API sections below document that release-preparation handoff.

## Skill: `agent-onboard`
### Trigger
User asks for agent-facing setup or onboarding changes.

### Required Inputs
- Target feature area (`backend`, `frontend`, `tooling`, or `manifest`).
- Scope of changes and acceptance criteria.

### Command Flow
1. Read `./AGENTS.md`.
2. Read `./agents.json` if present.
3. Update only the requested sections.
4. Run relevant validation commands after edit.

### Expected Output
- Summary of updated sections.
- List of files changed.
- Validation command results.

### Failure Handling
- If required references are missing, stop and request the missing inputs before writing.
- If validation fails, include failing command output and propose next corrective step.

## Skill: `feature-request-operator` 
### Trigger
User asks an agent to read or mutate feature requests for a public board.

### Purpose
Operate on board data via API:
- read, create, update, and explicitly delete projects
- read requests/issues
- read owner-scoped queue signals and cursor-based request changes
- find explainable duplicate candidates and manage reversible canonical links
- record delivery artifact links for agent-side verification
- update requests/issues
- transition request status
- read comments
- create requests
- add comments
- edit comments
- toggle upvotes

### Prompt Presets
- `portfolio-triage`: read-only queue snapshot across all projects owned by the authenticated user.
- `project-triage`: read-only queue snapshot for one `owner_handle/project_slug`.
- `project-implementation`: use one project's FeatureRequest issues as the source of truth for local repo implementation work.

### Agent/MCP Decision Boundary
- FeatureRequest stores facts and controlled state; the calling agent performs semantic judgment.
- Treat current priority, votes, comments, status, and activity timestamps as queue evidence.
- Treat duplicate similarity scores, matched terms, and score components as candidates only.
- Use the returned algorithm identifier when comparing scores across runs or versions.
- Never create a duplicate link solely because a similarity score is high; inspect both requests first.
- A delivery artifact is only a stored URL. Inspect it with the agent's repository, GitHub, CI,
  deployment, or release tools before describing delivery as verified.
- Linking a duplicate or delivery artifact never changes request priority or status automatically.
- Activity/change events begin when P1 is deployed; do not infer a complete pre-P1 audit history.

### Required Inputs
- Base URL:
  - https://featurerequest.io
- Auth mode:
  - MCP: OAuth 2.1 Authorization Code + PKCE S256; CIMD preferred, DCR fallback.
  - API-only workflows: existing `fr_` bearer tokens remain valid on `/api`.
  - Never send an `fr_` API token to `/mcp`; initial MCP scope is `read`, with `write` step-up.
- `owner_handle` (required for read/write paths under that board).
- Optional: `project_slug`.
- Input payloads:
  - request: `issue_type`, `title`, `description`, `priority`.
  - comment: `body`.
  - optional filters: `issue_type`, `status`, `priority`, `limit`.
  - `status=active` is a list-only filter that excludes `done`, `closed`, and `declined`.

### MCP/OAuth 1.1 Repository Runtime (Production Conformance Pending)
- Transport: Streamable HTTP at `/mcp`.
- Authentication: MCP OAuth discovery, public clients, PKCE S256, exact resource binding.
- Permission model:
  - act as the consenting FeatureRequest user;
  - use Contract-projected `read` and `write` scopes;
  - enforce project/request/comment ownership in the domain service;
  - reject API tokens, query tokens, cookie tokens, foreign-resource tokens, and expired tokens.
- The server intentionally does not expose `get_connection_context`; call `list_projects`
  when the authenticated user's owner/project context is unknown.
- `get_account_capabilities` is implemented as the capability/limit bootstrap. Its public
  production availability remains pending the immutable release gates.
- This tool list is a downstream projection only. The canonical public catalog and all
  behavioral metadata are owned by `agent/contract.yaml`.
- Bootstrap tool:
  - `get_account_capabilities`
- P1 project tools:
  - `list_projects`
  - `get_project`
  - `create_project`
  - `update_project`
  - `delete_project`
- Product Spec and scope tools:
  - `get_project_spec`
  - `update_project_spec`
  - `get_request_scope_assessment`
  - `reassess_request_scope`
  - `propose_project_spec_update`
  - `list_project_spec_proposals`
  - `resolve_project_spec_proposal`
- P1 request and evidence tools:
  - `list_requests`
  - `get_request`
  - `list_request_comments`
  - `get_queue_snapshot`
  - `find_duplicate_candidates`
  - `list_request_activity`
  - `list_request_changes`
  - `list_delivery_artifacts`
  - `create_request`
  - `update_request`
  - `transition_request`
  - `add_request_comment`
  - `update_request_comment`
  - `link_duplicate_request`
  - `unlink_duplicate_request`
  - `link_delivery_artifact`
  - `unlink_delivery_artifact`
- `delete_project` is destructive: call `get_project` first, require explicit user direction,
  and pass the same project id as `confirm_project_id`.
- Keep status transitions separate from content/priority updates.
- Treat scope assessments as evidence. Automatic `declined` is allowed only when the guarded
  Contract rule matches an exact `Out of scope` quote without contradiction or ambiguity.
- Assessment failures fail open and remain owner-only. Pending spec proposals are owner-private;
  acceptance requires the unchanged base spec revision and rejection creates no public event.
- Only the project owner may transition into or out of `declined`; authors may still comment.
- Do not transition a request to `done` or `closed` without explicit user direction
  and delivery evidence that the calling agent has inspected.
- Intentionally not exposed through MCP: token create/revoke, billing/checkout, bulk close,
  and bulk mutation.

### Plugin Package Compatibility
- Portable package contract: Agent Plugins 1.0.0 root `plugin.json`, root `mcp.json`,
  and immediate-child skills under `skills/`.
- The portable MCP declaration uses `streamable-http`; authentication is configured by
  the consuming client because Agent Plugins 1.0.0 does not define credential references.
- Codex-native metadata remains in `.codex-plugin/plugin.json` and `.mcp.json`; keep its
  name, version, MCP URL, and shared `skills/` content aligned with the portable package.

### Required API Routes
- Web-session agent onboarding only:
  - `POST /api/auth/agent-token/connect`
  - `POST /api/auth/agent-token/refresh`
- Read projects:
  - `GET /api/projects`
  - `GET /api/owners/{owner_handle}/projects`
- Manage owned projects:
  - `POST /api/projects`
  - `GET /api/projects/{project_id}`
  - `PATCH /api/projects/{project_id}`
  - `DELETE /api/projects/{project_id}`
- Product Spec and owner proposal workflow:
  - `GET /api/projects/{owner_handle}/{project_slug}/spec`
  - `PUT /api/projects/{project_id}/spec`
  - `DELETE /api/projects/{project_id}/spec`
  - `GET /api/issues/{issue_id}/scope-assessment`
  - `POST /api/issues/{issue_id}/scope-assessment/retry`
  - `POST /api/issues/{issue_id}/spec-change-proposals`
  - `GET /api/projects/{project_id}/spec-change-proposals?status=pending`
  - `PATCH /api/spec-change-proposals/{proposal_id}`
- Read issues:
  - `GET /api/owners/{owner_handle}/issues`
  - `GET /api/projects/{owner_handle}/{project_slug}/issues`
  - `GET /api/issues/{issue_id}`
- Read queue and activity evidence:
  - `GET /api/me/request-queue`
  - `GET /api/me/issue-changes`
  - `GET /api/issues/{issue_id}/activity`
- Find and manage duplicates:
  - `GET /api/projects/{owner_handle}/{project_slug}/duplicate-candidates`
  - `PATCH /api/issues/{issue_id}/duplicate`
  - `DELETE /api/issues/{issue_id}/duplicate`
- Manage delivery evidence:
  - `GET /api/issues/{issue_id}/delivery-artifacts`
  - `POST /api/issues/{issue_id}/delivery-artifacts`
  - `DELETE /api/issues/{issue_id}/delivery-artifacts/{artifact_id}`
- Update issue:
  - `PATCH /api/issues/{issue_id}`
- Create issue:
  - `POST /api/projects/{owner_handle}/{project_slug}/issues`
  - Agents must continue to use this authenticated endpoint. The public
    `/api/embed/projects/{owner_handle}/{project_slug}/submissions` route is browser-only,
    requires Turnstile plus email verification, and must not be used for agent writes.
- Add comment:
  - `POST /api/issues/{issue_id}/comments`
- Read comments:
  - `GET /api/issues/{issue_id}/comments`
- Edit comment:
  - `PATCH /api/issues/{issue_id}/comments/{comment_id}`
- Toggle upvote:
  - `POST /api/issues/{issue_id}/upvote/toggle`

### Command Flow
1. Select MCP or API mode explicitly; never reuse credentials across the two resources.
2. For MCP, complete OAuth discovery and call `get_account_capabilities`; accept `write` step-up
   only when the user-requested action requires mutation.
3. For API-only mode, use a supplied raw API token only on `/api`; agent-token connect/refresh
   remains limited to browser/session onboarding.
4. If read requested:
   - for portfolio triage, call `GET /api/me/request-queue`; use the returned current fields and signals as evidence for the agent's own prioritization.
   - for project-scoped triage or implementation, call `GET /api/projects/{owner_handle}/{project_slug}/issues` directly with optional filters.
   - if one issue is target, call issue detail.
5. If managing a project:
   - use the focused create/get/update project route.
   - before delete, read the project by id and proceed only when the user explicitly requested deletion.
6. If creating request:
   - optionally call duplicate candidates with the proposed title/description.
   - inspect plausible candidates; do not treat the score as a decision.
   - call create issue endpoint with required body when a new canonical request is still appropriate.
7. If classifying a duplicate:
   - read both issues, ensure they represent the same underlying request, then link the duplicate to the root canonical issue.
   - unlink the relationship when evidence changes; never transition or reprioritize as a side effect.
8. If updating request content or priority:
   - call update issue with only the requested fields.
9. If transitioning request status:
   - call update issue with only `status`.
   - do not use `done` or `closed` without explicit user direction and delivery evidence.
10. If adding comment:
   - call create comment endpoint with `{"body": "<text>"}`.
11. If editing comment:
   - call update comment endpoint with `{"body": "<text>"}`.
12. If upvote requested:
   - call upvote toggle endpoint and read returned `upvoted` + `upvotes_count`.
13. If recording delivery:
   - link the artifact URL with its kind and label.
   - inspect the external artifact independently; the stored link is not verification.
   - only then comment or transition when explicitly requested.
14. For polling or follow-up, call the cursor-based change feed with the last `next_cursor`.
15. Return a normalized result object (see output format).
16. On failures, return error object with action and actionable recovery step.

### Project-Scoped Implementation Guidance
- Treat FeatureRequest as the ticket source of truth.
- Perform code changes only in the local repository/workspace where the coding agent is already running.
- Only read issues for the instructed `owner_handle/project_slug`; do not read or modify other projects.
- Pick at most one ready issue per run unless the user explicitly asks for more.
- Before code changes, produce a short implementation plan.
- Run relevant tests after edits.
- After implementation, add a concise comment back to the issue when write access is available.
- Link relevant pull request, commit, deployment, or release URLs as delivery artifacts.
- Verify those artifacts with the coding agent's external tools; FeatureRequest does not verify them.
- Do not mark an issue `done` automatically; reserve `done`/`closed` for merge or release confirmation.

### Expected Output Format
Return compact JSON:
```json
{
  "ok": true,
  "action": "<focused MCP or API action name>",
  "request": {
    "method": "POST",
    "path": "/api/projects/{owner_handle}/{project_slug}/issues",
    "status": 201
  },
  "resource": {
    "owner_handle": "owner",
    "project_slug": "project",
    "issue_id": 123
  },
  "data": {},
  "meta": {
    "items_returned": 0,
    "created_at": "2026-02-27T12:00:00Z"
  }
}
```

For failures:
```json
{
  "ok": false,
  "action": "add_comment",
  "request": {...},
  "error": {
    "status_code": 400,
    "message": "Message rejected by moderation"
  },
  "next_step": "Retry with cleaner content or ask user for a revised message."
}
```

### Failure Handling
- `401`: refresh or request new credentials and retry.
- `403`:
  - for read-only token on write action, instruct token replacement with `can_write=true` before retry.
- `400`: log payload validation/moderation failure and stop; do not retry silently.
- `404`: validate `owner_handle`, `project_slug`, or `issue_id` input.
- `503`: retry with backoff for transient moderation/provider failures.
- Never auto-delete or mutate any resource unless `action` explicitly asked.

### Prompt Examples
- Read-only daily triage: read authenticated user's projects, summarize active requests, and return `Queue Snapshot`, `Priority Decisions`, `Active Follow-ups`, `Risks and Blockers`, and `Next Checkpoint`.
- Project-specific planning: read only `owner_handle/project_slug`, identify the next ready issue, and produce an implementation plan without editing code.
- Project-specific implementation with tests: read only `owner_handle/project_slug`, pick at most one ready issue, implement in the current local repo, run relevant tests, and comment back with results when write access is available.
- Release follow-up: after merge or release confirmation, add a closure comment and update the issue status only when explicitly asked.

## Skill: `user-request-manager`
### Trigger
User asks an agent to manage incoming requests as a queue (visibility, prioritization, ownership, follow-up, closure).

### Required Inputs
- API access token and scope.
- Request source input (list, ticket export, or pasted requests).
- Optional SLA or deadline policy.

### Command Flow
1. Ingest requests from provided source.
2. Normalize each item into an API-backed record:
   - `issue_id`, `owner_handle`, `project_slug`, `issue_type`, `title`, `description`, `priority`, `status`.
3. Deduplicate overlapping requests and keep one canonical item.
4. Triage by urgency/impact and assign `P0`-`P3`.
5. Maintain one prioritized queue sorted by priority and due date.
6. For each active request, include explicit next action in report output (do not persist non-model fields as API attributes).
7. Produce concise checkpoint updates (new/changed/blocked/due soon/next actions).
8. Close request only after expected outcome is met, with closure note.

### Expected Output
- `Queue Snapshot` table:
  - `issue_id | summary | priority | status | owner_handle/project_slug | next action`
- `Priority Decisions`
- `Active Follow-ups`
- `Risks and Blockers`
- `Next Checkpoint`

### Failure Handling
- Missing permissions/scope: return blocking auth note and exact missing scope.
- Missing required request fields: mark item `waiting`, request only missing fields.
- API rate-limit/transient failure: retry with bounded backoff and report partial progress.
- Never perform code or config edits from this skill; operate only through exposed request APIs.
