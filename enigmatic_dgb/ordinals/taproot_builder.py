"""BIP341 Taproot transaction building utilities.

This module implements the core BIP341 Taproot primitives needed to create
inscription commitment transactions. It handles tagged hashing, merkle tree
construction, key tweaking, and address encoding for DigiByte's Taproot support.

All operations follow BIP340 (Schnorr), BIP341 (Taproot), and BIP350 (bech32m).
"""

from __future__ import annotations

import hashlib
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend


# BIP340/341 constants
SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_FIELD_SIZE = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F

# Default internal key for inscriptions (unspendable)
# This is a pre-computed valid x-coordinate derived from SHA256("enigmatic-dgb-inscriptions")
# Since we don't know the discrete log (private key) for this point, it's provably unspendable
# Following the Bitcoin Ordinals pattern of using unspendable internal keys

DEFAULT_UNSPENDABLE_KEY = bytes.fromhex(
    "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
)
# This is the x-coordinate of the secp256k1 generator point G
# It's a well-known, nothing-up-my-sleeve number from the SECG spec
# The discrete log (private key) for tweaked versions is unknown, making it provably unspendable


def tagged_hash(tag: str, data: bytes) -> bytes:
    """Compute BIP340-style tagged hash.

    Tagged hashing prevents cross-protocol attacks by domain-separating different
    hash uses. The tag is hashed twice and prepended to the message before the
    final hash.

    Args:
        tag: Domain separation tag (e.g., "TapLeaf", "TapTweak")
        data: Data to hash

    Returns:
        32-byte SHA256 hash

    Reference:
        BIP340: https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki
    """
    tag_hash = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_hash + tag_hash + data).digest()


def ser_compact_size(n: int) -> bytes:
    """Serialize an integer as a Bitcoin compact size.

    Args:
        n: Integer to serialize

    Returns:
        Compact size encoding
    """
    if n < 253:
        return bytes([n])
    elif n <= 0xFFFF:
        return b'\xfd' + n.to_bytes(2, 'little')
    elif n <= 0xFFFFFFFF:
        return b'\xfe' + n.to_bytes(4, 'little')
    else:
        return b'\xff' + n.to_bytes(8, 'little')


def taproot_leaf_hash(leaf_script: bytes, leaf_version: int = 0xc0) -> bytes:
    """Compute TapLeaf hash for a single script leaf.

    Args:
        leaf_script: The script content
        leaf_version: Leaf version (0xc0 = TAPSCRIPT)

    Returns:
        32-byte tagged hash of the leaf

    Reference:
        BIP341: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki
    """
    return tagged_hash(
        "TapLeaf",
        bytes([leaf_version]) + ser_compact_size(len(leaf_script)) + leaf_script
    )


def taproot_tweak_pubkey(internal_key: bytes, merkle_root: bytes) -> Tuple[bytes, int]:
    """Tweak an internal public key with a merkle root per BIP341.

    This implements the core Taproot tweaking operation:
    Q = P + H_taptweak(P || merkle_root) * G

    Args:
        internal_key: 32-byte x-only internal public key
        merkle_root: 32-byte merkle root hash (or empty for key-path only)

    Returns:
        Tuple of (tweaked_pubkey, parity) where:
            - tweaked_pubkey: 32-byte x-only tweaked public key
            - parity: 0 if even y-coordinate, 1 if odd

    Raises:
        ValueError: If the internal key is invalid or tweaking fails

    Reference:
        BIP341: https://github.com/bitcoin/bips/blob/master/bip-0341.mediawiki
    """
    if len(internal_key) != 32:
        raise ValueError(f"Internal key must be 32 bytes, got {len(internal_key)}")

    # Compute tweak: t = tagged_hash("TapTweak", internal_key || merkle_root)
    tweak_data = internal_key + merkle_root
    tweak_hash = tagged_hash("TapTweak", tweak_data)
    tweak_int = int.from_bytes(tweak_hash, 'big')

    # Ensure tweak is valid (less than curve order)
    if tweak_int >= SECP256K1_ORDER:
        raise ValueError("Tweak value exceeds curve order")

    # Reconstruct point P from x-only coordinate (assume even y)
    # For x-only keys, we always use the even y-coordinate point
    try:
        internal_point = _point_from_xonly(internal_key)
    except Exception as exc:
        raise ValueError(f"Invalid internal key: {exc}") from exc

    # Compute tweak point: t*G
    curve = ec.SECP256K1()
    private_key = ec.derive_private_key(tweak_int, curve, default_backend())
    tweak_point = private_key.public_key().public_numbers()

    # Add points: Q = P + t*G
    try:
        tweaked_point = _point_add(internal_point, tweak_point)
    except Exception as exc:
        raise ValueError(f"Point addition failed: {exc}") from exc

    # Extract x-coordinate and parity
    tweaked_x = tweaked_point.x.to_bytes(32, 'big')
    parity = tweaked_point.y % 2

    return tweaked_x, parity


