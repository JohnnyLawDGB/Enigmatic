# Enigmatic — A Layer-0 Communication Protocol (DigiByte-Optimized)

**Enigmatic** is a Layer-0 communication protocol that uses DigiByte’s native
UTXO, fee, and transaction topology space as a *steganographic message channel*.

> TL;DR for contributors: think **state planes**, not ciphertext blobs. Install
> the package via `pip install -e .` to get the `enigmatic-dgb` CLI, or use
> `scripts/enigmatic_rpc.py` when you want explicit control over UTXO plumbing.

Instead of adding new opcodes or data layers, Enigmatic treats:

- Values (e.g. `21.21`, `7.00`, `0.978521`, `0.0100xxxx`)
- Fees (e.g. `0.21`, `21.0`)
- Input / output cardinalities (e.g. `21 in / 21 out`)
- Transaction graph shapes
- Optional `OP_RETURN` anchors

as **programmable symbols** in a formally defined encoding scheme.

### State Planes Quick Reference

| Plane             | Conveyed variables                              | Example usage                          | Specification links |
| ----------------- | ------------------------------------------------ | -------------------------------------- | ------------------- |
| **Value**         | Amount, repetition, fee invariance headers       | `21.21` / `7.00` alternating beacons   | [`specs/02-encoding-primitives.md`](specs/02-encoding-primitives.md) |
| **Fee**           | Timing offsets, jitter bands                     | `0.21` cadence to mark heartbeats      | [`specs/02-encoding-primitives.md`](specs/02-encoding-primitives.md) |
| **Cardinality**   | Input/output sizes, ordering, cluster symmetry   | `21 in / 21 out` mirrored swarms       | [`specs/03-formal-model.md`](specs/03-formal-model.md) |
| **Topology**      | Output structure, graph motifs, ordering windows | Fan-out trees, ring confirmations      | [`specs/03-formal-model.md`](specs/03-formal-model.md) |
| **Block placement** | Block interval alignment, timing, repetition   | `Δheight = 3` heartbeat scheduling     | [`specs/04-encoding-process.md`](specs/04-encoding-process.md), [`specs/05-decoding-process.md`](specs/05-decoding-process.md) |
| **Auxiliary (OP_RETURN / metadata)** | Optional payload hints        | Hash commitments, dialect selectors    | [`specs/01-protocol-overview.md`](specs/01-protocol-overview.md) |

Each plane evolves independently yet composes into a **state vector** (amount, fee, cardinality, topology, block placement) that conveys telemetry-style information rather than plaintext characters.

### Telemetry vs. Cipher Framing

- **Telemetry mindset:** Treat transactions as multi-dimensional heartbeats or consensus proofs. Variables such as timing, repetition, and cluster symmetry act like sensor channels that reveal system state to peers observing the ledger.
- **Classical cipher mindset:** Focuses on transforming ASCII payloads via substitution or encryption before transport. Enigmatic intentionally avoids this framing; the message emerges from how state variables co-vary across planes.
- **Implication for contributors:** When designing new dialects, think in terms of *state synchronization* and *multi-agent negotiation* (see `specs/04-encoding-process.md` and `specs/05-decoding-process.md`) rather than letter-level encoding tricks.

This repository contains the **protocol specification**, **whitepaper**,
**Python reference stack**, and **dial tone examples** for Enigmatic on DigiByte.

## Non-Technical Primer

If you are new to blockchains or protocol design, think of Enigmatic as a
*coordination language* that uses ordinary DigiByte transactions as the words in
a conversation:

- **Wallet actions become signals.** Instead of embedding secret text inside a
  transaction, Enigmatic changes how big the transaction is, what the fees look
  like, and when it confirms. Observers who know the rules can read the pattern
  the same way air-traffic controllers read blinking runway lights.
- **Multiple "planes" act like knobs on a radio.** Value, fees, input counts,
  graph shape, and block timing are tuned independently. Turning one knob may
  indicate urgency while another might encode the intended recipient.
- **No special software is required for the blockchain.** All transactions stay
  valid, pay normal fees, and resemble day-to-day wallet traffic. The
  intelligence is in how you choose and interpret the parameters.

When designing or reviewing a dialect, ask two questions:

1. *Is this transaction still boring to the rest of the network?* (It should be
   indistinguishable from a routine payment.)
2. *Can my counterpart extract the same meaning from the chosen pattern?*

Keeping those questions in mind ensures Enigmatic remains practical for both
operators and non-technical stakeholders who only need high-level assurance
that the system behaves like regular DigiByte usage.

