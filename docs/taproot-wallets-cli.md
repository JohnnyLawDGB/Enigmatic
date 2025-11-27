# Taproot wallets with `digibyte-cli` (Linux)

Practical steps for creating and using a Taproot-ready descriptor wallet with
DigiByte Core 8.26.x. This wallet mirrors what Enigmatic uses for Taproot
inscriptions (e.g., `ord-plan-taproot`, `ord-inscribe`).

## 1. Requirements

- DigiByte Core **8.26.x**, fully synced.
- `digibyted` and `digibyte-cli` available in `PATH`.
- RPC credentials configured for your node.

## 2. Enable descriptor wallets

Edit `~/.digibyte/digibyte.conf` (create the file if it does not exist) and add
`descriptorwallet=1`. A minimal configuration looks like:

```conf
# ~/.digibyte/digibyte.conf
server=1
daemon=1
txindex=1
rpcuser=rpcuser
rpcpassword=rpcpass
descriptorwallet=1
```

Restart the node after saving the file:

```bash
digibyte-cli stop
digibyted -daemon
```

## 3. Create a Taproot-ready wallet

Create a descriptor wallet named `taproot-lab` with private keys enabled and
loaded automatically:

```bash
digibyte-cli createwallet "taproot-lab" false false "" true true true
```

`createwallet` parameters are, in order: `disable_private_keys`, `blank`,
`passphrase`, `avoid_reuse`, `descriptors`, and `load_on_startup` (the optional
`external_signer` flag is omitted here). The `false false "" true true true`
choices mean:

- `disable_private_keys=false` – the wallet can sign transactions.
- `blank=false` – load built-in descriptors so Taproot templates are available.
- `passphrase=""` – no encryption by default (use a passphrase if preferred).
- `avoid_reuse=true` – mark reused addresses as spent to discourage reuse.
- `descriptors=true` – enable descriptor-based wallet plumbing required for
  Taproot.
- `load_on_startup=true` – load the wallet automatically on node start.

## 4. Verify the wallet state

```bash
digibyte-cli -rpcwallet=taproot-lab getwalletinfo
```

Confirm the wallet reports `private_keys_enabled = true`, `descriptors = true`,
and `blank = false` before generating addresses.

## 5. Generate and inspect a Taproot address

Create a Bech32m (P2TR) receive address:

```bash
digibyte-cli -rpcwallet=taproot-lab getnewaddress "" bech32m
```

Validate the address details (replace `<ADDRESS>` with the output from the prior
command):

```bash
digibyte-cli -rpcwallet=taproot-lab getaddressinfo <ADDRESS>
```

Key fields to check:

- `iswitness = true`
- `witness_version = 1`
- `desc` begins with `tr(` (Taproot descriptor)

The `taproot-lab` wallet and its P2TR addresses are suitable for Enigmatic’s
Taproot inscription flows.
