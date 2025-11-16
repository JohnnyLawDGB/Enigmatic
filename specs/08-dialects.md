# 08 — Dialects & Configuration Files

This document defines how Enigmatic dialects are described in machine-readable
form so tooling can drive DigiByte RPC endpoints automatically.

## 8.1 Dialect Schema

A dialect file is YAML or JSON with the following top-level keys:

- `name`: Human-readable dialect label.
- `planes.value`: Allowed headers + semantics.
- `planes.fee`: Fee bands with jitter guidance.
- `planes.cardinality`: Permitted `(m, n)` pairs and symmetry expectations.
- `planes.block`: Target `Δh` cadences and tolerance.
- `symbols`: Mapping from state vectors to logical symbols.
- `automation`: Hooks for wallet/RPC orchestration.

## 8.2 Example Snippet

```yaml
name: heartbeat
planes:
  value:
    - header: 21.21
      label: FRAME_SYNC
    - header: 7.00
      label: HEARTBEAT
  fee:
    - band: 0.21
      jitter: 0.005
  cardinality:
    - m: 21
      n: 21
      sigma: +1
  block:
    delta: 3
    tolerance: 1
symbols:
  - match:
      value: 21.21
      fee: 0.21
      m: 21
      n: 21
      delta: 3
      sigma: +1
    emit: FRAME_SYNC
automation:
  rpc:
    min_confirmations: 1
    rebroadcast: false
```

## 8.3 Automation Notes

- Parsers validate the file against a JSON Schema (future work) before encoding.
- RPC clients should respect `block.delta` before submitting new transactions,
  using DigiByte’s `getblockcount` to align with the cadence.
- Fee managers consume `planes.fee[].jitter` to randomize per transaction while
  staying inside wallet policy limits.

## 8.4 Extensibility

- Additional sections (e.g., `op_return`, `bit_packets`) may be added without
  breaking compatibility as long as they use self-describing keys.
- Dialect files should be versioned and signed when shared between agents.
