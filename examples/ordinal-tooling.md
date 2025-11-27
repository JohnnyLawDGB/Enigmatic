# Ordinal-style tooling for Enigmatic

The Enigmatic CLI ships with two experimental helpers for exploring inscription-like
payloads on DigiByte: `ord-scan` and `ord-decode`. These commands operate on top of
an ordinary DigiByte Core node; they do **not** change consensus behavior or enforce
any ordinal-numbering rules. Think of them as an observational layer that surfaces
conventionally encoded data for analysis within the Enigmatic state-plane model.

## Running `ord-scan`

`ord-scan` walks a block range and reports outputs that look like inscription
candidates. Today that primarily means OP_RETURN outputs and Taproot-like witness
patterns. You can run the scanner against a locally running DigiByte node that is
exposed over JSON-RPC. The CLI reads standard RPC environment variables
(`DGB_RPCUSER`, `DGB_RPCPASSWORD`, `DGB_RPCPORT`, etc.) so you can reuse existing
wallet settings.

Example: scan the most recent 5 blocks for OP_RETURN inscriptions only.

```bash
export DGB_RPCUSER="rpcuser"
export DGB_RPCPASSWORD="rpcpass"
export DGB_RPCPORT="14022"  # adjust for your node

enigmatic-dgb ord-scan --start -5 --end 0 --limit 50 --no-taproot
```

Notes:

- Passing a negative `--start` offset counts back from the current best height.
- Use `--limit` to cap how many candidate outputs are returned.
- `--no-op-return` or `--no-taproot` can disable individual detection modes if
  you only want one style of signal.
- The output lists `txid`, `vout`, and `ordinal_hint` fields, plus tags like
  `op_return` or `taproot_like` so you can decide what to decode next.

## Using `ord-decode` on a specific transaction

Once you have a candidate `txid` and `vout`, use `ord-decode` to inspect the raw
payloads. The decoder will fetch the transaction, identify inscription-like
outputs using the same heuristics as the scanner, and attempt to render useful
text or JSON when possible.

```bash
enigmatic-dgb ord-decode --txid <txid>
```

Typical output includes:

- `raw_payload`: hex bytes pulled from OP_RETURN or witness data.
- `decoded_text`: UTF-8 rendering of the payload (replacement characters are
  used for invalid sequences).
- `decoded_json`: parsed JSON when the text looks like a JSON object.
- `protocol` and `codec`: placeholders describing how the payload was
  interpreted.
- `location`: the `txid`, `vout`, and `height` that anchor the observation.

You can target a specific output with `--vout <index>`; otherwise all inscription
candidates in the transaction are decoded.

## How this fits the state-plane model

Enigmatic’s state-plane design separates **observation** from **consensus**.
`ord-scan` and `ord-decode` live purely in the observational layer: they surface
payloads that appear to follow conventional ordinal-style practices but do not
assign canonical numbers or enforce ordering rules. DigiByte consensus nodes are
unaware of these conventions, and the tooling must remain resilient to missing or
malformed data.

When you interpret the output, keep in mind:

- Tags like `op_return` and `taproot_like` are hints, not guarantees of
  inscription semantics.
- Multiple inscriptions may coexist within a single transaction, and future
  versions may add deeper Taproot- and script-path parsing.
- Because this is experimental, downstream automation should treat the decoded
  data as advisory signals rather than protocol obligations.

## Next steps

This basic workflow provides a foundation for deeper analysis—such as correlating
inscriptions with Enigmatic channels or mapping payloads into state-plane
transitions. Future releases may add filtering by address, richer protocol
identification, and Taproot-aware parsing once signing support matures.
