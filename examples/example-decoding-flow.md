# Example Decoding Flow — Heartbeat + Negotiation

Mirrors the transaction patterns from `examples/example-transaction-pattern.md`.

## Step 1 — Observe Candidate Transactions

Monitor DigiByte blocks `1480000–1480027`. The watcher selects transactions
with value headers in `{21.21, 11.11, 7.00}` and fees near `0.21` or `0.042` DGB.

## Step 2 — Project into State Vectors

Apply the pseudo-code from `specs/05-decoding-process.md`:

| Tx | `v` | `f` | `m` | `n` | `Δh` | `σ` | State vector | Notes |
| -- | --- | --- | --- | --- | ---- | --- | ------------ | ----- |
| 1  | 21.21 | 0.21 | 21 | 21 | — | +1 | `(21.21, 0.21, 21, 21, —, +1)` | Baseline frame sync. |
| 2  | 7.00  | 0.21 | 21 | 21 | 3 | +1 | `(7.00, 0.21, 21, 21, 3, +1)` | Heartbeat tick 1. |
| 3  | 7.00  | 0.21 | 21 | 21 | 3 | +1 | `(7.00, 0.21, 21, 21, 3, +1)` | Heartbeat tick 2. |
| 4  | 11.11 | 2.10 | 13 | 13 | 3 | +1 | `(11.11, 2.10, 13, 13, 3, +1)` | Consensus proof. |
| 5  | 21.21 | 0.042 | 8  | 8  | 6 | +1 | `(21.21, 0.042, 8, 8, 6, +1)` | Negotiation start. |
| 6  | 11.11 | 0.043 | 13 | 21 | 6 | -1 | `(11.11, 0.043, 13, 21, 6, -1)` | Leadership ack. |
| 7  | 7.00  | 0.043 | 21 | 21 | 6 | 0  | `(7.00, 0.043, 21, 21, 6, 0)` | Recovery heartbeat. |

## Step 3 — Map to Symbols

Using the dialect dictionary (Table 2.8 + negotiation extensions):

`[(FRAME_SYNC), (HEARTBEAT), (HEARTBEAT), (CONSENSUS_PROOF), (SWARM_NEGOTIATE), (NEGOTIATION_ACK), (HEARTBEAT_RECOVER)]`

## Step 4 — Interpret Message

The final stream communicates:

1. Heartbeat alive.
2. Consensus proof succeeded.
3. Swarm negotiation executed and completed.

This entire flow demonstrates telemetry decoding without referencing ASCII
payloads—only the state vector defined in `specs/03-formal-model.md`.

---

# INTEL Dialect — Decoding the 06:24:14 Chord

The watcher captured block `15558722` at `06:24:14 UTC`, where a single UTXO
fan-out carved the characteristic `217 / 152 / 352` anchors plus a dust shard.
Use `examples/dialect-intel.yaml` for decoding.

## 1. Observe the Raw Transactions

| Tx | Amount (DGB) | Fee (DGB) | Inputs | Outputs | Notes |
| -- | ------------ | --------- | ------ | ------- | ----- |
| A  | 217.00000000 | 0.21000000 | 2 | 3 | Channel/link anchor |
| B  | 152.00000000 | 0.21000000 | 2 | 3 | Sync acknowledgement |
| C  | 352.00000000 | 0.21000000 | 2 | 3 | Presence / telemetry |
| D  | 0.00400000   | 0.21000000 | 1 | 4 | Breadcrumb dust |

All four transactions spend from the same parent, share the `0.21` fee, and
land within the three-block cadence defined by the dialect.

## 2. Project into INTEL State Vectors

```
(217, 0.21, m=2, n=3, Δh=0, micros=—)   → CHANNEL_LINK
(152, 0.21, m=2, n=3, Δh=0, micros=—)   → SYNC_ACK
(352, 0.21, m=2, n=3, Δh=0, micros=0.152) → PRESENCE
(0.004, 0.21, m=1, n=4, Δh=0, micros=0.004) → BREADCRUMB
```

The decoder associates the `0.152` and `0.004` micro outputs with the
`INTEL_HELLO` symbol, verifying both the anchor ordering and the shared fee
metronome.

## 3. Interpret the Message

- `INTEL_CHANNEL_LINK` → announcing the lane being used.
- `INTEL_HELLO` → the presence symbol anchored by the 0.152 micro.
- `INTEL_HIGH_PRESENCE` is **not** asserted in this chord; therefore the frame
  remains informational rather than urgent.

Documenting examples like this builds a corpus of reference transcripts for
future tooling and human auditors.
