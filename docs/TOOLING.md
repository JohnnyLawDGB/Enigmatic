# Tooling Build & Usage Guide

This guide collects the practical steps required to build the Enigmatic DigiByte
toolchain from source and operate the included CLI utilities. It complements the
architecture overview in [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) and the
formal specs under `specs/`.

## 1. Prerequisites

- **Python:** 3.10 or newer.
- **DigiByte node:** A DigiByte Core node with RPC enabled. Create a wallet that
  will fund and observe Enigmatic patterns.
- **System packages:** `git`, `python3-venv`, and `build-essential` (for
  platforms that need C headers when installing dependencies).

## 2. Build & install the CLI

```bash
git clone https://github.com/JohnnyLawDGB/Enigmatic.git
cd Enigmatic
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

The editable install exposes the `enigmatic-dgb` executable and keeps it
synchronized with your working tree. You can confirm the installation via:

```bash
enigmatic-dgb --help
```

## 3. Runtime configuration

Every tool that touches the blockchain shares the same RPC configuration. The
CLI will automatically pick up these environment variables:

```bash
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"
export DGB_RPC_HOST="127.0.0.1"
export DGB_RPC_PORT="14022"
export DGB_RPC_WALLET="enigmatic"
```

You can override any of them via CLI flags (see the planner commands below).

## 4. Tool suite overview

| Component | Module / entry point | Primary purpose |
| --------- | -------------------- | --------------- |
| RPC client | `enigmatic_dgb.rpc_client.DigiByteRPC` | Typed JSON-RPC wrapper shared by all tools. |
| Transaction builder | `enigmatic_dgb.tx_builder.TransactionBuilder` | Selects UTXOs, assembles, and signs spends. |
| Encoder/decoder | `enigmatic_dgb.encoder`, `enigmatic_dgb.decoder` | Convert between high-level intents and spend instructions. |
| Watcher | `enigmatic_dgb.watcher.Watcher` | Polls the node, groups packets, and emits decoded messages. |
| CLI | `enigmatic_dgb.cli` / `enigmatic-dgb` | User-facing commands for sending, planning, and watching. |
| Automation planner | `enigmatic_dgb.planner` | Loads dialects and produces reproducible symbol plans. |

With the editable install in place you can import the modules directly from
Python or rely on the CLI commands described below.

## 5. Sending a free-form message

Use the `send-message` subcommand when you want to manually describe the intent
and payload without referencing a higher-level dialect file:

```bash
enigmatic-dgb send-message \
  --to-address dgb1example... \
  --intent presence \
  --channel ops-telemetry \
  --payload-json '{"window": "mid"}'
```

The CLI will:
1. Build an `EnigmaticMessage` with the provided metadata.
2. Run it through `EnigmaticEncoder` to derive the value/fee/cardinality pattern.
3. Ask `TransactionBuilder` to select UTXOs and assemble a raw transaction.
4. Broadcast the signed transaction via `DigiByteRPC`.

Add `--encrypt-with-passphrase <shared secret>` if you want the payload JSON to
be encrypted before it is embedded into the pattern.

## 6. Watching for patterns

To observe on-chain traffic destined for a receiver address, start the watcher:

```bash
enigmatic-dgb watch --address dgb1observer... --poll-interval 15
```

The watcher hits the DigiByte RPC interface every `poll-interval` seconds,
wraps new transactions as `ObservedTx` objects, groups them into packets, and
runs them through the decoder. Each decoded packet is printed as a JSON line so
you can pipe it to `jq`, `grep`, or a log aggregator.

## 7. Working with dialect symbols

Dialects bundle repeatable symbol definitions plus automation hints (wallets,
fee targets, scheduling suggestions). Load the provided heartbeat example or
your own dialect with the `send-symbol` command:

```bash
enigmatic-dgb send-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT \
  --to-address dgb1example... \
  --channel identity
```

`send-symbol` merges the dialect metadata with any overrides supplied on the
command line, encodes the resulting symbol, and relays it just like
`send-message`. Provide `--session-*` parameters when you are negotiating a
session via `enigmatic_dgb.session.SessionContext`.

## 8. Planning before broadcasting

When you want to inspect the exact transaction that would be produced before you
sign or broadcast it, use the `plan-symbol` or `plan-pattern` helpers:

```bash
# Inspect a symbol defined in a dialect without broadcasting
enigmatic-dgb plan-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT

# Craft an explicit set of output amounts (value plane only)
enigmatic-dgb plan-pattern \
  --to-address dgb1example... \
  --amounts 21.0,34.0,55.0,0.303 \
  --fee 0.21
```

Both commands print the selected UTXOs, ordered outputs, change split, and fee.
`plan-pattern` now produces a chained plan (one transaction per amount) so that
duplicate outputs to the same address never trigger DigiByte Core's
"duplicated address" RPC errors. The `--fee` argument applies per transaction,
and the broadcast path returns every transaction ID in relay order. Planner-
specific RPC flags (`--rpc-host`, `--rpc-port`, `--rpc-wallet`, etc.)
temporarily override both environment defaults and dialect hints, which is
useful when you stage a dialect on testnet or an air-gapped node.

## 9. Running tests and linting

Execute the unit tests to make sure the encoder/decoder stack still round-trips
correctly after changes:

```bash
pytest
```

Add `pytest -k "roundtrip" -vv` when you want verbose output for the
encoder/decoder coverage specifically. Formatting and import hygiene are handled
by the default `ruff` profile defined in `pyproject.toml`:

```bash
ruff check .
```

Run both commands before opening a pull request so reviewers can focus on the
protocol changes instead of style regressions.
