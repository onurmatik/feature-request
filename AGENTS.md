# AGENTS Instructions

## Purpose

This file is the root-level policy for all agent activity in this repository.
It applies to all files unless a deeper `AGENTS.md` is added in a subfolder.

## Repo Overview

- Backend: `manage.py`, `config/`, `accounts/`, `projects/`, `inbox/`, `featurerequest/`
- Frontend: `frontend/`
- Database: local SQLite in repo root (`db.sqlite3`) for development only.

## Core Standards for Agents

- Prefer minimal, surgical edits.
- Keep behavior backward compatible unless migration or explicit user request requires a breaking change.
- Preserve existing conventions in each app and folder before introducing new patterns.
- Use descriptive names and avoid broad refactors unless requested.
- Do not commit secrets to source control.
- Use existing test and lint commands instead of inventing new tooling unless required.

## Editing and Execution Rules

- Use `rg` / `rg --files` for discovery and search.
- Run relevant tests after each meaningful change.
- For backend changes:
  - `python manage.py test`
  - Add/adjust tests in the relevant app's `tests.py` when behavior changes.
- For frontend changes:
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build` (for build-surface changes).
- Use Python virtual environment Python packages when available.
- Keep API/auth behavior explicit and documented in code comments only where non-obvious.

## Safety and Permissions

- Do not perform destructive operations without explicit confirmation:
  - deleting local database files, migrations, branches, or large directories
  - `flush`, `migrate --run-syncdb --fake`, `migrate` with potential destructive effects
  - mass file deletion or rewrites across unrelated paths.
- Never run destructive shell commands in bulk unless requested by the user in the same task.
- Never assume test/staging/production credentials in local `.env`; load them from the environment.
- Never print full secrets/tokens in command output.

## Logging, Tracing, and Error Reporting

- Prefer structured logs for tool/API behavior when adding new modules:
  - include an operation name
  - include a correlation/request identifier
  - include success/error status and duration when easy.
- Any new agent-facing endpoint or batch flow must include clear logging around auth decisions, auth failures, and side effects.

## Tooling and Automation Policy

- Agent flow documentation should be centralized and deterministic:
  - Keep a single manifest file at `agent.json` in repository root:
    - tool surface
    - supported auth modes/scopes
    - limits/rate assumptions
    - documentation URL pointer
- Keep one root `AGENTS.md` (this file) for global policy.
- Use one `SKILL.md` per skill directory (not one monolithic `Skills.md`).
- Skill docs must include:
  - trigger and scope
  - required inputs
  - exact command/task flow
  - expected output format
  - failure handling and fallback behavior
- Treat any `SKILL.md` or `agent.json` as part of the public contract for agents and keep updates backward compatible.

## Tests and Task Evaluations

- Add agent task evals for:
  - happy path coverage
  - failure mode/permission error path
- Keep eval inputs deterministic and lightweight.
- CI (or local equivalent) must run:
  - backend tests
  - frontend lint/build
  - relevant eval checks for changed workflow areas.

## Change Review Checklist for Agents

- Confirm changed files are scoped to the request.
- Confirm no hidden behavior regressions in auth, permissions, and data writes.
- Confirm tests (or a concrete reason for skipping) are captured in your response.
- Confirm docs were updated when agent-facing interfaces changed.

## API Contract and DX Conventions

- Keep request/response schemas explicit (input/output shape documented).
- Include examples for both failure and success paths for any new feature-facing command or endpoint.
- Add a minimal SDK/CLI path when exposing repeated agent flows:
  - documented entrypoint, required config, and expected exit conditions
  - example scripts for at least one happy path and one failure path

## Workflow Expectations

- Provide concise progress updates while making changes.
- Summaries should include:
  - what changed
  - why it changed
  - command outputs or validation evidence
  - any follow-up tasks
