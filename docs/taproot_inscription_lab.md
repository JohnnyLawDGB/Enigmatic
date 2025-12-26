# DigiByte Taproot Inscription Lab Guide

This lab walks you from a fresh DigiByte Core v8.26.x node to broadcasting your first Taproot inscription with the `enigmatic-dgb` CLI. It assumes you are comfortable with Linux and the DigiByte CLI but do not want to reverse engineer RPC error codes along the way.

## 1) Node readiness and Taproot activation

1. Confirm you are running DigiByte Core **v8.26.x or newer** and that Taproot has activated (any current mainnet node is past activation).
2. Minimal `digibyte.conf` for a local node:

   ```ini
   server=1
   txindex=1
   rpcuser=YOURUSER
   rpcpassword=YOURPASS
   rpcport=14022
   rpcbind=127.0.0.1
   rpcallowip=127.0.0.1

   # Optional for lab mode: lower relay fee so small-fee inscriptions relay
   # Tradeoff: lower policies may allow low-fee txs onto your node/mempool.
   minrelaytxfee=0.00001
   ```

3. Start `digibyted`, let it sync, and keep the node running for the rest of the lab.

## 2) Create a descriptor Taproot wallet (`taproot-lab`)

```bash
digibyte-cli createwallet "taproot-lab" true true "" true true true
digibyte-cli loadwallet "taproot-lab"   # "already loaded" is fine
digibyte-cli listwallets
```

Get a Taproot address and confirm its descriptor:

```bash
digibyte-cli -rpcwallet=taproot-lab getnewaddress "" bech32m
ADDR=<output_from_getnewaddress>
digibyte-cli -rpcwallet=taproot-lab getaddressinfo "$ADDR"
```

Expected fields: `"witness_v1_taproot": true` and a `tr(...)` descriptor.

## 3) Fund `taproot-lab` from another wallet on the same node

Assume a funding wallet named `JohnnyTest` already has DGB. Replace `DEST_ADDR` with your Taproot address and `AMT` with how much to send (example uses 10 DGB).

```bash
SRC_WALLET="JohnnyTest"
DEST_ADDR="<taproot-lab-address>"
AMT=10.0

# 1. Create a minimal raw tx with a placeholder output
RAW=$(digibyte-cli -rpcwallet="$SRC_WALLET" createrawtransaction "[]" \
  "[{\"$DEST_ADDR\": $AMT}]")

# 2. Let the wallet fund it
FUNDED=$(digibyte-cli -rpcwallet="$SRC_WALLET" fundrawtransaction "$RAW")
echo "$FUNDED"

# 3. Extract the funded hex and sign it
FUNDED_HEX=$(echo "$FUNDED" | jq -r .hex)
SIGNED=$(digibyte-cli -rpcwallet="$SRC_WALLET" signrawtransactionwithwallet "$FUNDED_HEX")
SIGNED_HEX=$(echo "$SIGNED" | jq -r .hex)

# 4. Broadcast
TXID=$(digibyte-cli sendrawtransaction "$SIGNED_HEX")
echo "$TXID"
```

Check balances from `taproot-lab`:

```bash
digibyte-cli -rpcwallet=taproot-lab getbalances
```

## Fee & mempool realities (DigiByte Core + Taproot inscriptions)

### Why `listunspent` can be empty even when you have balance

`listunspent` defaults to `minconf=1`, so a fresh 0-conf funding transaction will not appear. The wallet balance may still show “trusted” funds.

```bash
digibyte-cli -rpcwallet=<wallet> listunspent
digibyte-cli -rpcwallet=<wallet> listunspent 0 9999999 [] true
```

**Guidance:** wait for 1 confirmation before selecting funding UTXOs for commit/reveal to avoid fragile chains.

### Check whether your funding tx is actually in mempool

```bash
digibyte-cli getmempoolentry <txid>
```

The `height` field is when the transaction entered the mempool (not confirmations). A 0-conf transaction can still show a `height` value.

### RBF bumping a funding tx (`bumpfee`)

```bash
digibyte-cli -rpcwallet=<wallet> help bumpfee
```

- `fee_rate` is **sat/vB** on 0.21+ semantics.
- Do **not** combine `fee_rate` and `estimate_mode`; pick one.
- Node policy (incremental/required fee) can demand much larger total fees than a small “+10 sat/vB” bump.

Estimator-based bump:

```bash
digibyte-cli -rpcwallet=<wallet> bumpfee <txid> '{"conf_target": 2, "estimate_mode": "conservative"}'
```

Manual bump (example that satisfied a strict policy):

```bash
digibyte-cli -rpcwallet=<wallet> bumpfee <txid> '{"fee_rate": 10500, "replaceable": true}'
```

> **Warning:** After `bumpfee` succeeds, the old `txid` is invalidated. Re-query your wallet/UTXOs and use the new `txid` for inscriptions or spend selection.

Illustrative numbers from our run (not protocol requirements):

