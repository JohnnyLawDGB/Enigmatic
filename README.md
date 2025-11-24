# Enigmatic — DigiByte Layer-0 Communication Stack

Enigmatic is a **Layer-0 communication protocol** that uses DigiByte’s native
UTXO, fee, and transaction topology space as a multi-plane message channel.
Each transaction expresses a **state vector** across value, fee, cardinality,
topology, and block-placement planes so peers can interpret intent without
adding new opcodes or consensus rules.

The repository ships four aligned pillars:

- **Specifications** (`specs/01-*.md`) – formalizes state planes, encoding and
  decoding functions, and dialect composition.
- **Whitepaper draft** (`docs/whitepaper.md`) – narrative that mirrors the spec
  and current implementation.
- **Python reference stack** (`enigmatic_dgb/`) – encoder, decoder, planner,
  transaction builder, RPC client, and the `enigmatic-dgb` CLI.
- **Examples & tests** (`examples/`, `tests/`) – reproducible dialects,
  decoded walkthroughs, and pytest coverage.

Read this README for a high-level tour, then jump to
[`docs/TOOLING.md`](docs/TOOLING.md) for CLI workflows or
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for module-level detail.

## State Planes & Terminology

| Plane | Conveys | Example usage | Specification |
| ----- | ------- | ------------- | ------------- |
| **Value** | Amount anchors and repetition headers | `21.21` / `7.00` alternating beacons | [`specs/02-encoding-primitives.md`](specs/02-encoding-primitives.md) |
| **Fee** | Timing offsets and jitter bands | `0.21` cadence to punctuate frames | [`specs/02-encoding-primitives.md`](specs/02-encoding-primitives.md) |
| **Cardinality** | Input/output counts and symmetry | `21 in / 21 out` mirrored swarms | [`specs/03-formal-model.md`](specs/03-formal-model.md) |
| **Topology** | Output graph motifs and ordering windows | Fan-out trees, ring confirmations | [`specs/03-formal-model.md`](specs/03-formal-model.md) |
| **Block placement** | Height deltas and repetition | `Δheight = 3` heartbeat scheduling | [`specs/04-encoding-process.md`](specs/04-encoding-process.md), [`specs/05-decoding-process.md`](specs/05-decoding-process.md) |
| **Auxiliary (OP_RETURN / metadata)** | Optional hints | Hash commitments, dialect selectors | [`specs/01-protocol-overview.md`](specs/01-protocol-overview.md) |

**State vector**: a single transaction’s coordinates across the planes above.
**Dialect**: a named ruleset mapping **symbols** (semantic intents) to state
vectors. Multi-transaction symbols are expressed as **frames** in a chain. The
specs keep these terms consistent for both implementers and analysts.

## Quickstart

```bash
git clone https://github.com/JohnnyLawDGB/Enigmatic.git
cd Enigmatic
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Export DigiByte RPC credentials used by the CLI
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"

# Start with the ASCII console to explore tools and menus
enigmatic-dgb console

# Verify the CLI is available outside the console
enigmatic-dgb --help

# Run unit tests (optional for docs-only edits)
pytest
```

The ASCII console defaults to **dry-run/testing mode** for planner and sender
flows so you can review the planned state vector for each command before
issuing a broadcast flag. Outside the console, use `--dry-run` with
`plan-*`/`send-*` commands to mirror the same guardrail.

## Repository Layout

| Path | Purpose |
| ---- | ------- |
| [`enigmatic_dgb/`](enigmatic_dgb) | Python package: encoder/decoder, planner, transaction builder, RPC client, CLI entry point. |
| [`specs/`](specs) | Canonical protocol chapters: overview → encoding primitives → formal model → encoding/decoding processes → dialects and security. |
| [`docs/`](docs) | Whitepaper draft, architecture notes, tooling guide, roadmap, and RPC test plan. |
| [`examples/`](examples) | Dialects plus decoded walkthroughs you can replay (see `examples/README.md`). |
| [`tests/`](tests) | Pytest suite covering encoder, planner, decoder, and CLI utilities. |

## Tooling Snapshot

