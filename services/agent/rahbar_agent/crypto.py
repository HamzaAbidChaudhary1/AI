"""App-level AES-GCM encryption for passport numbers and CNICs (docs/SECURITY.md).

Format: b"k1:" + 12-byte nonce + ciphertext. The key-id prefix makes rotation possible:
DOCS_ENCRYPTION_KEY may hold several keys "k2:<b64>,k1:<b64>"; the first one encrypts.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings


def _keys(spec: str | None = None) -> list[tuple[str, bytes]]:
    spec = spec if spec is not None else get_settings().docs_encryption_key
    if not spec:
        raise RuntimeError("DOCS_ENCRYPTION_KEY is not set")
    out: list[tuple[str, bytes]] = []
    for part in spec.split(","):
        kid, _, b64 = part.strip().partition(":")
        if not b64:
            kid, b64 = "k1", kid
        try:
            key = base64.b64decode(b64, validate=True)
        except ValueError:
            key = b""
        if len(key) != 32:
            # not a raw 32-byte base64 key: derive one (input must itself be a long random secret)
            if len(b64) < 32:
                raise RuntimeError("DOCS_ENCRYPTION_KEY is too short")
            key = hashlib.sha256(b64.encode()).digest()
        out.append((kid, key))
    return out


def encrypt(plaintext: str, spec: str | None = None) -> bytes:
    kid, key = _keys(spec)[0]
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), kid.encode())
    return kid.encode() + b":" + nonce + ct


def decrypt(blob: bytes, spec: str | None = None) -> str:
    kid_b, _, rest = bytes(blob).partition(b":")
    kid = kid_b.decode()
    for k, key in _keys(spec):
        if k == kid:
            return AESGCM(key).decrypt(rest[:12], rest[12:], kid.encode()).decode()
    raise RuntimeError(f"unknown key id {kid}")


def mask(value: str, keep: int = 4) -> str:
    """For display: 'AB1234567' -> '*****4567'."""
    return "*" * max(0, len(value) - keep) + value[-keep:]


def new_key_b64() -> str:
    return base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
