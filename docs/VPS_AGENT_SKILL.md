# VPS Agent Skill Notes

## Purpose
This note captures the minimum wiring and command patterns needed to operate the
Enigmatic tooling on a VPS without leaking credentials. It is intended for
future agent automation (RPC-driven send/watch, decode/encode validation, and
event monitoring).

## RPC Configuration (No Secrets)
- The CLI expects `DGB_RPC_*` (or `ENIGMATIC_DGB_RPC_*`) environment variables.
- Recommended env keys:
  - `DGB_RPC_USER`, `DGB_RPC_PASSWORD`
  - `DGB_RPC_HOST`, `DGB_RPC_PORT`
  - `DGB_RPC_WALLET` (must match a loaded wallet name)
- Alternately use `~/.enigmatic.yaml` with an `rpc:` section; the code does not
  read `~/.digibyte/digibyte.conf` directly.

## Canonical Send/Watch Commands
Dry-run encode (preview outputs + fee plane):
```
DGB_RPC_USER=... DGB_RPC_PASSWORD=... DGB_RPC_HOST=127.0.0.1 DGB_RPC_PORT=14022 DGB_RPC_WALLET=<wallet> \
python -m enigmatic_dgb.cli send-symbol \
  --dialect-path examples/dialect-showcase.yaml \
  --symbol hello_enigmatic \
  --to-address <destination> \
  --channel default \
  --fee 0.021021 \
  --dry-run
```

Broadcast:
```
DGB_RPC_USER=... DGB_RPC_PASSWORD=... DGB_RPC_HOST=127.0.0.1 DGB_RPC_PORT=14022 DGB_RPC_WALLET=<wallet> \
python -m enigmatic_dgb.cli send-symbol \
  --dialect-path examples/dialect-showcase.yaml \
  --symbol hello_enigmatic \
  --to-address <destination> \
  --channel default \
  --fee 0.021021
```

Watch/decode loop:
```
DGB_RPC_USER=... DGB_RPC_PASSWORD=... DGB_RPC_HOST=127.0.0.1 DGB_RPC_PORT=14022 DGB_RPC_WALLET=<wallet> \
python -m enigmatic_dgb.cli watch --address <destination> --poll-interval 10
```

Note: The oracle response targets the sender address, not the destination address,
so monitoring the sender wallet (or its addresses) is required to see replies.

## Dialect Requirements (Avoid Known Failures)
- Dialects must include a top-level `description` and `fee_punctuation`.
- YAML strings that include `:` should be quoted (example fixed in
  `examples/dialect-showcase.yaml`).
- `examples/dialect-heartbeat.yaml` lacks a description; `examples/dialect-intel.yaml`
  lacks `fee_punctuation`.

## Agent Policy Behavior (Internal Approvals)
- The hybrid agent uses internal policy gating; no external approval flow.
- Policy allows or blocks actions based on preferences and risk profile.

## Optional: RPC Event Source
- `DigiByteWalletEventSource` wraps `listtransactions` to produce `AgentEvent`
  entries and can be wired into `EventMonitor` + `EventProcessor`.
