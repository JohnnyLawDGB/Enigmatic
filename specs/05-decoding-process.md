# 05 — Decoding Process (Skeleton)

Given an observed transaction sequence and a protocol dialect, the decoder
reconstructs the intended message.

## 5.1 Inputs

- Observed transaction sequence \( (t_1, ..., t_\ell) \)  
- Protocol dialect and dictionary  
- Optional filters (address set, time window, etc.)  

## 5.2 Outputs

- Recovered message \(M\) or \(\varnothing\) (if none).  

## 5.3 High-Level Steps

1. Select candidate transactions according to the dialect’s discovery rules.  
2. Project each transaction into its encoding planes \(\Pi(t)\).  
3. Recover symbol stream from value, fee, cardinality, etc.
4. Validate framing, checksums, and integrity.
5. Emit reconstructed message \(M\).

## 5.4 Discovery Heuristics

- **Sliding-window fee bands:** Maintain a rolling histogram of fees for candidate transactions. Peaks near `0.21`, `2.10`, etc., suggest telemetry channels matching Table 2.8.
- **Symmetry scoring:** For each window of \(k\) transactions, compute \(\sigma_t\) from §2.3.1. A run of `+1` scores implies mirrored swarms (heartbeats), while alternating `+1/-1` implies negotiation cycles.
- **Block-interval monitors:** Track \(\Delta h_t\) and compare to dialect expectations. Accept ±1 jitter to tolerate reorgs and mempool delay.
- **Topology fingerprints:** Use graph traversal to detect fan-out trees or rings that match dialect motifs.

## 5.5 State Vector Reconstruction

Pseudo-code for reconstructing \(\mathbf{s}(t)\) and validating ordering:

```python
state = []
for tx in candidate_transactions:
    v = canonical_value_header(tx)
    f = classify_fee_band(tx.fee)
    m, n = len(tx.inputs), len(tx.outputs)
    delta_h = tx.height - prev_height(tx)
    sigma = symmetry_flag(m, n, tx.ordering)
    state.append((v, f, m, n, delta_h, sigma))

validate_cadence(state)
symbols = dialect.map_state_sequence(state)
return dialect.assemble_message(symbols)
```

`validate_cadence` enforces ordering, repetition counts, and checksum conditions declared in the dialect configuration.

## Appendix A — Worked Example

Replicate the README “State Planes Quick Reference” heartbeat example:

1. Observe three transactions spaced every 3 blocks with `21.21` value headers and `0.21 ± ε` fees.
2. Symmetry scoring yields `σ = +1` for all transactions (mirrored 21 in / 21 out patterns).
3. Dialect lookup maps `(21.21, 0.21, 21, 21, 3, +1)` to `FRAME_SYNC` → `HEARTBEAT` → `HEARTBEAT`.
4. Decoder reconstructs `M = [FRAME_SYNC, HEARTBEAT, HEARTBEAT]`, confirming swarm liveness.
