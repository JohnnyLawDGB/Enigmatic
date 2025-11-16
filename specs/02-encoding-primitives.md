# 02 — Encoding Primitives

This section defines the basic building blocks that Enigmatic uses to carry
information on DigiByte.

## 2.1 Value Plane

Reserved / example header values:

- `7.00` — segment marker  
- `11.11` — round start / header  
- `21.21` — broadcast or higher-level frame marker  
- `64.00` — power-of-two boundary  

Values are always exact to 1e-8 DGB and chosen to remain plausible to external
observers.

## 2.2 Fee Plane

Fees are used as an orthogonal signal:

- Example ranges:  
  - `0.21` DGB ± ε  
  - `2.10` DGB ± ε  
  - `21.00` DGB ± ε  

Where ε is small noise to avoid obvious fingerprinting.

## 2.3 Cardinality Plane

Input and output counts form a low-bandwidth but robust channel:

- `m = |IN_t|`
- `n = |OUT_t|`

Patterns like `m = 21, n = 21` or prime `m, n` can encode additional bits.

### 2.3.1 Cluster Symmetry

- **Mirrored clusters (`m = n`, ordered pairs)** act as swarm-alignment beacons. Example: `21 in / 21 out` sorted lexicographically signals that every participant contributed and received funds.
- **Rotational clusters** (e.g., inputs grouped by previous block mod 3, outputs grouped by future block mod 3) encode swarm roles.
- **Asymmetric perturbations** (e.g., `m = 13`, `n = 21`) flag leadership elections or quorum adjustments.

Decoders treat the symmetry flag \( \sigma_t \in \{-1, 0, 1\} \) (mirrored, neutral, asymmetric) as part of the state vector referenced throughout the roadmap.

## 2.4 Optional OP_RETURN Plane

OP_RETURN is used sparingly for:

- Version tagging  
- Hash commitments  
- Protocol negotiation  

## 2.5 Bit-Packets

Bit-packets are small DGB values such as `0.0100xxxx` where the 8 decimal
digits after the decimal point carry a code point.

Example:

- `0.01001101` → `01001101₂` → symbol in an application dictionary.

The protocol does not mandate a single mapping; instead, it defines how
dictionaries are negotiated and applied.

## 2.6 Block Interval Encoding (Timing)

Let \( \Delta h_t = h_t - h_{t-1} \) denote the height delta between sequential transactions in a stream. Timing acts as a first-class primitive:

- `Δh = 1` — saturated stream / urgent telemetry
- `Δh = 3` — heartbeat cadence (default for swarm liveness)
- `Δh = 6` — checkpoint / synchronization event
- `Δh = 21` — epoch boundary for configuration changes

Encoders fix the cadence per dialect, while decoders tolerate ±1 jitter unless otherwise negotiated.

## 2.7 Ordering & Repetition Motifs

Ordering binds meaning even when values repeat:

- **Canonical ordering rule:** sort inputs by previous txid, outputs by amount, then by script hash. Deviations (e.g., reverse ordering) mark exceptional states like failover or alert conditions.
- **Alternating value motifs:** `11.11` / `7.00` / `11.11` sequences indicate consensus proposals → acceptances → confirmations.
- **Repetition counts:** repeating the same `21.21` header exactly `k` times denotes participant cardinality without revealing addresses.

## 2.8 Reserved Dialect Markers

Coordinated combinations across planes create high-level symbols. Dialect authors reserve markers in coordination tables so encoders and decoders stay aligned.

| Symbol            | Value plane requirement | Fee band           | Cardinality      | `Δh` expectation | Semantics |
| ----------------- | ----------------------- | ------------------ | ---------------- | ---------------- | --------- |
| `FRAME_SYNC`      | `21.21` header          | `0.21 ± ε`         | `m = n = 21`     | `Δh = 3`         | Opens a telemetry round, establishes baseline state vector alignment. |
| `HEARTBEAT`       | `7.00` payload           | `0.21 ± ε`         | `m = 3, n = 3`   | `Δh = 3`         | Confirms swarm liveness; no topology changes implied. |
| `CONSENSUS_PROOF` | `11.11` majority marker | `2.10 ± ε`         | `m = 13, n = 13` | `Δh = 1`         | Encodes majority agreement and rapid follow-up transactions. |
| `SWARM_NEGOTIATE` | `0.0100xxxx` bit-packet | `0.042 ± ε`        | `m = 8, n = 8`   | `Δh = 6`         | Exchanges negotiation parameters before a configuration shift. |

Reserved markers must remain plausible to external observers; encoders randomize unused planes to prevent fingerprinting while still satisfying the table constraints.
