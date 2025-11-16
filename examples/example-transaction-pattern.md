# Example Transaction Patterns — Telemetry Focus

Synthetic (non-spendable) transactions showing how the state vector
\(\mathbf{s}(t) = (v, f, m, n, \Delta h, \sigma)\) from `specs/03-formal-model.md`
drives real-world topology.

## Scenario A — Heartbeat Stream

Cadence: `Δh = 3`, mirrored `m = n = 21`, reserved markers from Table 2.8.

| Tx | Height | Value header | Fee (DGB) | `m` | `n` | `Δh` | `σ` | Symbol | Notes |
| -- | ------ | ------------- | --------- | --- | --- | ---- | --- | ------ | ----- |
| 1  | 1480000 | `21.21` | `0.2104` | 21 | 21 | — | +1 | `FRAME_SYNC` | Opens epoch, matches README quick reference. |
| 2  | 1480003 | `7.00`  | `0.2098` | 21 | 21 | 3 | +1 | `HEARTBEAT` | Confirms swarm liveness. |
| 3  | 1480006 | `7.00`  | `0.2102` | 21 | 21 | 3 | +1 | `HEARTBEAT` | Second tick in cadence. |
| 4  | 1480009 | `11.11` | `2.1050` | 13 | 13 | 3 | +1 | `CONSENSUS_PROOF` | Temporary quorum vote, still heartbeat-aligned. |

## Scenario B — Swarm Negotiation Cycle

Cadence relaxes to `Δh = 6`. Cardinality shifts highlight leadership election.

| Tx | Height | Value header | Fee (DGB) | `m` | `n` | `Δh` | `σ` | Symbol | Notes |
| -- | ------ | ------------- | --------- | --- | --- | ---- | --- | ------ | ----- |
| 5  | 1480015 | `21.21` | `0.0421` | 8  | 8  | 6 | +1 | `SWARM_NEGOTIATE` | Dialect bit-packet conveys proposal hash. |
| 6  | 1480021 | `11.11` | `0.0429` | 13 | 21 | 6 | -1 | `NEGOTIATION_ACK` | Asymmetric cluster shows provisional leader (13 inputs). |
| 7  | 1480027 | `7.00`  | `0.0430` | 21 | 21 | 6 | 0  | `HEARTBEAT_RECOVER` | Returns to mirrored state post-negotiation. |

Each row is intentionally human-readable and can be recreated via synthetic wallet tooling (see `specs/04-encoding-process.md` for encoder guidance).
