# Taproot Inscription Implementation Fix Plan

## Problem Summary

The current `ord-inscribe --scheme taproot` command **does not actually create Taproot inscriptions**.

### What It Currently Does (WRONG):
1. Plans a Taproot leaf script with the inscription envelope ✓
2. Encodes the script as `OP_FALSE OP_IF <ENIG envelope> OP_ENDIF` ✓
3. **Then just sends 0.0001 DGB to a random bech32m address** ✗
4. **Never embeds the inscription in a Taproot script tree** ✗

### Evidence:
**File: `enigmatic_dgb/cli.py` lines 2351-2363**
```python
else:  # taproot scheme
    try:
        inscription_address = rpc.getnewaddress(address_type="bech32m")
    except TypeError:
        inscription_address = rpc.getnewaddress()

    outputs_payload = [{inscription_address: 0.0001}]
    raw_tx = builder.build_custom_tx(
        outputs_payload,
        float(guess_fee_dgb),
        fee_rate_override=fee_rate_override,
        replaceable=args.rbf,
    )
```

**File: `enigmatic_dgb/ordinals/workflows.py` lines 165-177**
```python
else:  # taproot
    try:
        inscription_address = rpc.getnewaddress(address_type="bech32m")
    except TypeError:
        inscription_address = rpc.getnewaddress()

    outputs_payload = [{inscription_address: 0.0001}]
    raw_tx = builder.build_custom_tx(
        outputs_payload,
        float(guess_fee_dgb),
        fee_rate_override=fee_rate_override,
        replaceable=rbf,
    )
```

The variable `inscription_hex` from line 2306 is **calculated but never used**!

## What Should Happen (Bitcoin Ordinals / BIP341 Taproot Pattern)

### Taproot Inscription Architecture

A proper Taproot inscription requires a **two-transaction flow**:

#### Transaction 1: COMMIT (what we need to fix)
1. Create a **Taproot leaf script** containing the inscription (already done correctly)
2. Choose or generate an **internal key** (32-byte x-only public key)
3. Compute the **merkle root** from the leaf script using BIP340 tagged hashing
4. **Tweak the internal key** with the merkle root to produce the **output key**
5. Create a **P2TR output**: `OP_1 <32-byte output key>`
6. Build and sign a transaction that **sends funds to this Taproot output**
7. Broadcast the commit transaction

#### Transaction 2: REVEAL (future work, not needed for commit)
- Spend FROM the Taproot output using the script-path
- Provide the control block, internal key, and satisfy the leaf script
- This "reveals" the inscription on-chain

**Critical insight**: The inscription is embedded in the **output's script tree**, not just sent to any Taproot address.

## Implementation Plan

### Step 1: Create Taproot Output Builder Utility

**New file: `enigmatic_dgb/ordinals/taproot_builder.py`**

Core functions needed:
- `tagged_hash(tag: str, data: bytes) -> bytes` - BIP340 tagged hashing
- `taproot_tweak_pubkey(internal_key: bytes, merkle_root: bytes) -> tuple[bytes, int]` - BIP341 tweaking
- `compute_taproot_output_from_script(leaf_script: bytes, internal_key: bytes) -> dict`
  - Returns: `{output_script_hex, output_key, merkle_root, control_block}`
- `create_taproot_address(output_key: bytes) -> str` - Encode as bech32m for DigiByte

Dependencies:
- Use `hashlib.sha256` for tagged hashing
- May need `bech32` library (check if already available)
- Reference: BIP340, BIP341 specifications

### Step 2: Integrate Into `OrdinalInscriptionPlanner`

**File: `enigmatic_dgb/ordinals/inscriptions.py`**

Modify `plan_taproot_inscription` to:
1. Generate or accept an internal key (default: use a proper key, not `00*32`)
2. Compute the Taproot output details using the new builder
3. Include in plan metadata:
   - `internal_key_hex`
   - `output_key_hex`
   - `merkle_root_hex`
   - `control_block_hex`
   - `taproot_address` (for sending funds to)

### Step 3: Update Transaction Building Flow

**File: `enigmatic_dgb/ordinals/workflows.py` lines 165-177**

