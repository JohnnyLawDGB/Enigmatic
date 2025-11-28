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

## 2. Historical Lineage: Steganography, Enigma, and Blockchain Signalling

### 2.1 Ancient ink and shaved heads

Steganography hides the **existence** of a message, while cryptography hides
its **meaning**. A classic example from Herodotus recounts Histiaeus having a
message tattooed onto a servant’s shaved scalp; only after the hair regrew was
the courier dispatched, and the recipient revealed the hidden text by shaving
the head again. Other early tactics—ink under wax tablets, invisible ink on
letters, and later microdots—show how ordinary objects can carry covert
structure.

### 2.2 Enigma and the birth of modern codebreaking

The World War II **Enigma** machine was a German electro-mechanical cipher
device whose rotor and plugboard settings scrambled radio traffic into
apparently meaningless character streams. Polish cryptanalysts opened the door
before the war, and British teams at Bletchley Park (including Alan Turing)
scaled the effort with “bombes” and crib-driven searches. Breaking Enigma is
credited with shortening the war by years. **Enigmatic** nods to this heritage:
we are not re-implementing Enigma, but we draw inspiration from mathematically
structured signalling that rides atop “ordinary” traffic. Our goal is
ledger-native signals whose state vectors look like normal DigiByte activity
unless you possess the dialect to decode the symbols and frames.

### 2.3 Whispers in the blockchain

As media turned digital, steganography moved into pixels and audio samples, and
ARGs/CTFs like Cicada 3301 layered clues across files and QR codes. Blockchains
extended the tradition: Satoshi Nakamoto embedded “The Times 03/Jan/2009
Chancellor on brink of second bailout for banks” in Bitcoin’s genesis block as
both timestamp and commentary. Users later leaned on OP_RETURN and structured
transaction patterns to place poems, keys, coordinates, and puzzle trails
on-chain.

### 2.4 How this frames Enigmatic

Enigmatic threads these stories together: classical steganography shows that
“you only notice the message if you know where to look”; Enigma illustrates
mathematically rich signalling over mundane channels; blockchain puzzles prove
ledgers can carry layered meaning. Enigmatic generalizes this for DigiByte by
using state planes—value, fee punctuation, cardinality symmetry, topology, and
block-placement cadence—as the signalling medium. Casual observers see valid,
economical transactions; holders of the dialect interpret structured symbols
and frames. The aim is not to romanticize spycraft, but to continue the long
tradition of communicating in plain sight with rigor and plausible deniability.

## 3. Architecture Overview

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

## 4. Formal Model & State Planes

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

## 5. Encoding Process & Dialects

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

## 6. Decoding & Observability

- `decoder.py` and `watcher.py` reconstruct state vectors from raw transactions
  and chain them into frames using block placement and change-linking
  heuristics.
- `enigmatic-dgb watch` streams decoded packets for a target address; decoded
  flows in `../examples/example-decoding-flow.md` mirror these mechanics.
- Detection heuristics (fee band clustering, symmetry scores, Δheight cadence)
  are catalogued in [`../specs/05-decoding-process.md`](../specs/05-decoding-process.md).

<!-- TODO: add detection playbook diagram showing sliding-window fee/height analysis -->

## 7. Taproot Inscriptions (Enigmatic Taproot Dialect v1)

Taproot inscriptions in Enigmatic embed a compact envelope inside a Taproot
script path without altering DigiByte consensus. The Enigmatic Taproot dialect
adds a short header—`ENIG` magic, a one-byte version, a length-prefixed content
type, and raw payload bytes—inside an `OP_FALSE OP_IF ... OP_ENDIF` branch so
the payload is revealed only when that path is exercised. Wallets spend or
decode the output like any other Taproot script; observers without the dialect
see a standard Taproot leaf with data-bearing pushes. Payloads should remain
small (≤520 bytes for a single script element) to stay relay-safe and avoid
policy rejections. The CLI surfaces this flow via `ord-plan-taproot` for dry
runs, `ord-inscribe --scheme taproot` for signing/broadcasting, and
`ord-decode` for inspection, all aligned with the dialect spec.

## 8. Use Cases

- **Presence and identity beacons** – Heartbeats and HELLO/PRESENCE frames from
  `dialect-heartbeat.yaml` and `dialect-intel.yaml` (replayable via CLI).
- **Operational telemetry** – Multi-frame chains with deterministic fees and
  block-spacing for pipeline checkpoints.
- **Swarm negotiation** – Symmetric cardinality/topology patterns indicating
  quorum formation or consensus-ready states.
- **Covert session bootstrap** – Optional payload encryption plus OP_RETURN
  commitments to coordinate shared secrets before higher-layer messaging.

## 9. Security, Deniability, and Detection

- **Plausible deniability** – Transactions remain economically rational; fee and
  value choices stay within normal wallet behavior. See
  [`../specs/06-security-model.md`](../specs/06-security-model.md).
- **Adversary model** – Observers may attempt state-plane fingerprinting
  (fee/value band detection, symmetry scoring). Mitigations include jitter bands
  and dialect rotation.
- **Verification surface** – Dry-run planners emit the exact inputs/outputs and
  Δheight expectations, enabling pre-broadcast audits. TODO: formalize the
  indistinguishability bounds for fee jitter.

## 10. Implementation Status (Repository Alignment)

- Specs chapters 01–06 define the planes, model, encoding/decoding processes,
  dialects, and security assumptions.
- Python modules under `enigmatic_dgb/` implement the encoder, planner, builder,
  and watcher used in the examples and tests.
- CLI commands in `enigmatic_dgb/cli.py` expose `plan-symbol`, `plan-chain`,
  `plan-sequence`, `send-symbol`, `send-message`, and watchers documented in
  [`../docs/TOOLING.md`](TOOLING.md).
- Examples in `../examples/` include dialect YAML files, decoded traces, and
  walkthroughs that can be reproduced with the RPC test plan.

## 11. Recent Updates (last 4 days)

- Added a Taproot inscription lab with step-by-step wallet setup, payload size
  guidance, and troubleshooting for relay policy edge cases and malformed
  outputs to speed up experimentation on DigiByte Taproot wallets.
- Hardened ordinal inscription workflows with clearer fee caps, address
  validation errors, and explicit broadcast toggles so operators can dry-run
  Taproot inscriptions before committing transactions on-chain.

## 12. Planned Enhancements

Roadmap items tracked in [`expansion-roadmap.md`](expansion-roadmap.md):

- Production-grade wallet/RPC integrations and hardware-wallet signing flows.
- Multi-chain experiments while keeping DigiByte the reference substrate.
- Community dialect registry with linting and replay fixtures.
- Analytics and detection dashboards for state-plane observation.
- Pattern detection frameworks for automated threat modeling.

<!-- TODO: insert appendix with formal security proof outline and notation table -->
