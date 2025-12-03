# DigiByte 8.26 Node Startup and Configuration Guide

This guide captures a minimal, reproducible way to bring up a DigiByte 8.26 node with full indexing, Dandelion transaction relay, and Taproot enabled. Commands assume a Linux host with `digibyted` and `digibyte-cli` available on `PATH`.

## 1) Prepare data and configuration directories

```bash
# Create a dedicated data directory for mainnet (adjust paths as needed)
export DGB_DATA="$HOME/.digibyte"
mkdir -p "$DGB_DATA"
```

Create or update `$DGB_DATA/digibyte.conf` with the following baseline configuration:

```ini
# Core daemon behaviour
server=1
daemon=1
listen=1
maxconnections=64

# RPC (update credentials!)
rpcuser=dgb_rpc_user
rpcpassword=change_this_password
rpcallowip=127.0.0.1
# Add more rpcallowip lines if you proxy requests from other hosts.

# Full indexing
# Keeps the full transaction index for historical queries and scripting work.
txindex=1

# Dandelion transaction relay privacy
# Enabled by default in 8.26, but kept explicit for clarity.
dandelion=1
# Optional tuning for epoch/fluff settings (defaults are usually fine)
# dandelion-stems=1

# Taproot usage for new wallet addresses
# Bech32m ensures new addresses and change outputs use Taproot.
addresstype=bech32m
changetype=bech32m

# Logging quality-of-life
logtimestamps=1
logips=1
```

> Tip: if you run testnet or a custom datadir, add `testnet=1` (or `-testnet` on the command line) and point `-datadir` to a separate folder to keep chains isolated.

## 2) Start the node

Run the daemon directly, pointing at the config and datadir created above:

```bash
digibyted -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" \
  -txindex=1 -dandelion=1
```

*The CLI flags mirror the config values to make intent obvious on first start; subsequent launches only need the config file.*

To follow progress, tail the log:

```bash
tail -f "$DGB_DATA/debug.log"
```

## 3) Basic `digibyte-cli` commands

Once the node starts syncing, you can interact with it via the CLI. Each command assumes the same `-conf` and `-datadir` paths as above.

| Purpose | Command |
| --- | --- |
| Node health and block status | `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getblockchaininfo` |
| Peer/network status | `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getnetworkinfo` |
| Wallet balance | `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getbalance` |
| New Taproot address (bech32m) | `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getnewaddress "" bech32m` |
| Broadcast raw transaction | `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" sendrawtransaction <hex>` |
| Check mempool | `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getrawmempool` |

## 4) Verifying indexing, Dandelion, and Taproot

1. **Full transaction index**: `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getindexinfo` should show `"txindex": { "synced": true }` once fully built. Initial indexing can take hours and consumes additional disk.
2. **Dandelion**: `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getnetworkinfo` should include `dandelion` in the `localservices` list. You can also search `debug.log` for `dandelion` to confirm the stem/fluff relay is active after startup.
3. **Taproot activation**: `digibyte-cli -conf="$DGB_DATA/digibyte.conf" -datadir="$DGB_DATA" getblockchaininfo` reports `"taproot": { "status": "active" }` under `softforks`. If absent, ensure you are on DigiByte mainnet and fully synced.

## 5) Common startup issues

- **Missing indexes**: If `getindexinfo` shows `txindex` missing or `synced=false`, stop the node, ensure `txindex=1` is set, and restart. An index rebuild can be forced with `-reindex` (expensive) if the node was previously started without txindex.
- **Privacy checks**: If Dandelion does not appear in `localservices`, confirm `dandelion=1` is set and no conflicting `-noprivacy` flags are present.
- **Taproot addresses**: Ensure `addresstype=bech32m` and `changetype=bech32m` are present so newly created addresses default to Taproot. Legacy wallets can still send to Taproot outputs without extra configuration.

With these steps in place, a DigiByte 8.26 node will sync with full historical data, relay transactions with Dandelion privacy, and generate Taproot-ready wallet addresses by default.
