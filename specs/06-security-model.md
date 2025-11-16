# 06 — Security Model (Skeleton)

This document will define the security and detectability properties of the
Enigmatic protocol.

## 6.1 Adversary Model

- Passive chain observer  
- Active reordering / censorship adversary  
- Economic adversary (fee manipulation, dust attacks)  

## 6.2 Security Goals

- Steganographic indistinguishability
- Robust decoding for in-protocol participants
- Resistance to trivial pattern detection

## 6.3 Detectability & State-Plane Fingerprinting

Adversaries attempt to classify Enigmatic traffic by spotting correlated value/fee/cardinality combinations.

- **State-plane fingerprinting:** Statistical attacks that count occurrences of `21.21` or `0.21 ± ε` values across the chain.
- **Timing correlation:** Watching for strict `Δh = 3` sequences tied to the same wallet cluster.
- **Topology clustering:** Identifying mirrored `m = n` flows with lexicographic ordering.

Mitigation strategies:

1. **Header mixing:** Blend reserved headers with plausible decoy values per dialect to reduce chi-square signatures.
2. **Adaptive fee jitter:** Sample ε from a dialect-specific distribution that tracks mempool medians; ensures overlapping ranges with organic traffic.
3. **Symmetry perturbations:** Occasionally emit `σ = 0` neutral frames even in mirrored swarms to defeat simple classifiers.

## 6.4 Noise & Randomization Strategies

- **Fee jitter (ε):** Keep ε within wallet-acceptable ranges (e.g., ±5% of prevailing fee) so mempool policies accept the transaction while obscuring deterministic patterns.
- **Ordering randomization:** Use canonical ordering for “steady state” and revert to pseudo-random permutations (still valid) during cover traffic windows. Decoders rely on repetition counts and metadata to distinguish signal vs. cover.
- **Block alignment fuzzing:** Occasionally shift a frame by +1 block if DigiByte propagation delays would otherwise reveal a rigid schedule.

## 6.5 Relationship to Section 7

`specs/section7.md` formalizes the cryptographic assumptions (hash hardness, ECDSA security) and mutual-information bounds. Section 6 inherits those assumptions but focuses on pragmatic detectability defenses. Future revisions will merge redundant text by:

- Referencing Section 7 for proofs of `I(M;O) < δ` while keeping operational guidance here.
- Sharing a unified adversary capability matrix between §§6.1 and 7.2.
