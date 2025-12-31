# Simple Usage Guide

New to Enigmatic? Start here for a concise workflow that pairs with the full
tooling guide in [`docs/TOOLING.md`](./TOOLING.md). This page focuses on the
core CLI steps to plan, send, and observe messages without diving into every
helper.

## 0) Set up once

```bash
git clone https://github.com/JohnnyLawDGB/Enigmatic.git
cd Enigmatic
python -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
```

Export DigiByte RPC credentials one time per terminal so planner, sender, and
watcher share them:

```bash
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"
export DGB_RPC_HOST="127.0.0.1"
export DGB_RPC_PORT="14022"
export DGB_RPC_WALLET="enigmatic"
```

## 1) Plan first, then broadcast

Run every command with `--dry-run` to review the planned **state vector** before
putting it on-chain. When the plan looks right, re-run the exact command with
`--broadcast` (or without `--dry-run`) to submit it.

```bash
enigmatic-dgb send-message \
  --to-address dgb1youraddress... \
  --intent presence \
  --channel ops \
  --payload-json '{"window": "mid"}' \
  --dry-run    # review only

# When satisfied:
enigmatic-dgb send-message ... --broadcast
```

## 2) Understand dialects at a glance

Dialects map semantic **symbols** (e.g., `HEARTBEAT`, `PULSE`) to specific
state-vector patterns across value, fee, cardinality, topology, and block
placement. They keep recurring intents consistent and easier to decode. Point
`plan-symbol` or `send-symbol` at a dialect YAML file to reuse those mappings
instead of hand-crafting every plane yourself.

```bash
enigmatic-dgb plan-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT \
  --dry-run
```

## 3) Quick reference: three everyday commands

- **Send a free-form message**: `enigmatic-dgb send-message --to-address ... --intent ... --channel ... --payload-json ... --dry-run`
- **Plan a symbol from a dialect**: `enigmatic-dgb plan-symbol --dialect-path <file> --symbol <NAME> --dry-run` (add `--broadcast` to send)
- **Watch and decode traffic**: `enigmatic-dgb watch --address <dgb1...> --poll-interval 15`

## 4) Suggested workflow

1. Export DigiByte RPC credentials (`DGB_RPC_USER`, `DGB_RPC_PASSWORD`, host,
   port, and wallet) once per terminal so all commands share them.
2. **Dry-run → review → broadcast**: start with `send-message` or
   `plan-symbol`, inspect the plan, then broadcast the same call.
3. Use `watch` on your addresses to see decoded packets and verify the intents
   you sent.

## 5) Ordinal helpers can wait

Enigmatic ships optional OP_RETURN and Taproot inscription helpers, but you can
ignore them until you are comfortable with the basics above. Focus on
`send-message`, `plan-symbol`, and `watch` first; bring in inscription commands
later if and when you need on-chain payloads.

## 6) Keep exploring

- Use the `enigmatic-dgb console` for guided menus if you prefer prompts over
  flags.
- Browse [`docs/TOOLING.md`](./TOOLING.md) for deeper options, UTXO utilities,
  and advanced dialect lifecycle commands.
