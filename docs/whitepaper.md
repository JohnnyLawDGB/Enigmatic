# Enigmatic — A Layer-0 Communication Protocol  
**DigiByte-Optimized Edition**

> This Markdown file mirrors the structure of the IEEE-style PDF whitepaper and
> serves as the canonical, Git-friendly version of the specification text.

## 1. Introduction

Enigmatic is a Layer-0, chain-native communication protocol that encodes
structured messages into DigiByte transactions without requiring any change to
consensus rules.

Transactions remain valid and economically meaningful, but when interpreted
under the Enigmatic ruleset, they also form a **steganographic message stream**.

The project ships with three coordinated pillars that keep the theory and the
implementation in lockstep:

1. **Protocol specifications** in `../specs/` describe the state planes (value,
   fee, cardinality, topology, block placement, auxiliary metadata) and the
   deterministic mapping between state vectors and intents.
2. **Reference tooling** in `../enigmatic_dgb/` exposes the encoder, decoder,
   planner, RPC utilities, and CLI so that reproducible transactions can be
   generated directly from the documented primitives.
3. **Dial tone examples and lab notebooks** in `../examples/` and
   `../docs/rpc_test_plan.md` demonstrate how real DigiByte transactions exhibit
   the motifs described in the specs.

This whitepaper mirrors the content in [`README.md`](../README.md) and
`docs/ARCHITECTURE.md` so contributors can trust that every workflow described
here exists in the repository.


## 2. Background and Design Rationale

- **DigiByte UTXO model.** UTXO selection provides discrete, inspectable
  components that can be repurposed as state variables. Enigmatic leans on
  deterministic coin control to express repetition, symmetry, and anchoring via
  the transaction graph.
- **Value precision and dust thresholds.** The fee punctuation (`0.21`,
  `0.152`, etc.) referenced in the README comes from DigiByte's high-precision
  outputs and generous dust threshold, allowing encoded values to remain
  economically sane while still conveying beacons.
- **Block cadence and multi-algo mining.** Average block intervals plus the
  randomness introduced by five mining algorithms create enough timing entropy
  to place heartbeats across the block height plane without requiring explicit
  wall-clock synchronization.

Together these properties make DigiByte an ideal substrate for the state plane
approach that Enigmatic formalizes in `../specs/02-encoding-primitives.md` and
`../specs/03-formal-model.md`.

## 3. Formal Model

The whitepaper follows the same structure as the spec chapter:

1. Define the message space \\\( \mathcal{M} \\\) and the state vector components.
2. Introduce the encoding function \\\( \mathcal{E}(M) \rightarrow t \\\) which maps intents to
   concrete DigiByte transactions by selecting amounts, fees, and topology
   constraints.
3. Describe the decoding function \\\( \mathcal{D}(t) \rightarrow M' \\\) which recovers
   intents from ledger observations by inspecting all state planes.

Readers who want the formal notation, invariants, and proofs should jump to
[`../specs/03-formal-model.md`](../specs/03-formal-model.md), while this document
maintains a narrative explanation that mirrors the README quick references.

## 4. Reference Stack and Tooling

Every section of the README has a direct tooling counterpart:

- `enigmatic_dgb/cli.py` exposes `enigmatic-dgb` commands such as
  `plan-symbol`, `plan-chain`, `plan-pattern`, and `send-sequence`. Each command
  accepts the planner arguments and confirmation guards documented in the
  README's "Unified CLI Workflows" section.
- `enigmatic_dgb/planner.py`, `enigmatic_dgb/tx_builder.py`, and
  `enigmatic_dgb/rpc_client.py` keep UTXO selection, change choreography, and
  RPC interactions deterministic across dry runs and broadcasts. The
  whitepaper's state plane discussion is therefore testable via `pytest` and the
  examples.
- `enigmatic_dgb/decoder.py` and `enigmatic_dgb/watcher.py` supply the telemetry
  decoders referenced in `examples/example-decoding-flow.md`, proving that the
  transaction motifs shown in the paper can be observed directly from the
  blockchain.

`docs/rpc_test_plan.md` documents the precise CLI commands and RPC assumptions
used during live dial tone tests so reviewers can reproduce the sequences cited
in the narrative.

## 5. Documentation Alignment

- [`README.md`](../README.md) introduces the state plane framing, quickstart, and
  CLI workflows. Each table and example links to the corresponding spec chapter
  or example dialect.
- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) zooms into the same modules listed
  above, ensuring that engineers jumping in from the whitepaper can find the
  correct implementation file.
- [`docs/README.md`](README.md) and the files under `../specs/` define the
  eight-part specification that this paper references section-by-section.
- [`examples/README.md`](../examples/README.md) keeps the chain of custody
  between dial tone YAML files, CLI invocations, and decoded interpretations so
  the lab exercises in this whitepaper stay verifiable.

Maintaining this alignment ensures the README, specs, and whitepaper reinforce
one another: the README gives quick starts, the specs provide rigor, and the
whitepaper ties both to the available tools.

---

