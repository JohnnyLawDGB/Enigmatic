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
   - header values  
   - per-output values  
   - fee band  
   - input/output cardinalities  
4. Construct unsigned transactions.  
5. Sign using standard DigiByte mechanisms.  
