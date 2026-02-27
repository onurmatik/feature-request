# Skills (Agent Task Catalog)

This file is the single skill registry for the repository. Each section is an actionable skill with a deterministic flow.

## Skill: `agent-onboard`
### Trigger
User asks for agent-facing setup or onboarding changes.

### Required Inputs
- Target feature area (`backend`, `frontend`, `tooling`, or `manifest`).
- Scope of changes and acceptance criteria.

### Command Flow
1. Read `/Users/onurmatik/Projects/FeatureRequest/AGENTS.md`.
2. Read `/Users/onurmatik/Projects/FeatureRequest/agents.json` if present.
3. Update only the requested sections.
4. Run relevant validation commands after edit.

### Expected Output
- Summary of updated sections.
- List of files changed.
- Validation command results.

### Failure Handling
- If required references are missing, stop and request the missing inputs before writing.
- If validation fails, include failing command output and propose next corrective step.

## Skill: `agent-manifest-update`
### Trigger
Request to create or update `agents.json`.

### Required Inputs
- Tool list with input/output schemas.
- Supported auth modes and scopes.
- Rate limits and operational constraints.
- Docs URL.

### Command Flow
1. Draft JSON under `/Users/onurmatik/Projects/FeatureRequest/agents.json`.
2. Validate JSON syntax.
3. Ensure consistency with `AGENTS.md`.
4. Run quick grep checks for impacted interfaces if endpoints changed.

### Expected Output
- Pretty-printed `agents.json` diff.
- Brief compatibility notes.

### Failure Handling
- Reject invalid schemas before write.
- For auth/scope ambiguity, return a blocking note with exact field assumptions.

## Skill: `feature-request-operator` 
### Trigger
User asks an agent to read or mutate feature requests for a public board.

### Purpose
Operate on board data via API:
- read projects
- read requests/issues
- create requests
- add comments
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
6. If upvote requested:
   - call upvote toggle endpoint and read returned `upvoted` + `upvotes_count`.
7. Return a normalized result object (see output format).
8. On failures, return error object with action and actionable recovery step.

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

## Skill: `agent-safe-edit`
### Trigger
Any code or config change requested by an agent workflow.

### Required Inputs
- File(s) to change.
- Goal and constraints.
- Whether destructive commands are needed.

### Command Flow
1. Confirm scope with existing `AGENTS.md`.
2. Inspect impacted files with minimal context reads.
3. Apply surgical patch.
4. Run targeted tests/lint/build.

### Expected Output
- Change summary.
- Command evidence (`test/lint` output).
- Why behavior is unchanged outside scope.

### Failure Handling
- On unexpected test failures, stop and report exact failure points.
- Do not perform destructive actions without explicit confirmation.

## Skill: `agent-evals`
### Trigger
Request to add or run agent task evaluations.

### Required Inputs
- Happy-path scenario definition.
- Failure-path scenario definition.
- Commands for deterministic validation.

### Command Flow
1. Add/extend tests with both success and expected-failure cases.
2. Keep tests deterministic and quick.
3. Wire into CI or validation scripts.

### Expected Output
- Test files and execution result log.

### Failure Handling
- If failure-path is flaky, mark as non-deterministic and replace with stable alternative.
- Escalate infra-related failures separately from logic failures.

## Skill: `agent-observability`
### Trigger
When adding tools/API entrypoints for agents.

### Required Inputs
- Endpoint or workflow name.
- Logging framework and transport.
- Identifier strategy for correlation IDs.

### Command Flow
1. Add structured logs around request parse, auth, tool execution, and result.
2. Include correlation/request ID in every emitted event.
3. Validate logs include operation name, status, and elapsed timing when feasible.

### Expected Output
- Log format examples and sample event shape.
- Verification command output.

### Failure Handling
- Ensure failure logs are emitted even on unhandled exceptions.
- If correlation ID is missing, fail loudly and include a blocking TODO.
