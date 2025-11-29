# What’s Next — Enigmatic Roadmap

This roadmap aligns upcoming work with the current implementation surface:
`enigmatic_dgb/`, `specs/`, `docs/`, `examples/`, and `tests/`. Milestones are
organized into near-term (current cycle) and mid-term (upcoming cycles) to keep
the protocol, tooling, and documentation in lockstep.

## Near-term (reference stack hardening)

- **Wallet/RPC ergonomics**: Expand dialect-level RPC overrides, add clearer
  error surfaces for missing wallets, and document hardware-wallet safe signing
  flows (`docs/TOOLING.md`).
- **Planner fidelity**: Surface block-placement expectations in `plan-*`
  summaries, emit clearer change-linking visuals, and add regression tests for
  chained frame reuse (`tests/`).
- **Dialect registry scaffolding**: Publish a canonical index in
  `examples/README.md`, plus linting for YAML structure and reserved plane
  markers (`specs/06-dialects.md`).
- **Detection playbooks**: Extend `specs/05-decoding-process.md` with sliding
  window heuristics and add watcher examples that score fee bands and symmetry.
- **Documentation parity**: Finalize whitepaper TODOs (timing diagrams,
  orthogonality proof sketch) and keep README/tooling guides synchronized with
  the CLI surface.

## Mid-term (feature expansion)

- **Production-grade wallet integrations**: Pluggable signers (hardware wallets,
  PSBT flows) and retryable broadcast paths for chained frames.
- **Multi-chain experiments**: Validate the state-plane approach on additional
  UTXO chains while retaining DigiByte as the reference substrate; factor chain
  abstractions into the planner where feasible.
- **Community dialect registry**: Hosted index with replay fixtures, semantic
  versioning, and automated `plan-symbol --dry-run` checks for submissions.
- **Observability & analytics**: Dashboard-friendly watcher outputs, optional
  metrics exporters, and pattern detection frameworks for threat modeling.
- **Pattern detection research**: Formalize indistinguishability bounds for fee
  jitter and block cadence; publish detection-resistance benchmarks alongside
  example countermeasures.
- **Layered audio encoding**: Prototype keyed thread extraction for layered
  audio recordings so only holders of the right keys can decode ordered streams
  from otherwise chaotic mixes, targeting both security and compression
  benefits.

## Adoption milestones

- **Spec completeness**: All TODO markers resolved in specs and whitepaper.
- **CLI parity**: Every documented command (`plan-symbol`, `plan-chain`,
  `plan-sequence`, `plan-pattern`, `send-symbol`, `send-message`, `watch`) has a
  replayable example in `examples/` and regression coverage in `tests/`.
- **Dialect lifecycle**: New dialects must ship with dry-run outputs, decoded
  walkthroughs, and RPC setup notes to keep reproducibility intact.
