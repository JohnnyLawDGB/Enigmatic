# Examples and Dialects

This directory acts as the "texture" layer for the specs. Each artifact shows
how theory looks when rendered into DigiByte transactions.

## Dialects

| File | Description |
| ---- | ----------- |
| `dialect-heartbeat.yaml` | Minimal heartbeat cadence used in README walkthroughs. Good for smoke-testing RPC flows. |
| `dialect-intel.yaml` | Replays the INTEL-style tri-anchor exchange described in the live experiments section. |

Both dialects can be fed into `scripts/enigmatic_rpc.py` via `--dialect` to plan
or broadcast state vectors.

## Narrative walkthroughs

| File | What it demonstrates |
| ---- | -------------------- |
| `example-transaction-pattern.md` | Step-by-step breakdown of a multi-anchor send. |
| `example-decoding-flow.md` | Mirrors how the decoder groups packets and infers intent. |
| `example1.md` / `example2.md` | Quick math exercises showing how value-plane encoding recovers integers. |
| `appendix_math.md` | Notes on the modular arithmetic backing the value plane. |
| `diagram_channels.png` | Visual showing overlapping channels; handy for presentations. |
| `2025-11-17-intel-continuation-analysis.md` | Continuation analysis of the 2025-11-17 DigiByte “intel” traffic, highlighting the 64.0 anchor and preserved invariants. |

When you add a new example, update this table with a short sentence describing
what a reviewer should look for.