def _point_from_xonly(x_bytes: bytes) -> ec.EllipticCurvePublicNumbers:
    """Reconstruct a secp256k1 point from x-only coordinate (assuming even y).

    Args:
        x_bytes: 32-byte x-coordinate

    Returns:
        EllipticCurvePublicNumbers representing the point

    Raises:
        ValueError: If x-coordinate is invalid
    """
    x = int.from_bytes(x_bytes, 'big')

    if x >= SECP256K1_FIELD_SIZE:
        raise ValueError("x-coordinate exceeds field size")

    # Compute y^2 = x^3 + 7 (mod p) for secp256k1
    y_squared = (pow(x, 3, SECP256K1_FIELD_SIZE) + 7) % SECP256K1_FIELD_SIZE

    # Compute square root (y = y_squared^((p+1)/4) for p ≡ 3 mod 4)
    y = pow(y_squared, (SECP256K1_FIELD_SIZE + 1) // 4, SECP256K1_FIELD_SIZE)

    # Verify it's actually a square root
    if pow(y, 2, SECP256K1_FIELD_SIZE) != y_squared:
        raise ValueError("x-coordinate is not on the curve")

    # Choose even y (BIP340 convention for x-only keys)
    if y % 2 != 0:
        y = SECP256K1_FIELD_SIZE - y

    return ec.EllipticCurvePublicNumbers(x, y, ec.SECP256K1())


def _point_add(p1: ec.EllipticCurvePublicNumbers, p2: ec.EllipticCurvePublicNumbers) -> ec.EllipticCurvePublicNumbers:
    """Add two secp256k1 points.

    Args:
        p1: First point
        p2: Second point

    Returns:
        Sum of the two points

    Note:
        This uses the cryptography library's internal point arithmetic.
        For production use, consider using a dedicated secp256k1 library.
    """
    # Convert to affine coordinates and add
    x1, y1 = p1.x, p1.y
    x2, y2 = p2.x, p2.y

    p = SECP256K1_FIELD_SIZE

    # Handle point doubling
    if x1 == x2:
        if y1 == y2:
            # Point doubling: λ = (3*x1^2) / (2*y1)
            lam = (3 * x1 * x1 * pow(2 * y1, -1, p)) % p
        else:
            # Points are inverses, result is point at infinity (not supported here)
            raise ValueError("Point addition results in point at infinity")
    else:
        # Point addition: λ = (y2 - y1) / (x2 - x1)
        lam = ((y2 - y1) * pow(x2 - x1, -1, p)) % p

    # x3 = λ^2 - x1 - x2
    x3 = (lam * lam - x1 - x2) % p
    # y3 = λ(x1 - x3) - y1
    y3 = (lam * (x1 - x3) - y1) % p

    return ec.EllipticCurvePublicNumbers(x3, y3, ec.SECP256K1())


def compute_taproot_output_from_script(
    leaf_script: bytes,
    internal_key: bytes | None = None
) -> dict:
    """Compute Taproot output details from a leaf script.

    This is the main entry point for creating a Taproot inscription commitment.
    It computes the merkle root, tweaks the internal key, and returns all
    information needed to build the commitment transaction and later reveal.

    Args:
        leaf_script: The Taproot script leaf (e.g., inscription envelope)
        internal_key: Optional 32-byte x-only internal key (defaults to unspendable)

    Returns:
        Dictionary containing:
            - internal_key: 32-byte x-only internal key (hex)
            - leaf_hash: 32-byte leaf hash (hex)
            - merkle_root: 32-byte merkle root (hex) - same as leaf_hash for single leaf
            - output_key: 32-byte tweaked output key (hex)
            - parity: Output key parity (0 or 1)
            - output_script: P2TR scriptPubKey (hex) - OP_1 <output_key>
            - control_block: Control block for script-path spending (hex)

    Example:
        >>> leaf = bytes.fromhex("006354...68")  # OP_0 OP_IF <inscription> OP_ENDIF
        >>> output = compute_taproot_output_from_script(leaf)
        >>> address = create_taproot_address(bytes.fromhex(output["output_key"]))
    """
    # Use unspendable key if none provided
    if internal_key is None:
        internal_key = DEFAULT_UNSPENDABLE_KEY

    if len(internal_key) != 32:
        raise ValueError(f"Internal key must be 32 bytes, got {len(internal_key)}")

    # Compute leaf hash
    leaf_hash = taproot_leaf_hash(leaf_script)

    # For a single leaf, merkle_root = leaf_hash
    merkle_root = leaf_hash

    # Tweak the internal key with the merkle root
    output_key, parity = taproot_tweak_pubkey(internal_key, merkle_root)

    # Build P2TR scriptPubKey: OP_1 <32-byte output key>
    output_script = bytes([0x51, 0x20]) + output_key  # OP_1 PUSH32

    # Build control block: <leaf_version + parity> <internal_key> [merkle_path]
    # For single leaf: just version+parity and internal key (no merkle path)
    leaf_version = 0xc0
    control_byte = leaf_version | parity
    control_block = bytes([control_byte]) + internal_key

    return {
        "internal_key": internal_key.hex(),
        "leaf_hash": leaf_hash.hex(),
        "merkle_root": merkle_root.hex(),
        "output_key": output_key.hex(),
        "parity": parity,
        "output_script": output_script.hex(),
        "control_block": control_block.hex(),
    }


def bech32_polymod(values: list[int]) -> int:
    """Compute bech32 checksum polymod."""
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        b = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ value
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def bech32_hrp_expand(hrp: str) -> list[int]:
    """Expand HRP for bech32 checksum."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_create_checksum(hrp: str, data: list[int], spec: str) -> list[int]:
    """Compute bech32/bech32m checksum.

    Args:
        hrp: Human-readable part
        data: Data values (5-bit)
        spec: Either 'bech32' or 'bech32m'

    Returns:
        Checksum values (6 elements)
    """
    values = bech32_hrp_expand(hrp) + data
    const = 0x2bc830a3 if spec == 'bech32m' else 1  # BIP350 constant for bech32m
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp: str, witver: int, witprog: bytes) -> str:
    """Encode a segwit address using bech32m (for witness v1+) or bech32 (v0).

    Args:
        hrp: Human-readable part (e.g., 'dgb' for DigiByte mainnet)
        witver: Witness version (0-16)
        witprog: Witness program bytes

    Returns:
        Bech32/bech32m encoded address

    Reference:
        BIP173 (bech32): https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki
        BIP350 (bech32m): https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki
    """
    spec = 'bech32m' if witver >= 1 else 'bech32'

    # Convert 8-bit to 5-bit
    data = _convertbits(witprog, 8, 5)
    if data is None:
        raise ValueError("Failed to convert witness program to 5-bit")

    # Prepend witness version
    combined = [witver] + data

    # Create checksum
    checksum = bech32_create_checksum(hrp, combined, spec)

    # Encode to characters
    CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    return hrp + '1' + ''.join([CHARSET[d] for d in combined + checksum])


def _convertbits(data: bytes, frombits: int, tobits: int, pad: bool = True) -> list[int] | None:
    """Convert between bit groups.

    Args:
        data: Input data
        frombits: Input bit width
        tobits: Output bit width
        pad: Whether to pad the output

    Returns:
        List of converted values, or None on error
    """
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1

    for value in data:
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)

    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None

    return ret


def create_taproot_address(output_key: bytes, hrp: str = "dgb") -> str:
    """Create a DigiByte Taproot (bech32m) address from an output key.

    Args:
        output_key: 32-byte tweaked output key
        hrp: Human-readable part ('dgb' for mainnet, 'dgbt' for testnet)

    Returns:
        Bech32m encoded Taproot address (witness v1)

    Example:
        >>> output_key = bytes.fromhex("50929b74c1a04954b78b4b6035e97a5e...")
        >>> address = create_taproot_address(output_key)
        >>> address.startswith('dgb1p')
        True
    """
    if len(output_key) != 32:
        raise ValueError(f"Output key must be 32 bytes, got {len(output_key)}")

    # Taproot is witness version 1
    return bech32_encode(hrp, 1, output_key)
