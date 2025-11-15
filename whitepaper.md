# Enigmatic — A Layer-0 Communication Protocol  
**DigiByte-Optimized Edition**

> This Markdown file mirrors the structure of the IEEE-style PDF whitepaper and
> serves as the canonical, Git-friendly version of the specification text.

## 1. Introduction

Enigmatic is a Layer-0, chain-native communication protocol that encodes
structured messages into DigiByte transactions without requiring any change to
consensus rules.

Transactions remain valid and economically meaningful, but when interpreted
under the Enigmatic ruleset, they also form a **steganographic message stream**.

(You can expand this section as you iterate on the PDF.)

## 2. Background and Design Rationale

- DigiByte UTXO model  
- Value precision and dust thresholds  
- Block times, multi-algo mining, and entropy sources  

(Expand with more detail from your PDF as it evolves.)

## 3. Formal Model

See [`../specs/03-formal-model.md`](../specs/03-formal-model.md).

---

As the whitepaper matures, this file should be kept in sync with any rendered
PDF versions committed under `docs/`.
