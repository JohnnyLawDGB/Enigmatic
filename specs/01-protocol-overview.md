# 01 — Protocol Overview

This document gives a high-level overview of the Enigmatic Layer-0 protocol.

## 1.1 Motivation

Blockchains are globally replicated, timestamped state machines. While they are
commonly treated as *payment rails*, they also provide a highly reliable,
low-bandwidth broadcast channel.

Enigmatic formalizes a way to use DigiByte’s UTXO-level details as a structured
signaling surface.

## 1.2 Core Ideas

- UTXOs as **registers**  
- Transaction values as **symbol carriers**  
- Fees, block heights, and topology as **side-channels**  
- No new opcodes, no consensus changes  

## 1.3 Actors

- **Encoder**: crafts transactions according to the Enigmatic ruleset.  
- **Decoder / Observer**: watches the chain or a subset of addresses, and
  reconstructs messages.  
- **Uninformed Node**: sees only normal-looking DigiByte activity.  

## 1.4 Design Principles

- Consensus-compatible  
- Plausibly deniable  
- Deterministic for in-protocol decoders  
- Modular and composable  