- Funding tx vsize ≈ 154 vB, initial fee ≈ 0.00003100 DGB (~20 sat/vB if 1 DGB = 1e8 sat-like units).
- `bumpfee` needed a total fee around 0.0155 DGB to clear policy; the manual bump above succeeded.
- `bumpfee` returned a new `txid`, and `walletconflicts` contained the old one.

### How to verify which txid actually confirmed

```bash
digibyte-cli -rpcwallet=<wallet> gettransaction <newtxid>
```

Useful fields:

- `confirmations`
- `walletconflicts` (shows the old `txid` if replaced)
- `replaces_txid` (old `txid`)

Then re-list spendable outputs:

```bash
digibyte-cli -rpcwallet=<wallet> listunspent
# or include 0-conf if you must:
digibyte-cli -rpcwallet=<wallet> listunspent 0 9999999 [] true
```

**Practical takeaway:** funding inscriptions with a confirmed UTXO is the boring but reliable path. If you use 0-conf, be explicit about mempool chaining and track replacement `txid`s.

## 4) Build a compact JSON payload (<= 520-byte script element)

Taproot inscriptions store the envelope in a single `PUSHDATA` element, so **520 bytes is the hard limit** for this lab. Avoid pretty-printed JSON or long keys unless you implement multi-chunk envelopes.

Example payload used for the first DigiByte Taproot inscription:

```bash
cat > dgb_ordinal_1.json << 'EOF'
{"p":"enigmatic/taproot-v1","k":"commemorative","t":"Enigmatic DigiByte Taproot Ordinal #1","m":"12 years, 21B DGB, first Enigmatic stego encode on DigiByte.","tags":["anniv","taproot","stego","ordinal","DGB"]}
EOF

MSG=$(cat dgb_ordinal_1.json)
```

## 5) Dry run: plan a Taproot inscription

Validate payload size, fee, and script layout without signing:

```bash
enigmatic-dgb ord-plan-taproot "$MSG" \
  --content-type application/json \
  --json
```

Key fields:

- `payload_length` should be > 0 and under 520.
- `taproot_script_hex` shows the unsatisfied leaf script.
- `estimated_fee` is the funding target.

If the payload is too large you will see:

```
ValueError: data too large for single script push: N bytes (max 520)
```

Use a more compact JSON (no pretty-printing) or implement chunked envelopes.

## 6) First signing dry run (no broadcast)

```bash
enigmatic-dgb ord-inscribe "$MSG" \
  --scheme taproot \
  --content-type application/json \
  --wallet taproot-lab \
  --max-fee-sats 100000 \
  --fee-rate-satvb 12000 \
  --no-broadcast
```

You should see a message like:

```
Broadcast disabled (--no-broadcast). Signed transaction (hex):
...
```

The hex is fully signed; you could broadcast it manually with `sendrawtransaction` if desired.

## 7) Broadcast the inscription

Using Enigmatic end-to-end:

```bash
enigmatic-dgb ord-inscribe "$MSG" \
  --scheme taproot \
  --content-type application/json \
  --wallet taproot-lab \
  --max-fee-sats 5000000 \
  --conf-target 2 \
  --estimate-mode conservative \
  --broadcast
```

Expected success message:

```
Broadcasted inscription transaction: <TXID>
```

Manual broadcast path (if you used `--no-broadcast`):

```bash
digibyte-cli sendrawtransaction "<SIGNED_HEX>"
```

## 8) Verify and decode

```bash
digibyte-cli getrawtransaction <TXID> 1
enigmatic-dgb ord-decode <TXID> --json
```

`ord-decode` should show the original JSON fields in the inscription payload.

## Troubleshooting & Common Errors

| Error text | Meaning | How to fix |
| --- | --- | --- |
| `ValueError: data too large for single script push: N bytes (max 520)` | Envelope is larger than the single-script-element limit. | Use compact JSON (no pretty printing or long keys) or implement multi-chunk envelopes. |
| `Invalid parameter, key-value pair must contain exactly one key` (code -8) | `createrawtransaction` outputs object is malformed. | Each output must be `{"address": amount}` or `{"data": "hex"}`. No extra keys. |
| `Invalid DigiByte address: script` (code -5) | You passed `"script"` as an output key to `createrawtransaction`. | Use an address string or `"data"` for OP_RETURN; do not use `"script"` in this context. |
| `min relay fee not met, FEE < THRESHOLD` (code -26) | Fee is below the node's `minrelaytxfee` policy. | Raise `--max-fee-sats` for the inscription, increase wallet `paytxfee` via `settxfee`, or lower `minrelaytxfee` in `digibyte.conf` for lab/test nodes. |
| `Your inscription payload is empty` | CLI received a zero-length payload. | Ensure the message/file contains data before calling `ord-plan-taproot` or `ord-inscribe`. |

If you hit an RPC broadcast failure, rerun with `--verbose` to log the JSON-RPC error body. The CLI will also print hints for the errors above.