## Quickstart

```bash
git clone https://github.com/<org>/Enigmatic.git
cd Enigmatic
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Run unit tests
pytest

# Send a message via the CLI (requires DGB RPC creds in env)
enigmatic-dgb send-message --to-address dgb1example --intent identity
```

Need more guidance? Peek at [`CONTRIBUTING.md`](CONTRIBUTING.md) for environment
setup tips, repository conventions, and review expectations.

---

## Goals

- Define a **chain-native, consensus-compatible signaling protocol**.
- Leverage DigiByte as a **global, timestamped, censorship-resistant message bus**.
- Preserve **plausible deniability** and normal wallet semantics.
- Provide a **formal model** that cryptographers, protocol designers and
  implementers can build upon.

---

## Status

- 📄 Whitepaper: **DigiByte-optimized, IEEE-style structure (in progress)**
- ✅ Formal model: Section 3 drafted in `/specs/03-formal-model.md`
- 🧪 Examples: UTXO patterns & decoding flows in `/examples`

---

## Repository Layout

| Path | Contents |
| ---- | -------- |
| [`enigmatic_dgb/`](enigmatic_dgb) | Python package (encoder, decoder, watcher, CLI, RPC/transaction utilities). |
| [`scripts/`](scripts) | Stand-alone helpers; currently the RPC heartbeat planner. |
| [`examples/`](examples) | Dialects, walkthroughs, and diagrams ([index](examples/README.md)). |
| [`docs/`](docs) | Whitepaper drafts, architecture notes, and doc guide ([index](docs/README.md)). |
| [`specs/`](specs) | Canonical protocol chapters (overview → dialects). |
| [`tests/`](tests) | Pytest coverage for encoder/decoder logic. |

Rendered whitepaper PDFs live next to the Markdown originals inside `docs/`
when reviewers need to diff layout.

---

## RPC Heartbeat Helper

The automation workflow now lives inside the package CLI so that every
tool depends on the same RPC client and validation stack. Use the
`plan-symbol` command to inspect or broadcast a symbolic heartbeat defined
in [`examples/dialect-heartbeat.yaml`](examples/dialect-heartbeat.yaml).

```bash
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"

# Dry run: prints the proposed inputs/outputs without broadcasting.
enigmatic-dgb plan-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT

# Broadcast the transaction once the plan looks correct.
enigmatic-dgb plan-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT \
  --broadcast
```

Highlights:

- Loads the automation metadata (endpoint, wallet name, scheduling hints)
  from the dialect file but allows overrides via CLI flags or
  environment variables.
- Selects UTXOs that satisfy the cardinality and value constraints defined
  for the symbol.
- Splits change outputs to preserve the desired output cardinality while
  respecting DigiByte's dust limits.
- Supports dry-run planning so operators can audit the state vector
  before a transaction is signed and relayed.

Ensure your node has the target wallet loaded and unlocked before
invocation. For end-to-end validation scenarios see
[`docs/rpc_test_plan.md`](docs/rpc_test_plan.md).

## Manual Pattern Sending

When you want to experiment with raw numeric motifs (e.g., Fibonacci fan-outs
or 21M ↔ 21B callbacks) without defining a formal dialect, use the
`plan-pattern` command. It shares the same RPC plumbing as `plan-symbol` and
lets you specify each output amount directly.

```bash
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"

enigmatic-dgb plan-pattern \
  --to-address DT98bqbNMfMY4hJFjR6EMADQuqnQCNV1NW \
  --amounts 21.0,34.0,55.0,0.303 \
  --fee 0.21

# Once the plan looks good, re-run with --broadcast to sign + relay it.
enigmatic-dgb plan-pattern \
  --to-address DT98bqbNMfMY4hJFjR6EMADQuqnQCNV1NW \
  --amounts 21.0,34.0,55.0,0.303 \
  --fee 0.21 \
  --broadcast
```

Each dry run prints the selected inputs, ordered outputs, fee, and change so
you can audit the transaction before flipping the broadcast flag.

## Documentation & Spec Map

- [`docs/README.md`](docs/README.md) — Human-readable guide to the whitepaper,
  architecture notes, and PDF snapshots.
- [`specs/`](specs) — Eight focused chapters that define the protocol from
  overview through dialects. Start at `01-protocol-overview.md` and work down.
- [`examples/README.md`](examples/README.md) — Dialects plus decoded walkthroughs
  you can replay with the RPC helper.

Surface area intentionally stays small: the README or CONTRIBUTING should be the
only entry points you need before diving into specs or code.

