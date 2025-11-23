# Enigmatic — A Layer-0 Communication Protocol
**DigiByte-Optimized Edition**

> This Markdown mirrors the evolving IEEE-style PDF and stays aligned with the
> repository’s specs, tooling, and examples. TODO markers indicate where
> diagrams and formal proofs will be added before publication.

## 1. Introduction

Enigmatic is a Layer-0 communication protocol that treats DigiByte transactions
as **state vectors** across multiple planes (value, fee, cardinality, topology,
block placement, and optional auxiliary metadata). Under an agreed **dialect**,
the joint distribution of these planes expresses **symbols** and multi-frame
messages without changing DigiByte consensus rules or wallet semantics.

The project combines:

- Formal specifications in [`../specs/`](../specs) describing each state plane
  and the encoding/decoding functions.
- A reference Python stack in [`../enigmatic_dgb/`](../enigmatic_dgb) that keeps
  the encoder, planner, transaction builder, watcher, and CLI aligned with the
  specs.
- Replayable dialects and decoded walkthroughs in [`../examples/`](../examples)
  plus reproducible RPC experiments in [`rpc_test_plan.md`](rpc_test_plan.md).

## 2. Architecture Overview

- **Protocol layer** – Defines the message space \(\mathcal{M}\), state planes,
  and dialect composition (see `../specs/01-protocol-overview.md` and
  `../specs/02-encoding-primitives.md`).
- **Encoding/decoding logic** – Maps intents to state vectors via
  \(\mathcal{E}(M) \rightarrow t\) and reconstructs intents via
  \(\mathcal{D}(t) \rightarrow M'\) (`../specs/03-formal-model.md`).
- **Reference implementation** – `planner.py`, `tx_builder.py`, `encoder.py`,
  `decoder.py`, and `watcher.py` ensure every state plane is executable and
  testable (`tests/`).
- **Tooling surface** – `enigmatic_dgb/cli.py` provides `plan-symbol`,
  `plan-chain`, `plan-sequence`, `send-symbol`, `send-message`, and watcher
  commands for both dry-run and broadcast workflows.

<!-- TODO: insert block-placement timing diagram showing Δheight coordination across frames -->

## 3. Formal Model & State Planes

The state vector for a transaction \(t\) is
\(\mathbf{s}(t) = (v, f, m, n, \tau, \sigma, a)\), where:

- \(v\): value plane anchors and repetition headers.
- \(f\): fee punctuation / jitter bands.
- \(m, n\): input/output cardinalities (and symmetry across them).
- \(\tau\): topology motifs and ordering windows.
- \(\sigma\): block-placement cadence (height deltas, repetition across frames).
- \(a\): auxiliary metadata (OP_RETURN or commitments when present).

Encoding deterministically maps an intent to \(\mathbf{s}(t)\), and decoding
reconstructs intents from observed planes. The proofs of determinism,
orthogonality between planes, and decoder completeness live in
[`../specs/03-formal-model.md`](../specs/03-formal-model.md) and
[`../specs/04-encoding-process.md`](../specs/04-encoding-process.md).

<!-- TODO: add lemma/proof sketch illustrating orthogonality of planes for multi-channel multiplexing -->

## 4. Encoding Process & Dialects

- Dialects (`../specs/06-dialects.md`) map **symbols** to one or more **frames**
  (transactions) by declaring constraints on each state plane.
- `planner.py` resolves those constraints into concrete UTXO selections and
  change choreography, preserving input/output symmetry and dust compliance.
- `tx_builder.py` realizes the frame with deterministic output ordering and
  optional OP_RETURN hints.
- `plan-symbol`, `plan-chain`, and `plan-pattern` expose dry-run views so
  auditors can diff the planned state vector before a broadcast.

Dialect authors iterate on YAML files in `../examples/` using the planner to
validate fee punctuation, block spacing, and cardinality before any funds move.

<!-- TODO: insert dialect lifecycle diagram (draft → dry-run → broadcast) -->

## 5. Decoding & Observability

- `decoder.py` and `watcher.py` reconstruct state vectors from raw transactions
  and chain them into frames using block placement and change-linking
  heuristics.
- `enigmatic-dgb watch` streams decoded packets for a target address; decoded
  flows in `../examples/example-decoding-flow.md` mirror these mechanics.
- Detection heuristics (fee band clustering, symmetry scores, Δheight cadence)
  are catalogued in [`../specs/05-decoding-process.md`](../specs/05-decoding-process.md).

<!-- TODO: add detection playbook diagram showing sliding-window fee/height analysis -->

## 6. Use Cases

- **Presence and identity beacons** – Heartbeats and HELLO/PRESENCE frames from
  `dialect-heartbeat.yaml` and `dialect-intel.yaml` (replayable via CLI).
- **Operational telemetry** – Multi-frame chains with deterministic fees and
  block-spacing for pipeline checkpoints.
- **Swarm negotiation** – Symmetric cardinality/topology patterns indicating
  quorum formation or consensus-ready states.
- **Covert session bootstrap** – Optional payload encryption plus OP_RETURN
  commitments to coordinate shared secrets before higher-layer messaging.

## 7. Security, Deniability, and Detection

- **Plausible deniability** – Transactions remain economically rational; fee and
  value choices stay within normal wallet behavior. See
  [`../specs/06-security-model.md`](../specs/06-security-model.md).
- **Adversary model** – Observers may attempt state-plane fingerprinting
  (fee/value band detection, symmetry scoring). Mitigations include jitter bands
  and dialect rotation.
- **Verification surface** – Dry-run planners emit the exact inputs/outputs and
  Δheight expectations, enabling pre-broadcast audits. TODO: formalize the
  indistinguishability bounds for fee jitter.

## 8. Implementation Status (Repository Alignment)

- Specs chapters 01–06 define the planes, model, encoding/decoding processes,
  dialects, and security assumptions.
- Python modules under `enigmatic_dgb/` implement the encoder, planner, builder,
  and watcher used in the examples and tests.
- CLI commands in `enigmatic_dgb/cli.py` expose `plan-symbol`, `plan-chain`,
  `plan-sequence`, `send-symbol`, `send-message`, and watchers documented in
  [`../docs/TOOLING.md`](TOOLING.md).
- Examples in `../examples/` include dialect YAML files, decoded traces, and
  walkthroughs that can be reproduced with the RPC test plan.

## 9. Planned Enhancements

Roadmap items tracked in [`expansion-roadmap.md`](expansion-roadmap.md):

- Production-grade wallet/RPC integrations and hardware-wallet signing flows.
- Multi-chain experiments while keeping DigiByte the reference substrate.
- Community dialect registry with linting and replay fixtures.
- Analytics and detection dashboards for state-plane observation.
- Pattern detection frameworks for automated threat modeling.

<!-- TODO: insert appendix with formal security proof outline and notation table -->
