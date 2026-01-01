# Development TODOs

This document tracks outstanding TODO comments in the codebase for visibility and prioritization.

## Ordinals Module (Experimental)

### `ordinals/taproot.py`
- **Line 94**: Stricter script parsing for Taproot witnesses
- **Line 116**: Refine heuristic for Taproot path detection (currently permissive)

### `ordinals/indexer.py`
- **Line 66**: Support reverse iteration and negative offsets from chain tip
- **Line 89**: Implement OP_RETURN payload scraping and full Taproot-style witness parsing

### `ordinals/ownership.py`
- **Line 80**: Performance optimization - index transactions by address instead of full scans

### `ordinals/inscriptions.py`
- **Line 236**: Integrate TransactionBuilder.build_payment_tx for exact fee derivation
- **Line 292**: Thread hardened internal key handling through inscription flow
- **Line 489**: Replace placeholder with proper BIP341-style Taproot parsing

## Core Modules

### `watcher.py`
- **Line 111**: Use block timestamp from gettransaction RPC call when available

---

*Last updated: 2026-01-01*
