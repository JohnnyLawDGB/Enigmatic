"""Optional encryption helper utilities for Enigmatic payloads.

The helpers defined here provide a modern AEAD (AES-GCM by default, but the
patterns also support ChaCha20-Poly1305) + KDF construction that callers can use
to protect legitimate semantic metadata associated with Enigmatic messages.
They are not intended for misuse or hiding illicit traffic, and they reinforce
the guidance that Enigmatic's numeric telemetry is just a transport layer.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

logger = logging.getLogger(__name__)

_AESGCM_NONCE_SIZE = 12
_SCRYPT_SALT_SIZE = 16
_SCRYPT_KEY_LENGTH = 32
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


@dataclass
class EncryptedPayload:
    """Representation of serialized encrypted payload data."""

    algorithm: str
    kdf: str
    salt: str
    nonce: str
    ciphertext: str
    associated_data: str | None


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = Scrypt(
        salt=salt,
        length=_SCRYPT_KEY_LENGTH,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def derive_key_from_passphrase(passphrase: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a symmetric key using scrypt."""

    if salt is None:
        salt = os.urandom(_SCRYPT_SALT_SIZE)
    key = _derive_key(passphrase, salt)
    logger.debug("Derived symmetric key using scrypt")
    return key, salt


def encrypt_payload(
    payload: dict[str, Any],
    passphrase: str,
    associated_data: bytes | None = None,
) -> EncryptedPayload:
    """Encrypt the provided payload dictionary."""

    json_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    key, salt = derive_key_from_passphrase(passphrase)
    nonce = os.urandom(_AESGCM_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, json_payload, associated_data)

    return EncryptedPayload(
        algorithm="aes-gcm",
        kdf="scrypt",
        salt=base64.b64encode(salt).decode("ascii"),
        nonce=base64.b64encode(nonce).decode("ascii"),
        ciphertext=base64.b64encode(ciphertext).decode("ascii"),
        associated_data=(
            base64.b64encode(associated_data).decode("ascii") if associated_data else None
        ),
    )


def decrypt_payload(encrypted: EncryptedPayload, passphrase: str) -> dict[str, Any]:
    """Decrypt an :class:`EncryptedPayload` structure using the provided passphrase."""

    salt = base64.b64decode(encrypted.salt.encode("ascii"))
    nonce = base64.b64decode(encrypted.nonce.encode("ascii"))
    ciphertext = base64.b64decode(encrypted.ciphertext.encode("ascii"))
    associated_data = (
        base64.b64decode(encrypted.associated_data.encode("ascii"))
        if encrypted.associated_data
        else None
    )
    key, _ = derive_key_from_passphrase(passphrase, salt=salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)
    except InvalidTag as exc:  # pragma: no cover - depends on external input
        raise ValueError("Failed to decrypt payload; invalid passphrase or data") from exc
    return json.loads(plaintext.decode("utf-8"))
