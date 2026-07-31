import json
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

# Dev-only default so the stack boots out of the box — generated once via
# Fernet.generate_key(), NOT a secret worth protecting. Any real deployment
# must set CREDENTIAL_ENCRYPTION_KEY to its own key (Fernet.generate_key())
# or every stored credential becomes unrecoverable garbage on rotation.
_DEV_DEFAULT_KEY = b"3JqU9pS8pXk2vN7hM1dY4bW6fL0cR5tA8gZ2xE9jK3o="

_configured_key = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")

if not _configured_key:
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY must be set in production — refusing to start "
            "with the dev-only default (every stored credential would be decryptable "
            "by anyone with source access)."
        )
    logging.getLogger("aiops").warning(
        "CREDENTIAL_ENCRYPTION_KEY is unset — using a dev-only default key committed "
        "in source. Every stored credential is decryptable by anyone with repo access. "
        "Set a real key before any real deployment."
    )

_key = _configured_key.encode() or _DEV_DEFAULT_KEY
_fernet = Fernet(_key)


def encrypt_fields(fields: dict) -> bytes:
    """Encrypts a dict of secret fields (e.g. {"api_key": "..."}) as one opaque blob."""
    return _fernet.encrypt(json.dumps(fields).encode())


def decrypt_fields(ciphertext: bytes) -> dict:
    try:
        return json.loads(_fernet.decrypt(bytes(ciphertext)).decode())
    except InvalidToken:
        raise ValueError("Credential could not be decrypted — encryption key may have changed")


def masked_preview(fields: dict) -> str:
    """Never echoes a real secret value — just enough to let a human recognize
    which credential is configured (e.g. 'sk-...ab12')."""
    if not fields:
        return ""
    first_value = str(next(iter(fields.values())))
    if len(first_value) <= 4:
        return "****"
    return f"{first_value[:3]}...{first_value[-4:]}"
