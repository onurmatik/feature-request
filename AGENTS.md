# AGENTS Instructions

## Purpose

This file defines the root-level policy for agents operating in this repository.
Default mode is request management.
It applies to all files unless a deeper `AGENTS.md` exists in a subfolder.

## Repo Context

- Product: public feature request and feedback platform.
- Agent semantics live exclusively in `agent/contract.yaml` and are validated by
  `agent/contract.schema.json` plus the versioned files under `agent/conformance/`.
- `agents.json` is a downstream environment/API/MCP adapter and projection; it is not an
  independent source for tool, authorization, approval, entitlement, error, or retry semantics.
- `/.agents/skills/feature-request/SKILL.md` and `skills/feature-request/SKILL.md` are downstream
  operational views of the Contract. They may explain workflows but must not redefine it.

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

- Use `agent/contract.yaml` for normative agent scope and authorization semantics; use
  `agents.json` only to resolve the current API/MCP environment and implemented adapter surface.
- Treat Agent Contract 1.0.0 MCP conformance as pending until the downstream MCP gate passes.
  In particular, do not claim that the target `get_account_capabilities` bootstrap tool or the
  Contract's mutation schemas are available in the current runtime before that gate passes.
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

- Keep `agent/contract.yaml` as the sole canonical, machine-readable source for agent behavior.
- Treat `agents.json`, MCP metadata, standalone skills, and plugin artifacts as generated,
  mapped, or verified downstream adapters. They must not silently reinterpret Contract semantics.
- The Contract bootstrap target is `get_account_capabilities`; its scopes and behavior are read
  from the Contract rather than copied into downstream policy documents.
- Keep downstream projections aligned through the Contract gate. A changed projection without a
  matching Contract change, or a claimed runtime feature without MCP conformance, is a failure.

## Change Review Checklist

- Confirm changes are scoped to the user request.
- Confirm normative auth/scope behavior is owned by `agent/contract.yaml` and remains explicit.
- Confirm downstream adapters reference or mechanically project Contract values without redefining
  them, and report MCP conformance as `pending` until its separate runtime gate passes.
- Confirm data-write side effects are intentional.
- Confirm request-management docs/contracts are updated together when needed.

## Workflow Expectations

- Provide concise progress updates while working.
- In summaries, include:
  - what changed
  - why it changed
  - any validation evidence (or why validation was skipped)
  - follow-up tasks, if any
