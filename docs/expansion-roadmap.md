# Expansion Roadmap Based on Multi-Plane State Encoding

This roadmap ties the telemetry-style state variables (amount, timing, ordering, repetition, input size, output structure, fee invariance, block interval alignment, cluster symmetry) to concrete edits in the repository. Each subsection lists proposed expansions and the files / sections that should host them.

## 1. README.md — Multi-Plane Quick Reference
- Add a **"State Planes"** table summarizing how amount, fee, cardinality, topology, and block placement act as orthogonal channels.
- Include a short **"Telemetry vs. Cipher"** comparison that frames Enigmatic as state synchronization rather than substitution ciphers.
- Provide links to relevant specs (e.g., Value plane → `specs/02-encoding-primitives.md`, Formal model → `specs/03-formal-model.md`).

## 2. specs/02-encoding-primitives.md — Variable Mapping Enhancements
- Extend §2.1–§2.5 with explicit mappings for the observed variables:
  - **Timing** → add a new subsection on *block interval encoding* with examples like "∆height = 3 → heartbeat".
  - **Ordering & repetition** → define canonical transaction ordering rules and repeated value motifs (e.g., alternating 11.11 / 7.00 headers) to signal consensus states.
  - **Cluster symmetry** → document how mirrored input/output values encode swarm formations.
- Introduce a table of **reserved dialect markers** that show how combinations across planes yield higher-level symbols (e.g., Value 21.21 + Fee 0.21 + m=n=21 → `FRAME_SYNC`).

## 3. specs/03-formal-model.md — State Vector Formalization
- After Definition 3.2, add a **state vector definition**: \( \mathbf{s}(t) = (v, f, m, n, \Delta h, \sigma) \) capturing amount, fee, cardinality, block spacing, and symmetry flags.
- Provide lemmas showing how orthogonality between vector components enables parallel message streams.
- Add an example proof sketch for *multi-agent state synchronization* that references telemetry variables.

## 4. specs/04-encoding-process.md — Dialect-Aware Workflow
- Flesh out Step 3 with a checklist that ties each variable to encoding decisions (e.g., choose `∆height` cadence before assigning fees).
- Insert a new §4.4 **"Telemetry Dialects"** section describing how to build reusable configs for heartbeats, consensus proofs, and swarm negotiation.
- Document automation hooks (YAML/JSON dialect files) that map raw messages into multi-plane targets.

## 5. specs/05-decoding-process.md — Observer Playbooks
- Add discovery heuristics for spotting telemetry streams: sliding-window fee band detection, symmetry scoring for clusters, and block-interval monitors.
- Provide pseudo-code for reconstructing state vectors and validating timing / ordering constraints.
- Include an appendix with a worked example that mirrors the README quick reference.

## 6. specs/06-security-model.md & specs/section7.md — Detectability & Noise
- Expand the adversary model with **state-plane fingerprinting** attempts (e.g., statistical detection of 21.21 headers) and mitigation guidance.
- Describe how fee jitter (ε) and randomized ordering preserve indistinguishability without breaking decoder expectations.
- Reconcile Section 6 (skeleton) with `specs/section7.md` by either merging or cross-referencing their overlapping threat analyses.

## 7. Examples Directory — Telemetry Walkthroughs
- Replace placeholders in `examples/example-transaction-pattern.md` and `examples/example-decoding-flow.md` with concrete scenarios that illustrate a telemetry heartbeat and a swarm negotiation cycle.
- Add tables showing each transaction’s amount, fee, cardinality, block height delta, and interpreted symbol.
- Ensure examples link back to the state vector formalism introduced in §3.

## 8. New Supporting Files
- **`specs/08-dialects.md`**: Define how dialect configs declare plane usage, reserved markers, and timing cadences.
- **`examples/dialect-heartbeat.yaml`**: Machine-readable sample that the encoder/decoder skeletons can load when automation tooling is built.

---
By applying these edits, the repository will reflect the telemetry-style, multi-variable communication model described in the recap, giving contributors clear targets for documentation and future implementation work.
