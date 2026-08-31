from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from travel_agent.bootstrap.settings import Settings


class Argon2idHasher:
    def __init__(self, concurrency: int = 2) -> None:
        self._hasher = Argon2PasswordHasher(
            time_cost=3,
            memory_cost=64 * 1024,
            parallelism=1,
            hash_len=32,
            salt_len=16,
        )
        self._semaphore = asyncio.Semaphore(concurrency)

    async def hash(self, secret: str) -> str:
        async with self._semaphore:
            return await asyncio.to_thread(self._hasher.hash, secret)

    async def verify(self, encoded_hash: str, secret: str) -> bool:
        async with self._semaphore:
            try:
                return await asyncio.to_thread(self._hasher.verify, encoded_hash, secret)
            except (VerifyMismatchError, InvalidHashError):
                return False


class AesGcmTextProtector:
    _version = b"TP1"

    def __init__(self, key: bytes) -> None:
        self._cipher = AESGCM(key)

    def encrypt(self, value: str, *, context: str) -> bytes:
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher.encrypt(nonce, value.encode("utf-8"), context.encode("utf-8"))
        return self._version + nonce + ciphertext

    def decrypt(self, payload: bytes, *, context: str) -> str:
        if not payload.startswith(self._version):
            raise ValueError("unsupported protected text version")
        nonce = payload[3:15]
        ciphertext = payload[15:]
        plaintext = self._cipher.decrypt(nonce, ciphertext, context.encode("utf-8"))
        return plaintext.decode("utf-8")


class SecureTokenIssuer:
    def session_token(self) -> str:
        return secrets.token_urlsafe(32)

    def csrf_token(self) -> str:
        return secrets.token_urlsafe(32)

    def recovery_code(self) -> str:
        encoded = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        return "-".join(encoded[index : index + 4] for index in range(0, len(encoded), 4))

    def invite_code(self) -> str:
        encoded = base64.b32encode(secrets.token_bytes(15)).decode("ascii").rstrip("=")
        return "-".join(encoded[index : index + 4] for index in range(0, len(encoded), 4))


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def resolve_protection_key(settings: Settings) -> bytes:
    configured = settings.app_master_key
    if configured is not None:
        raw = configured.get_secret_value().encode("utf-8")
        if len(raw) >= 32:
            return hashlib.sha256(raw).digest()
    if settings.is_production:
        raise RuntimeError("APP_MASTER_KEY must contain at least 32 UTF-8 bytes")
    return _development_key(settings.data_root / "system-dev.key")


def _development_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.read_bytes()
    except FileNotFoundError:
        key = secrets.token_bytes(32)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return path.read_bytes()
        with os.fdopen(descriptor, "wb") as file:
            file.write(key)
        return key
