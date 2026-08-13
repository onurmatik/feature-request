---
name: feature-request
description: Operate FeatureRequest projects and evidence-backed request lifecycles through its authenticated MCP tools.
---

# FeatureRequest Operator

Use this skill when the user wants to collect, inspect, triage, update, implement,
or follow up on requests stored in FeatureRequest.

## Agent Contract Handoff

- This skill is a downstream operational adapter. `agent/contract.yaml` is the sole semantic
  source for tool schemas, scopes, capabilities, ownership, approvals, errors, side effects,
  idempotency, and retry behavior.
- Agent Contract 1.0.0 defines `get_account_capabilities` as the implemented bootstrap tool.
- The repository implements the full 23-tool Contract projection, including the bootstrap.
  MCP production conformance is `pending` until the immutable MCP release and real-client
  acceptance gates pass; do not present the public service as released before then.
- The flows below describe the downstream repository adapter and must not reinterpret the Contract.

## Decision Boundary

- FeatureRequest supplies stored facts, deterministic queue signals, similarity evidence,
  activity events, and controlled mutations.
- You, the calling agent, decide priority, duplicate equivalence, implementation readiness,
  and whether delivery evidence proves the requested outcome.
- Never classify a duplicate solely from a similarity score.
- Never describe a delivery artifact as verified until you inspect it with the appropriate
  repository, GitHub, CI, deployment, or release capability.
- Duplicate and delivery links do not change priority or status automatically.

## Authentication and Scope

- Connect through MCP OAuth discovery. Authorization Code + PKCE S256 is required, CIMD is
  preferred, and public-client DCR is the controlled fallback.
- Initial linking requests `read`; mutation tools trigger a `write` step-up challenge.
- Existing `fr_` FeatureRequest API tokens are for `/api` only and are rejected by `/mcp`.
- Call `get_account_capabilities` first for capability and project-limit discovery; use
  `list_projects` when owner or project context is unknown. `get_connection_context` is not exposed.
- Never expose OAuth access/refresh tokens, authorization codes, PKCE values, or API tokens.

## Triage Flow

1. Call `get_queue_snapshot` for active requests and deterministic counts/signals.
2. Read relevant requests, comments, activity, and delivery artifacts.
3. Make and explain your own priority decisions using the user's urgency and impact context.
4. Use `find_duplicate_candidates` as evidence; inspect plausible requests before linking.
5. Apply only the explicitly intended mutation and summarize its effect.

## Intake Flow

1. Normalize input into project, issue type, title, description, and current priority.
2. Search duplicate candidates before creating when enough text is available.
3. Reuse a canonical request only after semantic comparison; otherwise call `create_request`.
4. Add useful source or clarification context as a comment when needed.

## Implementation and Delivery Flow

1. Read one ready request and its activity before code changes.
2. Implement in the coding agent's current repository; FeatureRequest does not edit code.
3. Run proportionate tests and inspect resulting pull request, commit, deployment, or release.
4. Call `link_delivery_artifact` to store relevant evidence URLs.
5. Add a concise result comment when write access is available.
6. Transition to `done` or `closed` only with explicit user direction and inspected evidence.

## Project Operations

- Use focused `create_project`, `get_project`, and `update_project` tools.
- `delete_project` is destructive. Call `get_project` first, require explicit user direction,
  and pass the same id as `confirm_project_id`.

## Follow-up

- Use `list_request_changes` with the last returned cursor for incremental follow-up.
- Activity begins with the P1 event migration; do not claim it reconstructs pre-P1 history.
- Surface stale or blocked requests with evidence and a clear next action.

## Intentionally Unsupported MCP Actions

- Token creation or revocation.
- Billing or checkout.
- Bulk close or bulk mutation.