Replace the current broken logic:
```python
# BEFORE (wrong):
inscription_address = rpc.getnewaddress(address_type="bech32m")
outputs_payload = [{inscription_address: 0.0001}]

# AFTER (correct):
from .taproot_builder import create_taproot_address, compute_taproot_output_from_script

# Get the leaf script from the plan
leaf_script_hex = plan.get("metadata", {}).get("taproot_script_hex")
leaf_script = bytes.fromhex(leaf_script_hex)

# Get or generate internal key
internal_key_hex = plan.get("metadata", {}).get("internal_key_hex")
internal_key = bytes.fromhex(internal_key_hex)

# Build the Taproot output with the inscription embedded
taproot_output = compute_taproot_output_from_script(leaf_script, internal_key)
inscription_address = create_taproot_address(taproot_output["output_key"])

# Now send to this address (this commits the inscription)
outputs_payload = [{inscription_address: 0.0001}]
```

**File: `enigmatic_dgb/cli.py` lines 2351-2363** - Apply same fix

### Step 4: Internal Key Management

**Options for internal key generation:**

Option A: **Derive from wallet**
- Use `getdescriptorinfo` or `deriveaddresses` from the wallet
- Extract the x-only pubkey from a descriptor
- Pros: Provably owned by wallet
- Cons: More complex RPC integration

Option B: **Unspendable key (Bitcoin Ordinals pattern)**
- Use a fixed unspendable key (e.g., H point or similar)
- Pros: Simple, matches Ordinals conventions
- Cons: Funds sent to reveal output are unrecoverable via key-path

Option C: **Generate ephemeral key**
- Generate a random 32-byte key for each inscription
- Pros: Simple implementation
- Cons: Not recoverable without saving the key

**Recommendation**: Start with Option B (unspendable key) to match Bitcoin Ordinals behavior, document clearly that key-path spending is not available.

### Step 5: Update Tests

**File: `tests/test_taproot_dialect_v1.py`**

Add tests for:
- `tagged_hash` correctness (use BIP340 test vectors)
- `taproot_tweak_pubkey` (use BIP341 test vectors)
- `compute_taproot_output_from_script` - verify merkle root calculation
- End-to-end: plan → build → verify output is P2TR with correct pubkey

### Step 6: Documentation Updates

**File: `docs/taproot_inscription_lab.md`**

Add section explaining:
- Commit vs Reveal transactions
- Why the inscription address is deterministic from the leaf script
- How to verify the inscription is embedded (decode the output)
- Internal key choices and implications

## Technical References

### BIP340 Tagged Hashing
```python
def tagged_hash(tag: str, msg: bytes) -> bytes:
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + msg).digest()
```

### BIP341 Taproot Tweaking
```python
def taproot_tweak_pubkey(internal_key: bytes, merkle_root: bytes) -> tuple[bytes, int]:
    # internal_key: 32-byte x-only pubkey
    # merkle_root: 32-byte hash (or empty bytes for key-path only)
    t = tagged_hash("TapTweak", internal_key + merkle_root)
    # Point addition (requires secp256k1 library or equivalent)
    # Returns (tweaked_pubkey, parity)
```

### Merkle Root for Single Leaf
```python
def taproot_tree_hash(leaf_script: bytes) -> bytes:
    leaf_version = 0xc0  # TAPROOT_LEAF_TAPSCRIPT
    leaf_hash = tagged_hash("TapLeaf", bytes([leaf_version]) + compact_size(len(leaf_script)) + leaf_script)
    return leaf_hash  # For single leaf, merkle_root = leaf_hash
```

## Implementation Priority

1. **High**: `taproot_builder.py` core utilities
2. **High**: Update `workflows.py` and `cli.py` transaction building
3. **Medium**: Proper internal key handling
4. **Medium**: Update planner to include full Taproot output details
5. **Low**: Tests and documentation (but do validate manually!)

## Success Criteria

After implementation, verify:
1. `ord-inscribe --scheme taproot` creates a transaction with a P2TR output
2. The output's pubkey is the **tweaked** key (internal_key + merkle_root)
3. `ord-decode <txid>` can extract the inscription from the Taproot script tree
4. The inscription is visible in the witness when spending the output (reveal)

## Notes

- The current receipts show successful "taproot" inscriptions, but these are likely just payments to random Taproot addresses with no inscription data
- The envelope encoding (`encode_enig_taproot_payload`) and leaf script building (`build_enig_leaf`) are correct
- The bug is purely in the transaction construction - we plan correctly but don't execute the plan
- This is a critical bug that makes the entire Taproot inscription feature non-functional
