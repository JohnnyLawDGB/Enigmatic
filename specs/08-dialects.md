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

## 8.5 INTEL Dialect Reference

The `examples/dialect-intel.yaml` file captures the intent of the INTEL traffic
observed on-chain (e.g., block 15558722 at 06:24:14 UTC). Highlights:

- **Anchors:** `217`, `152`, `352`, `866` encode channel links, sync acks,
  steady presence, and high-presence bursts respectively.
- **Micros:** `0.004`, `0.152`, `0.303` act as embedded flags. They are
  modeled explicitly via a `planes.micros[]` section so tooling can enforce the
  dust-level constraints.
- **Fees:** A single band at `0.21 ± 0.004` DGB forms the metronome.
- **Packetization:** Most packets carve `217 → 152 → 352` within three blocks.
- **Symbols:** `INTEL_HELLO`, `INTEL_PRESENCE`, `INTEL_HIGH_PRESENCE`, and
  `INTEL_CHANNEL_LINK` map those anchors into telemetry intents.

Tooling should treat micros as required sub-symbols when matching INTEL packets
to prevent false positives from unrelated dust consolidation transactions.
