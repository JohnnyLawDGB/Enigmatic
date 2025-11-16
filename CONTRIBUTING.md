# Contributing to Enigmatic

Thanks for lending brain cycles to this experiment. These notes compress the
tribal knowledge we've been passing around in chats into a concrete workflow so
new folks can get productive quickly.

## 1. Development setup

1. Install Python 3.9+.
2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .[dev]
   ```

3. Copy or export `DGB_RPC_*` environment variables if you plan to hit a live
   DigiByte node.
4. Run the test suite to ensure everything is wired up:

   ```bash
   pytest
   ```

## 2. Repository map

| Area | Purpose |
| ---- | ------- |
| `enigmatic_dgb/` | Reference Python package (encoder, decoder, watcher, CLI). |
| `scripts/` | Stand-alone utilities such as the RPC heartbeat planner. |
| `specs/` | Canonical protocol specification (formal model, encoding/decoding processes). |
| `docs/` | Long-form design notes and whitepaper drafts (see `docs/README.md`). |
| `examples/` | Concrete dial tones, message walkthroughs, and diagrams. |
| `tests/` | Pytest coverage of the encoder/decoder surface. |

## 3. Making changes

* Keep doc edits focused. If you're touching a spec, call it out in your PR
  description so reviewers can zero in on semantics.
* Python follows the standard library's style with type hints and `black`
  formatting. Run `black .` if you're touching logic-heavy modules.
* Favor pure functions in `enigmatic_dgb.*` modules; CLI/watcher glue should be
  the only place that holds state.
* If you add a new example or dialect, document it in `examples/README.md` so
  others know how to replay it.

## 4. Tests and validation

* `pytest` must pass for every PR.
* If you add RPC-facing functionality, include a dry-run example or describe
  how to trigger it against regtest/testnet.
* Docs/spec PRs should link to rendered previews or include enough screenshots
  so reviewers can check formatting.

## 5. Communication

* Draft PR summaries that explain **why** the change matters, not just what it
  does.
* Use GitHub discussions/issues to float protocol changes before writing code.
* Security reports? Email the maintainers privately instead of filing a public
  issue.

Thanks again for helping make Enigmatic easier to reason about and extend.
