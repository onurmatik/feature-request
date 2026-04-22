---
name: feature-request
description: Manage feature request intake, normalization, triage, queue operations, and API-only lifecycle workflows.
---

# Skills (Agent Task Catalog)

This file is the single skill registry for the repository. Each section is an actionable skill with a deterministic flow.

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
- read projects
- read requests/issues
- create requests
- add comments
- edit comments
- toggle upvotes

### Required Inputs
- Base URL:
  - https://featurerequest.io
- Auth mode:
  - `Bearer <token>` flow.
  - For write operations, token must be write-enabled (`can_write=true`).
- `owner_handle` (required for read/write paths under that board).
- Optional: `project_slug`.
- Input payloads:
  - request: `issue_type`, `title`, `description`, `priority`.
  - comment: `body`.
  - optional filters: `issue_type`, `status`, `priority`, `limit`.

### Required API Routes
- Agent connect/bootstrap:
  - `POST /api/auth/agent-token/connect`
  - `POST /api/auth/agent-token/refresh`
- Read projects:
  - `GET /api/owners/{owner_handle}/projects`
- Read issues:
  - `GET /api/owners/{owner_handle}/issues`
  - `GET /api/projects/{owner_handle}/{project_slug}/issues`
  - `GET /api/issues/{issue_id}`
- Create issue:
  - `POST /api/projects/{owner_handle}/{project_slug}/issues`
- Add comment:
  - `POST /api/issues/{issue_id}/comments`
- Edit comment:
  - `PATCH /api/issues/{issue_id}/comments/{comment_id}`
- Toggle upvote:
  - `POST /api/issues/{issue_id}/upvote/toggle`

### Command Flow
1. Validate auth credentials and action.
2. If no token exists yet for this run, call `POST /api/auth/agent-token/connect` and store returned token securely for current task.
3. If read requested:
   - call project list, then issue list filtered by optional fields.
   - if one issue is target, call issue detail.
4. If creating request:
   - call create issue endpoint with required body.
5. If adding comment:
   - call create comment endpoint with `{"body": "<text>"}`.
6. If editing comment:
   - call update comment endpoint with `{"body": "<text>"}`.
7. If upvote requested:
   - call upvote toggle endpoint and read returned `upvoted` + `upvotes_count`.
8. Return a normalized result object (see output format).
9. On failures, return error object with action and actionable recovery step.

### Expected Output Format
Return compact JSON:
```json
{
  "ok": true,
  "action": "read_issues|create_issue|add_comment|toggle_upvote",
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
