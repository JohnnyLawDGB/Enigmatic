# Encode/Decode API Contract

Enigmatic can be called in two ways on a VPS: direct CLI execution or a minimal
HTTP JSON wrapper. Both options use the same encoding/decoding logic.

## Option A: CLI (subprocess)

Call `enigmatic-dgb` with arguments and parse stdout. This is the simplest
option if you already manage processes on the VPS.

Example (DTSP encode):

```bash
enigmatic-dgb dtsp-encode "HELLO"
```

Example (Taproot decode):

```bash
enigmatic-dgb ord-decode <txid> --json
```

All CLI commands exit non-zero on error and print `error: ...` to stderr.

## Option B: HTTP JSON API

Run the server:

```bash
enigmatic-api --host 0.0.0.0 --port 8123
```

Environment options:

- `ENIGMATIC_API_HOST`, `ENIGMATIC_API_PORT`
- `ENIGMATIC_API_ALLOW_ORIGIN` (CORS; leave empty for none)

For a systemd unit example, see `docs/VPS_SERVICE.md`.

### Endpoints

`POST /encode/dtsp`
- Request: `{ "message": "HELLO", "include_handshake": true, "include_accept": false }`
- Response: `{ "amounts": ["0.00022611", "..."], "sequence": "0.00022611,..." }`

`POST /decode/dtsp`
- Request: `{ "amounts": ["0.00022611", "..."], "strip_handshake": false, "tolerance": 1e-10, "show_matches": true }`
- Response: `{ "message": "HELLO", "matches": [{"amount":"0.00022611","symbol":"START","error":0.0}] }`

`POST /encode/binary`
- Request: `{ "text": "HI", "base_amount": "0.0001", "bits_per_char": 8 }`
- Response: `{ "amounts": ["0.00011001", "..."], "packets": [{"letter":"H","bits":"01001000","amount":"0.00011001"}] }`

`POST /decode/binary`
- Request: `{ "amounts": ["0.00011001", "..."], "base_amount": "0.0001", "bits_per_char": 8 }`
- Response: `{ "text": "HI" }`

`POST /decode/ord`
- Request: `{ "txid": "<txid>", "vout": 0 }`
- Response: `{ "payloads": [{ "txid":"...", "vout":0, "protocol":"enigmatic/taproot-v1", "decoded_json": {...} }] }`

`POST /plan/sequence`
- Request: `{ "to_address": "dgb1...", "amounts": ["0.1","0.2"], "fee": "0.21", "chained": false, "min_confirmations": 1, "use_utxos": ["txid:vout"] }`
- Response: `{ "plan": { ... }, "op_returns": [null,null] }`

`POST /send/sequence`
- Request: `{ "to_address": "dgb1...", "amounts": ["0.1","0.2"], "fee": "0.21", "chained": false, "min_confirmations": 1, "auto_prepare_utxos": true }`
- Response: `{ "txids": ["..."] }`

`POST /plan/pattern` and `POST /send/pattern`
- Same shape as the sequence endpoints; `op_return_*` is ignored for patterns.

Optional send parameters:
- `allow_unconfirmed` (bool)
- `single_tx` (bool)
- `min_confirmations_between_steps` (int)
- `wait_between_txs` (seconds)
- `max_wait_seconds` (seconds)
- `op_return_hex` or `op_return_ascii` (array of strings, length = amounts)
- `auto_prepare_fee` (DGB string)

### Errors

All errors return JSON with `{"error": "<message>"}` and a non-200 status. For
`ord-decode`, the server retries with the base RPC endpoint if a wallet-scoped
RPC cannot see a mempool transaction.

### Request RPC overrides

Every endpoint accepts an optional `rpc` object to override the default RPC
settings (useful when the VPS hosts multiple wallets):

```json
{
  "rpc": {
    "wallet": "JohnnyTest",
    "endpoint": "http://127.0.0.1:14022"
  }
}
```

### Security

Do not expose the HTTP API directly to the public internet. Run it behind a
private network, VPN, or authenticated reverse proxy.