### Troubleshooting checklist (fees/mempool)

- Run `listunspent` with/without `minconf=1` to confirm the funding UTXO is visible.
- Use `getmempoolentry <txid>` to see if the funding transaction is in the mempool (height ≠ confirmations).
- If bumping, pick **either** `fee_rate` (sat/vB) or `estimate_mode`, not both.
- Prefer passing `--fee-rate-satvb <value>` to avoid low-fee stalls. The CLI now logs `vsize`, `fee_rate`, and computed fee (sats/DGB) before broadcasting and will reject fees above `--max-fee-sats`.
- After `bumpfee`, capture the new `txid` and ignore the old one for commit/reveal.
- Re-run `gettransaction <newtxid>` and `listunspent` to verify the confirmed funding UTXO before inscribing.

## Quick reference commands

- Plan-only Taproot inscription: `enigmatic-dgb ord-plan-taproot "$MSG" --content-type application/json --json`
- Sign without broadcast: `enigmatic-dgb ord-inscribe "$MSG" --scheme taproot --wallet taproot-lab --no-broadcast`
- Broadcast immediately: `enigmatic-dgb ord-inscribe "$MSG" --scheme taproot --wallet taproot-lab --broadcast --max-fee-sats 5000000`
- Decode after mining/relay: `enigmatic-dgb ord-decode <TXID> --json`

## Fee & mempool realities

Taproot inscriptions ride inside normal DigiByte policy and mempool rules. Funding and commit transactions must satisfy feerate, RBF, and relay constraints just like any other transaction. The example below uses a **real, confirmed** Taproot funding transaction to ground the numbers.

### Worked example: Taproot funding transaction anatomy

- **Transaction metadata**
  - txid: `510100490839e0b934783eb795edb4d5162a637bf864b1976ad1f9fb36010a8c`
  - version: 2, locktime: 22688052, confirmations: >10
  - size: 205 bytes, **vsize: 154 vB**, weight: 616
  - inputs: 1 (Taproot key-path spend), outputs: 2 (both P2TR)
  - total fee paid: **0.01627500 DGB**

- **1) Size vs vsize vs weight**
  - Fee calculation uses **vsize**, not raw `size`.
  - Relationship: `weight = vsize * 4`. Here `616 weight / 4 = 154 vB`.
  - RBF and mempool limits are expressed in vbytes; always size transactions with `getmempoolentry`/`fundrawtransaction` outputs, not serialized byte length.

- **2) Fee calculation (real numbers)**
  - Fee paid: 0.016275 DGB → 1,627,500 base units (DGB has 1e8 base units just like BTC sats).
  - Effective feerate: `1,627,500 / 154 ≈ 10,570 sat/vB`.
  - This elevated feerate was needed to satisfy incremental relay/RBF requirements from prior replacements, **not** typical mainnet pressure. Expect far lower feerates in calm mempools.

- **3) Taproot input (key-path spend)**
  - No `scriptSig` bytes and a single-element `txinwitness` with one Schnorr signature.
  - That pattern signals a Taproot **key-path spend** (no script-path reveal or annex).

  Trimmed `getrawtransaction` (decoded) fragment:

  ```json
  {
    "vin": [
      {
        "txid": "...",
        "vout": 1,
        "scriptSig": { "asm": "", "hex": "" },
        "txinwitness": [
          "snr_sig_hex..."
        ]
      }
    ]
  }
  ```

- **4) Taproot outputs (P2TR)**
  - `vout 0`: **0.0001 DGB** postage-style output to a Taproot address.
  - `vout 1`: remaining balance returned to a Taproot change/funding output.
  - Both outputs show `"type": "witness_v1_taproot"` and `"address": "dgb1p..."` (bech32m).

  Trimmed outputs:

  ```json
  {
    "vout": [
      { "value": 0.00010000, "scriptPubKey": { "type": "witness_v1_taproot", "address": "dgb1p..." } },
      { "value": 9.98...,     "scriptPubKey": { "type": "witness_v1_taproot", "address": "dgb1p..." } }
    ]
  }
  ```

- **5) RBF lifecycle visibility**
  - `gettransaction` exposes RBF state during fee bumps: `replaces_txid`, `walletconflicts`, and `bip125-replaceable` flip from `"yes"` to `"no"` once confirmed.
  - After a successful `bumpfee`, the old txid is permanently invalid. Wallets and tooling must re-query UTXOs (`listunspent`) instead of assuming prior `txid:vout` pairs still exist.

  Example (trimmed after confirmation):

  ```json
  {
    "confirmations": 12,
    "replaces_txid": ["old_txid..."],
    "walletconflicts": [],
    "bip125-replaceable": "no"
  }
  ```

> **Why this matters for inscriptions**
> - Funding UTXOs should ideally confirm before commit/reveal.
> - RBF is powerful but can force unexpectedly high feerates after repeated bumps.
> - Never hardcode txids or vout indexes after a bump; always trust `listunspent`.
