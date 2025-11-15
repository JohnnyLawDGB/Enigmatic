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
