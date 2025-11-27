# Enigmatic DigiByte Architecture

## 0. Overview

`enigmatic-dgb` is a Python reference stack for legitimate, experimental messaging over DigiByte. It treats the DigiByte blockchain as a constrained transport where semantic intents are expressed through patterned payments and fees. The project intentionally avoids any evasion or wrongdoing; it simply exposes research tooling for encoding, decoding, and observing these patterns.

## 1. Layered design

### 1.1 RPC Client (`enigmatic_dgb.rpc_client`)
* Handles JSON-RPC communication with a DigiByte Core–style node.
* Provides typed helpers for standard RPC methods, plus error handling and logging.
* Configuration flows from environment variables and is shared by the rest of the stack.

### 1.2 Transaction + UTXO layer (`enigmatic_dgb.tx_builder`)
* Supplies a `UTXOManager` for querying and selecting unspent outputs.
* Builds and signs raw transactions, using `fundrawtransaction` when available or falling back to manual selection.
* Does **not** embed any Enigmatic semantics; it simply executes payment instructions with explicit fees.

### 1.3 Domain model (`enigmatic_dgb.model`)
* Declares `EnigmaticMessage`, anchor/micro pattern helpers, and `EncodingConfig` with defaults.
* Keeps protocol semantics decoupled from transport.

### 1.4 Encoder (`enigmatic_dgb.encoder`)
* Maps a high-level `EnigmaticMessage` onto deterministic `SpendInstruction` objects (anchors, micros, punctuation fee).
* The output is consumed by the transaction builder; no RPC interaction occurs in this layer.

### 1.5 Decoder (`enigmatic_dgb.decoder`)
* Provides `ObservedTx`, packet grouping utilities, and `EnigmaticDecoder` for inferring intents/payloads from observed anchors/micros.
* Operates on data supplied by watchers/indexers.

### 1.6 Watcher (`enigmatic_dgb.watcher`)
* Polls the DigiByte node for activity touching configured addresses.
* Converts new activity into `ObservedTx`, groups packets, and emits decoded `EnigmaticMessage` objects via callbacks.

### 1.7 Ordinal-style inscription tooling (`enigmatic_dgb/ordinals/`)
* Optional, experimental layer for observing and decoding inscription-like data (OP_RETURN payloads and Taproot-style witness segments).
* Reuses the shared `rpc_client` utilities to walk blocks/transactions without altering consensus rules.
* `indexer.py` surfaces candidate locations, `inscriptions.py` decodes OP_RETURN and Taproot dialect payloads, and `taproot.py` inspects witness/state for heuristic matches. Public re-exports live in `enigmatic_dgb.ordinals` and are also exposed at the package root for discoverability.
```
[rpc_client]
    |-- watcher.py --> decoder.py (address-focused flows)
    \-- ordinals/indexer.py --> ordinals/inscriptions.py (inscription-like flows)
```

### 1.8 CLI (`enigmatic_dgb.cli`)
* Exposes `enigmatic-dgb` entry point with `send-message`, `watch`, and the `ord-*` subcommands.
* `send-message` orchestrates encoding plus transaction submission.
* `watch` runs the RPC-based watcher and prints decoded packets as JSON lines.
* Ordinal helpers (`ord-scan`, `ord-index`, `ord-mine`, `ord-decode`, `ord-plan-*`, `ord-inscribe`) reuse the shared RPC client for OP_RETURN and Taproot-dialect payloads. Broadcasting is opt-in for inscription creation, guarded by fee caps and warnings; `--verbose` emits detailed RPC traces for troubleshooting.

### 1.9 Tests (`tests/`)
* `test_enigmatic_roundtrip.py` covers encoder/decoder interoperability and packet grouping heuristics.

## 2. Data flow

### 2.1 High-level message -> blockchain
1. User/script constructs `EnigmaticMessage` using `EncodingConfig`.
2. `EnigmaticEncoder` converts the message into `SpendInstruction` objects + punctuation fee.
3. Instructions are aggregated into address/amount outputs.
4. `TransactionBuilder` selects UTXOs and builds/signs a raw transaction that implements the pattern with the requested fee.
5. `DigiByteRPC` broadcasts the signed transaction.

### 2.2 Blockchain -> decoded message
1. `Watcher` polls RPC (or external indexer) for transactions affecting a watched address.
2. New hits are wrapped as `ObservedTx` and fed to `group_into_packets`, which segments bursts by configurable time gaps.
3. `EnigmaticDecoder` inspects anchors, micros, and punctuation fees to infer `intent` plus a coarse payload.
4. The resulting `EnigmaticMessage` objects are delivered to callbacks (CLI prints JSON, services may enqueue events, etc.).

## 3. Directory structure

```
enigmatic_dgb/
  __init__.py
  rpc_client.py
  tx_builder.py
  model.py
  encoder.py
  decoder.py
  watcher.py
  cli.py
tests/
  test_enigmatic_roundtrip.py
```

This layout keeps clean separations between node access, transaction mechanics, domain semantics, and user-facing tools while reinforcing the intent that Enigmatic is an experimental, above-board signaling experiment.
