# 03 — Formal Model

This document provides a formal description of the Enigmatic protocol as a
Layer-0 communication layer on the DigiByte blockchain.

## 3.1 Ledger and Transaction Model

**Definition 3.1 (Ledger \(L\)).**  
Let \(L\) be the DigiByte blockchain, an append-only sequence of blocks:

\[
L = \{ B_0, B_1, ..., B_h \}
\]

where \(h\) is the current block height.

Each block \(B_i\) contains a set of transactions:

\[
B_i = \{ t_{i,1}, t_{i,2}, ..., t_{i,k_i} \}
\]

---

**Definition 3.2 (Transaction \(t\)).**  
A transaction \(t\) consists of:

- Inputs \( IN_t = \{ in_1, ..., in_m \} \)  
- Outputs \( OUT_t = \{ out_1, ..., out_n \} \)  
- Version, locktime, weight, and other consensus-relevant fields.  

Each output \( out_j \) has:

- Value \( v_j \in \mathbb{R}^+ \) (DGB)  
- ScriptPubKey \( s_j \)  

---

**Definition 3.3 (UTXO Set \(U\)).**  
At height \(h\), the UTXO set \(U_h\) is the set of all unspent outputs of
transactions in \(L\) up to height \(h\).

Enigmatic treats elements of \(U_h\) as **registers** in a distributed state
machine.

---

## 3.2 Encoding Planes

Enigmatic uses several orthogonal **encoding planes**:

1. **Value Plane \(V\)** — output values  
2. **Fee Plane \(F\)** — transaction fee  
3. **Cardinality Plane \(C\)** — input / output counts  
4. **Topology Plane \(G\)** — graph relationships  
5. **Block Plane \(H\)** — height and hash-derived entropy  
6. **Optional OP_RETURN Plane \(R\)** — explicit metadata  

Formally, for a transaction \(t\):

\[
\Pi(t) = (V_t, F_t, C_t, G_t, H_t, R_t)
\]

where:

- \(V_t = \{ v_1, ..., v_n \}\)  
- \(F_t = \sum IN_t - \sum OUT_t\)  
- \(C_t = (|IN_t|, |OUT_t|)\)  
- \(G_t\) is the local UTXO graph neighborhood  
- \(H_t = (height(t), hash(B_{height(t)}))\)  
- \(R_t\) is any OP_RETURN content.  

---

## 3.3 Message Space and Channel

Let \( \mathcal{M} \) be the space of abstract messages.  
A message \(M \in \mathcal{M}\) is a finite sequence of primitives:

\[
M = (p_1, p_2, ..., p_k)
\]

where each \(p_i\) is a symbol in some alphabet \(\Sigma\) (bytes, opcodes, tags).

We define a **channel** \( \mathcal{C} \) over DigiByte as:

\[
\mathcal{C}: \mathcal{M} \rightarrow \mathcal{T}^\*
\]

such that a message \(M\) is carried by a sequence of transactions
\( (t_1, ..., t_\ell) \in \mathcal{T}^\* \).

---

## 3.4 Encoding Function

The Enigmatic encoding function:

\[
\mathcal{E}: \mathcal{M} \rightarrow \mathcal{T}^\*
\]

must satisfy:

1. **Validity**: for all \( t \in \mathcal{E}(M) \), \(t\) is a valid DigiByte transaction.  
2. **Plausibility**: \( \Pi(t) \) falls within plausible ranges for organic wallet behavior.  
3. **Determinism (per dialect)**: given a fixed protocol dialect and seed, encoders produce a unique (or well-defined) class of transaction sequences.  
4. **Locality**: encodings should not require global UTXO control; they can be constructed using a wallet controlling a finite subset of \(U_h\).  

---

## 3.5 Decoding Function

The decoding function:

\[
\mathcal{D}: \mathcal{T}^\* \rightarrow \mathcal{M} \cup \{ \varnothing \}
\]

takes a transaction sequence and recovers the intended message, given:

- A protocol dialect \(D\)  
- A shared dictionary for:
  - header values  
  - bit-packets  
  - fee bands  
  - topology markers  

For a correctly formed Enigmatic message under dialect \(D\):

\[
\mathcal{D}_D(\mathcal{E}_D(M)) = M
\]

Otherwise, \(\mathcal{D}_D\) may yield:

- Partial messages  
- A parse error  
- The empty message \(\varnothing\)  

---

## 3.6 Constraints

To remain **Layer-0** and consensus-compatible, Enigmatic imposes:

- No new script opcodes  
- No non-standard scripts  
- No reliance on miner cooperation  
- No dependence on mempool-only behavior  

All behavior is encoded in data the consensus already understands:
values, fees, addresses, and block placement.

---

## 3.7 Security Objectives (Preview)

The formal security model (to be detailed in `/specs/06-security-model.md`) aims for:

1. **Steganographic Secrecy**: observers cannot easily distinguish Enigmatic
   traffic from ordinary DigiByte usage.  
2. **Robust Decodability**: authorized decoders reconstruct messages without
   ambiguity, given the correct dialect and keys.  
3. **Forward Secrecy (optional)**: when seeded from block hashes and
   ephemeral keys.  
4. **Graceful Degradation**: if the decoding rules or keys are lost, the
   funds remain fungible DGB with no protocol-level penalty.  
