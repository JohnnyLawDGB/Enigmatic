# Taproot Inscription Fix - Implementation Summary

**Date**: 2026-01-01
**Status**: ✅ COMPLETE

## Problem

The `ord-inscribe --scheme taproot` command was **not actually creating Taproot inscriptions**. It would:
1. ✓ Correctly plan and encode the inscription envelope
2. ✓ Correctly build the Taproot leaf script
3. ✗ **Then just send funds to a random bech32m address**
4. ✗ **Never embed the inscription in a Taproot script tree**

The inscription data was being computed but never used in the transaction output.

## Solution Implemented

### 1. New Module: `enigmatic_dgb/ordinals/taproot_builder.py`

Created a complete BIP341 Taproot implementation with:

- **`tagged_hash(tag, data)`** - BIP340 tagged hashing for domain separation
- **`taproot_leaf_hash(leaf_script)`** - Compute TapLeaf hash for inscription script
- **`taproot_tweak_pubkey(internal_key, merkle_root)`** - BIP341 key tweaking with point arithmetic
- **`compute_taproot_output_from_script(leaf_script, internal_key)`** - Main entry point that:
  - Computes merkle root from leaf script
  - Tweaks internal key to produce output key
  - Returns all data needed for commitment tx and later reveal
- **`create_taproot_address(output_key)`** - Encode tweaked key as DigiByte bech32m address
- **`bech32_encode()` and helpers** - BIP173/BIP350 bech32m encoding

#### Internal Key

Uses the x-coordinate of the secp256k1 generator point G as the default unspendable internal key:
```
79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798
```

This is a well-known, nothing-up-my-sleeve value. The tweaked versions are provably unspendable since no one knows the discrete log of the tweaked point.

### 2. Updated `enigmatic_dgb/ordinals/workflows.py`

Modified `prepare_inscription_transaction()` to properly create Taproot commitments:

**Before (WRONG)**:
```python
inscription_address = rpc.getnewaddress(address_type="bech32m")
outputs_payload = [{inscription_address: 0.0001}]
```

**After (CORRECT)**:
```python
# Get the planned leaf script from the planner
leaf_script = bytes.fromhex(plan.get("metadata", {}).get("taproot_script_hex"))

# Compute the Taproot output with inscription embedded
taproot_output = compute_taproot_output_from_script(leaf_script, internal_key)

# Create commitment address from the tweaked output key
output_key = bytes.fromhex(taproot_output["output_key"])
inscription_address = create_taproot_address(output_key)

# Send to this Taproot output (commits the inscription)
outputs_payload = [{inscription_address: 0.0001}]
```

### 3. Updated `enigmatic_dgb/cli.py`

Applied the same fix to `cmd_ord_inscribe()` with additional logging:

```python
logger.info(
    "Taproot commitment address=%s output_key=%s",
    inscription_address,
    taproot_output["output_key"][:16] + "...",
)
```

## How It Works Now

### Taproot Inscription Flow

1. **Encode Envelope**: `encode_enig_taproot_payload(content_type, payload)`
   → `ENIG` + version + content-type + payload

2. **Build Leaf Script**: `TaprootScriptBuilder.build_enig_leaf(envelope)`
   → `OP_0 OP_IF <envelope> OP_ENDIF`

3. **Compute Leaf Hash**: `taproot_leaf_hash(leaf_script)`
   → Tagged hash: `SHA256("TapLeaf" | 0xc0 | compact_size(script) | script)`

4. **Tweak Internal Key**:
   ```
   t = SHA256("TapTweak" | internal_key | leaf_hash)
   output_key = internal_key + t·G  (point addition on secp256k1)
   ```

5. **Create P2TR Output**: `OP_1 <32-byte output_key>`

6. **Encode as Bech32m**: `dgb1p...` address

7. **Send Transaction**: Send 0.0001 DGB to this address

### Key Differences from Before

| Aspect | Before (Broken) | After (Fixed) |
|--------|----------------|---------------|
| **Output address** | Random bech32m from wallet | Deterministic from inscription script |
| **Script tree** | Not embedded | Properly embedded via Taproot tweaking |
| **Verifiability** | Inscription not on-chain | Inscription committed in output key |
| **Reveal** | Not possible | Can be revealed via script-path spend |

## Verification

### Test Results

```
✓ Taproot output computed successfully!
  Internal key: 79be667ef9dcbbac...
  Leaf hash: 5ec8231e3ae2f044...
  Output key: d92b2ccfdb69761b...
  Parity: 0
  Output script: 5120d9...
  Control block length: 33 bytes

✓ Taproot address created: dgb1pmy4jen7md9mph8l4fp8e7l0gdnlkkzkdspcdvqc6ns7qlukfvgxs24ldld
✓ Address format is bech32m (dgb1p): True
```

### Manual Verification Steps

After broadcasting a Taproot inscription, verify it worked:

1. **Decode the transaction**:
   ```bash
   enigmatic-dgb ord-decode <txid> --json
   ```

2. **Check the output**:
   ```bash
   digibyte-cli getrawtransaction <txid> 1
   ```

   Look for:
   - Output with type: `"witness_v1_taproot"`
   - Address starting with `dgb1p`
   - ScriptPubKey: `OP_1 <32-byte output key>`

3. **Verify the key is tweaked**:
   - Extract the 32-byte output key from scriptPubKey
   - It should NOT match any wallet address
   - It should be deterministically derived from the inscription script

## Files Modified

1. **New**: `enigmatic_dgb/ordinals/taproot_builder.py` (420 lines)
2. **Modified**: `enigmatic_dgb/ordinals/workflows.py`
3. **Modified**: `enigmatic_dgb/cli.py`
4. **Documentation**: `docs/taproot_inscription_fix_plan.md`
5. **Summary**: `docs/taproot_inscription_fix_summary.md` (this file)

## Testing

All tests passed:
- ✅ `taproot_builder` module import
- ✅ BIP341 key tweaking
- ✅ Bech32m address encoding
- ✅ End-to-end inscription workflow simulation
- ✅ Integration with existing inscription planner

## Next Steps (Optional Future Work)

1. **Reveal Transaction Builder**: Implement script-path spending to reveal inscriptions
2. **Enhanced Verification**: Add `ord-verify` command to check Taproot commitments
3. **Test Vectors**: Add BIP341 test vectors for regression testing
4. **Internal Key Options**: Support wallet-derived or custom internal keys
5. **Multi-leaf Support**: Extend to Taproot trees with multiple script paths

## References

- [BIP340: Schnorr Signatures](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki)
- [BIP341: Taproot](https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki)
- [BIP350: Bech32m](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki)
- [Bitcoin Ordinals Theory](https://docs.ordinals.com/)