All CLI workflows live in `enigmatic_dgb/cli.py` and are documented in
[`docs/TOOLING.md`](docs/TOOLING.md). Highlights:

- **Plan or send a symbol from a dialect**: `enigmatic-dgb plan-symbol` /
  `enigmatic-dgb send-symbol`
- **Plan chained frames from a dialect**: `enigmatic-dgb plan-chain`
- **Plan or send explicit sequences**: `enigmatic-dgb plan-sequence` /
  `enigmatic-dgb send-sequence` and `enigmatic-dgb plan-pattern`
- **Free-form intents**: `enigmatic-dgb send-message`
- **Observation and decoding**: `enigmatic-dgb watch`, `dtsp-*`,
  `binary-utxo-*`

Typical workflow: **dry-run → review state vector → broadcast**. Wallet and RPC
credentials are shared across commands via environment variables or CLI
overrides. See [`docs/rpc_test_plan.md`](docs/rpc_test_plan.md) for reproducible
on-chain experiments.

## History & Inspiration

Enigmatic sits in a long line of “messages hidden in plain sight”: from
Histiaeus’ scalp-tattoo courier, to Enigma traffic that sounded ordinary but was
mathematically scrambled, to Bitcoin’s genesis block embedding “The Times
03/Jan/2009 Chancellor on brink of second bailout for banks.” The name nods to
Enigma and the broader tradition of structured signalling over common channels,
with DigiByte state planes as the medium. Read the full lineage in
[`docs/whitepaper.md`](docs/whitepaper.md#2-historical-lineage-steganography-enigma-and-blockchain-signalling).

## Architecture Snapshot

The reference stack keeps the formal model executable:

- `planner.py` selects UTXO sets and arranges change to satisfy dialect
  constraints (cardinality, value headers, block spacing).
- `tx_builder.py` assembles DigiByte transactions with deterministic ordering,
  dust compliance, and optional OP_RETURN hints.
- `encoder.py` / `decoder.py` translate intents to/from state vectors;
  `watcher.py` observes chains of frames.
- `rpc_client.py` wraps DigiByte JSON-RPC; tests and CLI share the same client.

`docs/ARCHITECTURE.md` links these modules to the spec chapters so auditors can
trace every state plane from definition to implementation.

## Examples & Dialects

Replayable assets live in `examples/`:

- `dialect-heartbeat.yaml` and `dialect-intel.yaml` define symbols and frames.
- `example-decoding-flow.md` shows how a multi-frame reply is parsed back into
  symbols via `watcher.py`.
- `examples/README.md` indexes additional motifs and decoded traces.

### Showcase dialect (console-friendly)

- `examples/dialect-showcase.yaml` ships curated, safe sample payloads you can
  load directly from the console’s "Dialect-driven symbols" menu. Symbols
  include `genesis_bitcoin_2009`, `genesis_digibyte_2014`, `halving_cycle`,
  `triptych_21_21_84`, `digishield_pulse`, `digiswarm_burst`,
  `digidollar_steady`, and `hello_enigmatic`.

Use `enigmatic-dgb plan-symbol --dialect-path examples/dialect-heartbeat.yaml --symbol HEARTBEAT --dry-run`
to inspect a state vector before broadcasting it.

## Security & Deniability

Enigmatic keeps transactions economically plausible and policy-compliant while
embedding meaning in the joint distribution of state planes. The security model
in [`specs/06-security-model.md`](specs/06-security-model.md) details threat
assumptions, detectability bounds, and deniability considerations.

## Documentation Map

- Protocol specs: [`specs/`](specs)
- Architecture notes: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Tooling guide: [`docs/TOOLING.md`](docs/TOOLING.md)
- Whitepaper draft: [`docs/whitepaper.md`](docs/whitepaper.md)
- Roadmap: [`docs/expansion-roadmap.md`](docs/expansion-roadmap.md)

## What’s Next

Near- and mid-term priorities emphasize production-grade wallet integration,
expanded dialect coverage, and richer observability. See
[`docs/expansion-roadmap.md`](docs/expansion-roadmap.md) for the tracked items
and adoption milestones.

## License

This project is licensed under the **MIT License**.
See [`LICENSE`](LICENSE) for details.
