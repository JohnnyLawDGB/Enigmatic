# Tooling & Usage Guide

This guide captures how to operate Enigmatic’s DigiByte reference stack. It
aligns with `enigmatic_dgb/cli.py`, the specs in `../specs/`, and the examples in
`../examples/` so contributors can move from a dry-run plan to an on-chain
broadcast without guessing how components fit together.

## 1. Prerequisites

- **Python**: 3.10+.
- **DigiByte node**: DigiByte Core with RPC enabled and a funded wallet.
- **System packages**: `git`, `python3-venv`, `build-essential` (for dependency
  builds).

## 2. Install & verify the CLI

```bash
git clone https://github.com/JohnnyLawDGB/Enigmatic.git
cd Enigmatic
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]

# Confirm availability
enigmatic-dgb --help
```

The editable install exposes the `enigmatic-dgb` CLI and keeps it synchronized
with your working tree.

## 3. RPC & wallet configuration

All planner, sender, and watcher commands share a single configuration surface.
Set environment variables to avoid repeating flags:

```bash
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"
export DGB_RPC_HOST="127.0.0.1"
export DGB_RPC_PORT="14022"
export DGB_RPC_WALLET="enigmatic"
```

Override any field per command with `--rpc-host`, `--rpc-port`, `--rpc-user`,
`--rpc-password`, `--rpc-wallet`, or `--rpc-url`. Load and unlock the target
wallet before broadcasting so the transaction builder can sign each frame.

## 4. Command surface

| Command | Purpose |
| ------- | ------- |
| `send-message` | Encode a free-form intent and payload without referencing a dialect. |
| `send-symbol` | Encode and broadcast a symbol defined in a dialect YAML file. |
| `plan-symbol` | Dry-run or broadcast a single symbol using automation metadata. |
| `plan-chain` | Plan or broadcast multi-frame symbols defined in a dialect. |
| `plan-pattern` | Plan/broadcast an explicit list of amounts (value-plane only). |
| `send-sequence` / `plan-sequence` | Chained explicit sequences with optional OP_RETURN hints. |
| `watch` | Observe an address and stream decoded packets. |
| `dtsp-*`, `binary-utxo-*` | Encode/decode helpers for specific substitution mappings. |

Common planner flags:

- `--min-confirmations` – funding UTXO filter (default 1; set to 0 for
  unconfirmed starts).
- `--min-confirmations-between-steps` – wait for confirmations between frames.
- `--wait-between-txs` – poll cadence / pacing delay between frames.
- `--max-wait-seconds` – abort threshold for confirmation waits.
- `--fee` – override dialect fee punctuation (where supported).
- `--block-target` – optional absolute block height to celebrate or align with;
  broadcasting waits until the chain is within the configured drift window.

## 5. Typical workflow: dry-run → broadcast

1. **Plan** a symbol or pattern without broadcasting.
2. **Inspect** the emitted state vector: inputs, outputs (value plane), fee,
   cardinality, block-placement expectations, and optional OP_RETURN hints.
3. **Broadcast** the exact plan after review; the builder reuses the planned
   change choreography so the broadcast matches the dry-run.

### Example: dialect symbol

```bash
# Preview the HEARTBEAT symbol defined in examples/dialect-heartbeat.yaml
enigmatic-dgb plan-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT --dry-run

# Broadcast once reviewed
enigmatic-dgb plan-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT --broadcast
```

### Example: chained frames from a dialect

```bash
enigmatic-dgb plan-chain \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT_CHAIN \
  --to-address DT98bqbNMfMY4hJFjR6EMADQuqnQCNV1NW \
  --min-confirmations 0 --max-frames 3 --dry-run

# Add --broadcast to stream txids in order and reuse the planned change output between frames.
```

### Example: explicit sequences without a dialect

