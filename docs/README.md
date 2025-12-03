# Documentation Guide

Enigmatic splits narrative docs from the formal specification so contributors
can find the right depth quickly.

## Whitepaper + architecture

| File | Why it exists |
| ---- | ------------- |
| `whitepaper.md` | Markdown version of the public whitepaper. Mirrors the PDF drafts in this folder. |
| `Enigmatic_L0_Whitepaper_Expanded*.pdf` | Printable snapshots of the evolving paper. Useful for reviewers who want layout accuracy. |
| `ARCHITECTURE.md` | Explains how the Python reference stack is layered (RPC, tx builder, encoder/decoder, watcher, CLI). |
| `expansion-roadmap.md` | Tracks future research directions and backlog items that are too verbose for GitHub issues. |

## Specification chapters (`../specs`)

Each spec file is intentionally short and focused. Start with the overview and
work down the list:

1. `01-protocol-overview.md` — Motivation, terminology, and the role of each
   state plane.
2. `02-encoding-primitives.md` — Value, fee, cardinality, topology, block
   placement, and auxiliary planes.
3. `03-formal-model.md` — State vectors, invariants, and reasoning about
   channel synchronization.
4. `04-encoding-process.md` — Step-by-step instructions for emitters.
5. `05-decoding-process.md` — Counterpart for observers.
6. `06-security-model.md` — Threats, deniability considerations, and mitigations.
7. `07-implementation-notes.md` — Practicalities for wallet/automation authors.
8. `08-dialects.md` — Examples of higher-level symbol packs built on the base
   primitives.

## How to contribute to docs

* Keep edits scoped to a single file whenever possible to simplify review.
* Link related changes from README/CONTRIBUTING so new readers can discover the
  updates.
* When adding diagrams, check them into `examples/` or `docs/` with a short ALT
  text description for accessibility.

## Operational runbooks

| File | Why it exists |
| ---- | ------------- |
| `digibyte-node-setup.md` | Quickstart for running a DigiByte 8.26 node with txindex, Dandelion relay, and Taproot defaults enabled. |
