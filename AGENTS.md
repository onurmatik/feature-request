# AGENTS Instructions

## Purpose

This file defines the root-level policy for agents operating in this repository.
Default mode is request management.
It applies to all files unless a deeper `AGENTS.md` exists in a subfolder.

## Repo Context

- Product: public feature request and feedback platform.
- API surface and auth contract live in `agents.json`.
- Skill/task catalog lives in `/SKILL.md`.

## Operating Model

- Treat agent work as API-only request lifecycle operations.
- Do not perform code/config edits unless the user explicitly asks for implementation work.
- Keep changes backward compatible for request workflows unless user asks otherwise.

## Core Request Management Standards

- Maintain one clear queue view for all active requests.
- Normalize incoming requests to API-backed fields:
  - `issue_id`, `owner_handle`, `project_slug`, `issue_type`, `title`, `description`, `priority`, `status`
- Deduplicate overlapping requests and keep one canonical item.
- Prioritize by urgency and impact (`P0` to `P3`) with a one-line rationale.
- For active items, include explicit next actions in output reporting.
- If a workflow field is not supported by API/model, keep it in report notes only.

## Deterministic Workflow

1. Intake: collect request data from user-provided sources.
2. Normalize: map to canonical API-backed fields.
3. Triage: assign priority and decision (`do_now`, `plan`, `delegate`, `decline`).
4. Queue management: keep ordered queue by priority and target date context.
5. Follow-up: surface stale/blocked items and escalation needs.
6. Closure: mark complete only after expected outcome is met and summarized.

## API and Permission Rules

- Respect auth mode and scope declared in `agents.json`.
- Read-only tokens must not be used for write operations.
- On `401/403`, stop and return actionable auth guidance.
- Never log or expose full secrets/tokens in outputs.

## Safety Rules

- Never run destructive operations unless user explicitly confirms in the same task.
- Never delete local database files, migrations, branches, or large directories by default.
- Never perform bulk rewrites across unrelated paths.

## Output Contract for Request Management

Agent updates should include:

- `Queue Snapshot`
- `Priority Decisions`
- `Active Follow-ups`
- `Risks and Blockers`
- `Next Checkpoint`

Queue format:

`issue_id | summary | priority | status | owner_handle/project_slug | next action`

## Source-of-Truth Policy

- Keep `agents.json` as the canonical machine-readable agent contract.
- Keep `SKILL.md` as the canonical skill/task flow document.
- Keep both files aligned when request lifecycle behavior changes.

## Change Review Checklist

- Confirm changes are scoped to the user request.
- Confirm auth/scope behavior remains explicit and correct.
- Confirm data-write side effects are intentional.
- Confirm request-management docs/contracts are updated together when needed.

## Workflow Expectations

- Provide concise progress updates while working.
- In summaries, include:
  - what changed
  - why it changed
  - any validation evidence (or why validation was skipped)
  - follow-up tasks, if any
