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
