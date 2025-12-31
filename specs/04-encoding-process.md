# 04 — Encoding Process (Skeleton)

This document specifies how an encoder maps a message \(M\) into one or more
DigiByte transactions under Enigmatic.

## 4.1 Inputs

- Message \(M\) (sequence of primitives)  
- Wallet state (set of spendable UTXOs)  
- Encoding dialect and dictionary  
- Policy constraints (fee ranges, dust limits, etc.)  

## 4.2 Outputs

- A sequence of valid DigiByte transactions ready to be signed and broadcast.  

## 4.3 High-Level Steps

1. Interpret \(M\) under the selected dialect.  
2. Partition \(M\) into frames and bit-packets.  
3. Assign frames to transactions and choose:
   - header values (Value plane)
   - per-output values / bit-packets
   - fee band (including jitter ε)
   - input/output cardinalities (mirrored, asymmetric, leader-election, etc.)
   - block interval target \(\Delta h\)
   - ordering / repetition motifs (e.g., alternating 11.11 / 7.00)

   **Checklist:**
   1. Fix \(\Delta h\) cadence before selecting fee bands so that mempool dynamics will not break timing guarantees.
   2. Reserve the correct value header for the frame type (e.g., `FRAME_SYNC` vs `HEARTBEAT`).
   3. Choose cardinality + symmetry that matches the swarm size or negotiation state.
   4. Decide whether OP_RETURN hints or auxiliary metadata are necessary.
   5. Encode ordering / repetition counts needed by the decoder to reconstruct \(\mathbf{s}(t)\).
4. Construct unsigned transactions.
5. Sign using standard DigiByte mechanisms.

## 4.4 Telemetry Dialects & Automation Hooks

- **Dialect configuration files** (YAML/JSON) declare the allowed value headers, fee bands, cardinalities, and timing cadences. Example schemas live in `examples/dialect-heartbeat.yaml`.
- **Automation pipeline:**
  1. Load dialect config → produce a finite-state encoder describing valid \(\mathbf{s}(t)\) transitions.
  2. Map message primitives onto state transitions (e.g., `HEARTBEAT`, `CONSENSUS_PROOF`).
  3. Use wallet orchestration to select UTXOs that satisfy the requested cardinalities and symmetry constraints.
  4. Emit transactions and schedule them against the DigiByte node’s RPC interface, respecting the `Δh` schedule.
- **RPC Integration:** Encoders must monitor `getblockcount` (or headers) to align block intervals and adjust fees dynamically. Future tooling will reuse the shared RPC configuration surface (environment variables or `.enigmatic.yaml`) to coordinate these steps.