```bash
# Inspect a prime staircase
enigmatic-dgb plan-sequence \
  --to-address DT98bqbNMfMY4hJFjR6EMADQuqnQCNV1NW \
  --amounts 73,61,47,37,23,13,5 \
  --fee 0.21 --op-return-ascii I,S,E,E,Y,O,U

# Broadcast the same plan
enigmatic-dgb send-sequence \
  --to-address DT98bqbNMfMY4hJFjR6EMADQuqnQCNV1NW \
  --amounts 73,61,47,37,23,13,5 \
  --fee 0.21 --op-return-ascii I,S,E,E,Y,O,U
```

### Example: free-form message

```bash
enigmatic-dgb send-message \
  --to-address dgb1example... \
  --intent presence \
  --channel ops \
  --payload-json '{"window": "mid"}'
```

## 6. Creating or extending dialects

1. Copy an existing dialect (e.g., `examples/dialect-heartbeat.yaml`).
2. Define symbols and, if needed, multi-frame chains. Specify value anchors,
   fee punctuation, cardinality, topology hints, block-placement cadence, and
   optional OP_RETURN selectors.
3. Use `enigmatic-dgb plan-symbol --dialect-path <file> --symbol <NAME> --dry-run`
   to validate constraints and dust compliance.
4. Iterate until the planned state vector matches the intended symbol, then
   broadcast with `--broadcast` or incorporate into automation.

Keep dialect files close to their replay instructions inside `examples/README.md`
so observers can reproduce them with the same CLI flags.

## 7. Decoding patterns and watching addresses

- **Live observation**: `enigmatic-dgb watch --address <dgb1...> --poll-interval 15`
  streams decoded packets (JSON per line). Pipe to `jq` or a log collector.
- **DTSP helpers**: `dtsp-encode`, `dtsp-decode`, and `dtsp-table` convert
  between plaintext and decimal-time-substitution patterns.
- **Binary packet helpers**: `binary-utxo-encode` / `binary-utxo-decode` map text
  to binary payloads expressed as decimal outputs.

Decoded walkthroughs in `examples/example-decoding-flow.md` mirror the watcher
output and illustrate how block spacing and change-linking recover multi-frame
symbols.

### Ordinal inscription exploration

Probe the chain for inscription-style outputs or inspect a specific
transaction using the shared RPC configuration:

```bash
# Scan a slice of the chain for candidates
enigmatic-dgb ord-scan --limit 10

# Decode inscription-like payloads from a transaction (all vouts)
enigmatic-dgb ord-decode <txid>
```

Taproot-aware parsing is experimental and may not recognize all inscription
formats.

### Taproot inscription planning

Use the plan-only Taproot helper to sketch an inscription following the
Enigmatic Taproot Dialect v1. It connects to the DigiByte node using the same
RPC flags as other ordinal commands and **does not sign or broadcast** the
transaction.

```bash
# Plan a text/plain inscription
enigmatic-dgb ord-plan-taproot "hello taproot"

# Plan a binary payload with a custom content type and JSON output
enigmatic-dgb ord-plan-taproot 0x68656c6c6f --content-type application/octet-stream --json
```

## 8. Integrating wallets & RPC setups

- For **mainnet/testnet switching**, override `--rpc-port` and `--rpc-wallet`
  per command while reusing the same dialect file.
- For **air-gapped signing**, use `plan-*` commands to export the planned inputs
  and outputs, sign offline via DigiByte Core, then broadcast with
  `sendrawtransaction`.
- For **automation**, wrap CLI invocations in scripts or import
  `TransactionBuilder`, `SymbolPlanner`, and `DigiByteRPC` directly from the
  package to reuse the same deterministic planning logic.

## 9. Validation & troubleshooting

- Run `pytest` to confirm encoder/decoder and planner invariants before rolling
  out new dialects.
- Use `--min-confirmations=0` with caution: chains will reference unconfirmed
  change outputs in memory until the prior frame confirms.
- If a broadcast fails, re-run the identical `plan-*` command to confirm no
  wallet state drift occurred between planning and submission.

## 10. References

- Specs: `../specs/`
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- RPC experiments: [`rpc_test_plan.md`](rpc_test_plan.md)
- Dialects and walkthroughs: `../examples/`
