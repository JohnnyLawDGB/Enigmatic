# Project Context and Worklist (Persistent)

## Purpose
Build a hybrid AI system that combines a conversational chat interface with an
always-on event-driven agent. The agent should respond to user requests and
autonomously monitor events (e.g., transactions), applying rules, triggering
alerts, and executing safe, policy-bound actions.

## Current State (From PDF)
- Basic chat UI exists with limited backend support.
- Backend capabilities are only partially integrated; not autonomous.
- No continuous event monitoring or proactive actions yet.

## Target Capabilities
- Natural language requests that map to concrete actions or queries.
- Always-on event monitoring that reacts in real time.
- Multi-step workflows (log, alert, act) with context retention.
- Policy/safety layer for confirmations and guardrails.
- Shared state between chat and event modules.

## Proposed Architecture (High-Level)
- Front-End Chat UI: user interaction, receives proactive notifications.
- Backend AI Agent (single service initially):
  - Conversational Module: parses requests, triggers actions, returns answers.
  - Event Monitoring Module: subscribes/polls events, runs rules, triggers actions.
- Integration Layer:
  - Event Sources (RPC/WebSocket/polling).
  - Action Executors (on-chain or external API actions).
  - State Management (recent events, preferences, audit).
  - Policy Engine (approvals, thresholds, allowlists).

## State and Safety
- Maintain recent events, pending approvals, and user preferences.
- Ensure idempotency (do not handle the same event twice).
- Require confirmations for high-risk actions or above thresholds.
- Log all autonomous actions with metadata for auditability.

## Development Workflow (Condensed)
1. Local setup with test data and stubs for event sources.
2. Build event monitoring loop with rules and alerting.
3. Build conversational command parsing and intent dispatch.
4. Integrate modules and shared state.
5. Local tests (unit + integration + edge cases).
6. Deploy to VPS with process manager and monitoring.
7. Connect UI for live alerts and confirmations.

## Worklist (Scaffolded)
### Phase 1: Baseline Foundations
- Define canonical event schema and action interfaces.
- Implement state store (in-memory + optional persistence).
- Set up logging and audit trail structure.

### Phase 2: Event Monitoring MVP
- Build event source adapters (polling or WebSocket).
- Implement rule engine (thresholds, watchlists, patterns).
- Add idempotency and alert debouncing.

### Phase 3: Conversational MVP
- Intent parser (keyword/regex, upgrade to LLM later).
- Command dispatcher to backend functions.
- Clarification flow for ambiguous requests.

### Phase 4: Integration and Policies
- Shared state wiring between chat and event modules.
- Policy checks and confirmation flow.
- Notification pathway to UI (alerts + actions).

### Phase 5: Testing and Hardening
- Unit tests for rule evaluation and parsing.
- Integration tests with simulated event streams.
- Failure handling and retries (safe defaults).

### Phase 6: Deployment
- VPS setup, env config, process management.
- Health checks and uptime monitoring.
- Observability (logs, metrics, alerting).

## Open Decisions / Inputs Needed
- Event sources and target chain(s) to support first.
- Chat UI integration mechanism (REST vs WebSocket).
- Policy defaults (thresholds, allowlists, approvals).
- Persistence choice (SQLite vs PostgreSQL vs in-memory).

## Notes
- Prioritize safe autonomy: default to notify and request confirmation.
- Keep modules decoupled; expose clean interfaces for later expansion.
