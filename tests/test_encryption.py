"""Unit tests for the optional encryption helper layer."""

from __future__ import annotations

from datetime import datetime

import pytest

from enigmatic_dgb.encryption import (
    decrypt_payload,
    derive_key_from_passphrase,
    encrypt_payload,
)
from enigmatic_dgb.model import (
    EnigmaticMessage,
    message_decrypt_payload,
    message_with_encrypted_payload,
)


def test_derive_key_deterministic_with_explicit_salt() -> None:
    salt = b"scrypt-test-salt"
    key_one, salt_one = derive_key_from_passphrase("hunter2", salt=salt)
    key_two, salt_two = derive_key_from_passphrase("hunter2", salt=salt)

    assert key_one == key_two
    assert salt_one == salt_two


def test_derive_key_changes_with_random_salt() -> None:
    key_one, salt_one = derive_key_from_passphrase("hunter2")
    key_two, salt_two = derive_key_from_passphrase("hunter2")

    assert salt_one != salt_two
    assert key_one != key_two


def test_encrypt_and_decrypt_payload_round_trip() -> None:
    payload = {"alpha": 1, "beta": "two"}
    encrypted = encrypt_payload(payload, passphrase="shared-secret")
    decrypted = decrypt_payload(encrypted, passphrase="shared-secret")

    assert decrypted == payload


def test_decrypt_payload_rejects_wrong_passphrase() -> None:
    payload = {"example": True}
    encrypted = encrypt_payload(payload, passphrase="shared-secret")

    with pytest.raises(ValueError):
        decrypt_payload(encrypted, passphrase="not-the-same")


def test_message_helpers_encrypt_and_decrypt() -> None:
    message = EnigmaticMessage(
        id="msg-1",
        timestamp=datetime.utcnow(),
        channel="ops",
        intent="presence",
        payload={"note": "classified"},
    )

    encrypted_payload = encrypt_payload(message.payload, passphrase="passphrase")
    encrypted_message = message_with_encrypted_payload(message, encrypted_payload)

    assert encrypted_message.encrypted is True
    assert "encrypted" in encrypted_message.payload

    decrypted_payload = message_decrypt_payload(encrypted_message, passphrase="passphrase")
    assert decrypted_payload == {"note": "classified"}


def test_message_decrypt_payload_plaintext_passthrough() -> None:
    payload = {"flag": False}
    message = EnigmaticMessage(
        id="plain",
        timestamp=datetime.utcnow(),
        channel="ops",
        intent="identity",
        payload=payload,
    )

    assert message_decrypt_payload(message, passphrase="ignored") == payload