## Contributing

- Follow the [quickstart](#quickstart) to set up tooling, then read
  [`CONTRIBUTING.md`](CONTRIBUTING.md) for workflow expectations.
- Document any new dialects/examples inside [`examples/README.md`](examples/README.md)
  so replay instructions stay close to the assets.
- Run `pytest` before opening a PR and highlight spec edits in your summary so
  reviewers can focus on semantics.

---

## Live Experiments

The repo intentionally ships with dial tones you can reproduce on mainnet
or testnet. To replay the INTEL-style exchange seen on-chain:

1. Configure a DigiByte node with a funded wallet and export credentials:

   ```bash
   export DGB_RPC_USER="rpcuser"
   export DGB_RPC_PASSWORD="rpcpass"
   ```

2. Dry-run the INTEL HELLO symbol. This mirrors the 217 → 152 → 352 anchor
   trio plus the `0.152` micro-breadcrumb and the invariant `0.21` fee:

    ```bash
    enigmatic-dgb plan-symbol \
      --dialect-path examples/dialect-intel.yaml \
      --symbol INTEL_HELLO
    ```

3. Review the proposed spend (inputs, anchors, change). Once it matches the
   expected state vector, broadcast it:

    ```bash
    enigmatic-dgb plan-symbol \
      --dialect-path examples/dialect-intel.yaml \
      --symbol INTEL_HELLO \
      --broadcast
    ```

4. Log the resulting `txid`, block height, and timestamps. Repeat for
   `INTEL_PRESENCE` or `INTEL_HIGH_PRESENCE` to measure how peers respond.

5. Watch for symmetric replies (same anchors, `0.21` fee, and matching micro
   shards). The `examples/example-decoding-flow.md` file now contains a
   walkthrough of the 06:24:14 chord decoded via the new dialect.

This section is intentionally lightweight—treat it as a lab notebook for
documenting reproducible transmissions and their decoded interpretations.

---

## High-Level Idea

Enigmatic defines:

- A **message space** \\( \mathcal{M} \\): abstract protocol primitives (opcodes, bytes, tags)
- An **encoding function** \\( \mathcal{E}(M) \rightarrow t \\): which maps message
  primitives into concrete DigiByte transactions
- A **decoding function** \\( \mathcal{D}(t) \rightarrow M' \\): which recovers the
  intended symbols from the transaction graph

All encodings are:

- Valid DigiByte transactions
- Economically plausible
- Steganographic by default: transaction flows look like normal wallet behavior

### Deterministic Expression Dictionary

| Expression | Plain-language meaning | Where it shows up |
| ---------- | ---------------------- | ----------------- |
| \\( \mathcal{M} \\) | The abstract "message space" — every possible intent, tag, or symbol Enigmatic can describe before it touches the blockchain. | `specs/01-protocol-overview.md`, `specs/02-encoding-primitives.md` |
| \\( \mathcal{E}(M) \rightarrow t \\) | The encoding function: take a message from \\( \mathcal{M} \\) and turn it into a concrete DigiByte transaction \\( t \\). Think "planner" that chooses values, fees, and graph layout. | README, `specs/02-encoding-primitives.md` |
| \\( \mathcal{D}(t) \rightarrow M' \\) | The decoding function: observe a real transaction and reconstruct the intended message. Comparable to a telemetry parser that turns sensor readings back into structured data. | README, `specs/03-formal-model.md` |
| **State plane** | One dimension of the transaction (value, fee, cardinality, topology, block placement) that can carry information. | README table above, `specs/03-formal-model.md` |
| **State vector** | The combination of all state planes for a single transaction. Equivalent to a row in a spreadsheet describing one heartbeat. | `specs/03-formal-model.md`, `specs/04-encoding-process.md` |
| **Dialect** | A named ruleset that maps symbols to state vectors, similar to how Morse code maps dots and dashes to letters. | `examples/`, `specs/06-dialects.md` |
| **Deterministic** | Means that given the same inputs (dialect + intent) the encoder will always choose the same transaction pattern, eliminating guesswork for the decoder. | README, specs generally |

---

## Scope and Non-Goals

**In scope:**

- Formal definitions and proofs-of-concept  
- Encoding / decoding specifications  
- Security and detection analysis  
- Reference implementation notes  

**Out of scope (for now):**

- Production wallet integrations  
- Miner policy changes  
- Any DigiByte consensus modifications  

---

## License

This project is licensed under the **MIT License**.  
See [`LICENSE`](./LICENSE) for details.
