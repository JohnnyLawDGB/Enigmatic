# DigiByte RPC Test Plan

This checklist describes integration tests that can be executed directly against a DigiByte node through the `enigmatic-dgb plan-symbol` and `send-symbol` commands. They are written so that an operator can run them against mainnet or testnet by simply adjusting RPC credentials and the target wallet.

## 1. Dialect Planning Dry Run
1. Ensure the automation dialect (e.g., `examples/dialect-heartbeat.yaml`) is up to date with the desired state planes.
2. Export RPC credentials via `DGB_RPC_USER` / `DGB_RPC_PASSWORD` or pass them to the CLI.
3. Run:
   ```bash
   enigmatic-dgb plan-symbol \
     --dialect-path examples/dialect-heartbeat.yaml \
     --symbol HEARTBEAT
   ```
4. Verify the printed JSON shows:
   - `inputs` length equals the symbol's `m` field.
   - `outputs` length equals `n` (including change branches).
   - `fee` matches the dialect definition.
5. Inspect `block_target` to confirm the planner respects the dialect's `delta` scheduling hint.

## 2. Broadcast and Confirm Heartbeat
1. Repeat the planning run with `--broadcast` and `--receiver-address <controlled DGB address>`.
2. Capture the returned `txid` and watch the node mempool via `getrawtransaction`.
3. Wait for the transaction to confirm, then decode it:
   ```bash
   digibyte-cli getrawtransaction <txid> 1
   ```
4. Assert the confirmed transaction preserves the planned output ordering and amounts (tolerating rounding to 8 decimal places).
5. Record the confirmation height to correlate with the dialect's timing delta.

## 3. Watcher End-to-End
1. Start the watcher in a dedicated terminal:
   ```bash
   enigmatic-dgb watch --address <receiver address> --poll-interval 10
   ```
2. Broadcast a symbol as in test 2.
3. Observe the watcher printing a decoded `EnigmaticMessage` JSON blob. Confirm the `channel`, `intent`, and payload metadata mirror the dialect definition.

## 4. Session-Gated Symbol
1. Establish a session using the handshake helpers (see `enigmatic_dgb.session` docstrings) and capture the base64 session key.
2. Invoke:
   ```bash
   enigmatic-dgb send-symbol \
     --dialect-path path/to/dialect.yaml \
     --symbol <session-required symbol> \
     --session-key-b64 <key> \
     --session-id <id> \
     --session-dialect <dialect name>
   ```
3. Verify the CLI succeeds only when the session metadata matches the dialect requirements. This ensures on-chain messages tied to sensitive intents cannot be emitted without a valid session context.

## 5. Fee / Dust Guardrails
1. Modify the dialect locally so that the symbol requests more outputs than the available change allows.
2. Run `enigmatic-dgb plan-symbol --broadcast` and expect the planner to exit with a descriptive error (`change per branch would be below dust limit`).
3. Record the failure, then revert the dialect to its canonical values.

Each of these tests exercises a different plane (cardinality, fee punctuation, timing, sessions) using the exact RPC surface the production agents rely on, so passing the checklist before a deployment gives high confidence that the node, wallet, and dialect files are aligned.
