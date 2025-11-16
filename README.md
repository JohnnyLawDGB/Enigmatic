# Enigmatic — A Layer-0 Communication Protocol (DigiByte-Optimized)

**Enigmatic** is a Layer-0 communication protocol that uses DigiByte’s native
UTXO, fee, and transaction topology space as a *steganographic message channel*.

Instead of adding new opcodes or data layers, Enigmatic treats:

- Values (e.g. `21.21`, `7.00`, `0.978521`, `0.0100xxxx`)
- Fees (e.g. `0.21`, `21.0`)
- Input / output cardinalities (e.g. `21 in / 21 out`)
- Transaction graph shapes
- Optional `OP_RETURN` anchors

as **programmable symbols** in a formally defined encoding scheme.

### State Planes Quick Reference

| Plane             | Conveyed variables                              | Example usage                          | Specification links |
| ----------------- | ------------------------------------------------ | -------------------------------------- | ------------------- |
| **Value**         | Amount, repetition, fee invariance headers       | `21.21` / `7.00` alternating beacons   | [`specs/02-encoding-primitives.md`](specs/02-encoding-primitives.md) |
| **Fee**           | Timing offsets, jitter bands                     | `0.21` cadence to mark heartbeats      | [`specs/02-encoding-primitives.md`](specs/02-encoding-primitives.md) |
| **Cardinality**   | Input/output sizes, ordering, cluster symmetry   | `21 in / 21 out` mirrored swarms       | [`specs/03-formal-model.md`](specs/03-formal-model.md) |
| **Topology**      | Output structure, graph motifs, ordering windows | Fan-out trees, ring confirmations      | [`specs/03-formal-model.md`](specs/03-formal-model.md) |
| **Block placement** | Block interval alignment, timing, repetition   | `Δheight = 3` heartbeat scheduling     | [`specs/04-encoding-process.md`](specs/04-encoding-process.md), [`specs/05-decoding-process.md`](specs/05-decoding-process.md) |
| **Auxiliary (OP_RETURN / metadata)** | Optional payload hints        | Hash commitments, dialect selectors    | [`specs/01-protocol-overview.md`](specs/01-protocol-overview.md) |

Each plane evolves independently yet composes into a **state vector** (amount, fee, cardinality, topology, block placement) that conveys telemetry-style information rather than plaintext characters.

### Telemetry vs. Cipher Framing

- **Telemetry mindset:** Treat transactions as multi-dimensional heartbeats or consensus proofs. Variables such as timing, repetition, and cluster symmetry act like sensor channels that reveal system state to peers observing the ledger.
- **Classical cipher mindset:** Focuses on transforming ASCII payloads via substitution or encryption before transport. Enigmatic intentionally avoids this framing; the message emerges from how state variables co-vary across planes.
- **Implication for contributors:** When designing new dialects, think in terms of *state synchronization* and *multi-agent negotiation* (see `specs/04-encoding-process.md` and `specs/05-decoding-process.md`) rather than letter-level encoding tricks.

This repository contains the **protocol specification**, **whitepaper**, and
**reference examples** for Enigmatic on DigiByte.

---

## Goals

- Define a **chain-native, consensus-compatible signaling protocol**.
- Leverage DigiByte as a **global, timestamped, censorship-resistant message bus**.
- Preserve **plausible deniability** and normal wallet semantics.
- Provide a **formal model** that cryptographers, protocol designers and
  implementers can build upon.

---

## Status

- 📄 Whitepaper: **DigiByte-optimized, IEEE-style structure (in progress)**
- ✅ Formal model: Section 3 drafted in `/specs/03-formal-model.md`
- 🧪 Examples: UTXO patterns & decoding flows in `/examples`

---

## Repository Layout

```text
docs/
  whitepaper.md        # human-readable whitepaper version (Markdown)

specs/
  01-protocol-overview.md
  02-encoding-primitives.md
  03-formal-model.md
  04-encoding-process.md
  05-decoding-process.md
  06-security-model.md
  07-implementation-notes.md
  08-dialects.md

examples/
  example-transaction-pattern.md
  example-decoding-flow.md
  dialect-heartbeat.yaml
```

You can also place a PDF version of the whitepaper in `docs/`:

- `docs/Enigmatic_L0_Protocol.pdf`

---

## High-Level Idea

Enigmatic defines:

- A **message space** \\( \mathcal{M} \\): abstract protocol primitives (opcodes, bytes, tags)
- An **encoding function** \\( \mathcal{E}(M) \rightarrow t \\): which maps message
  primitives into concrete DigiByte transactions
- A **decoding function** \\( \mathcal{D}(t) \rightarrow M' \\): which recovers the
  intended symbols from the transaction graph

All encodings are:

- Valid DigiByte transactions  
- Economically plausible  
- Steganographic by default: transaction flows look like normal wallet behavior  

---

## Scope and Non-Goals

**In scope:**

- Formal definitions and proofs-of-concept  
- Encoding / decoding specifications  
- Security and detection analysis  
- Reference implementation notes  

**Out of scope (for now):**

- Production wallet integrations  
- Miner policy changes  
- Any DigiByte consensus modifications  

---

## License

This project is licensed under the **MIT License**.  
See [`LICENSE`](./LICENSE) for details.
