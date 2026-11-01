"""Private document storage (docs/SECURITY.md). Supabase Storage in deployed envs; a local folder in dev.
Access only via short-lived signed URLs issued after an ownership/role check."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from pathlib import Path
from typing import Protocol

import httpx

SIGNED_URL_SECONDS = 300


class Storage(Protocol):
    def put(self, bucket: str, path: str, data: bytes, mime: str) -> None: ...
    def get(self, bucket: str, path: str) -> bytes: ...
    def delete(self, bucket: str, path: str) -> None: ...
    def signed_url(self, bucket: str, path: str, seconds: int = SIGNED_URL_SECONDS) -> str: ...


class SupabaseStorage:
    def __init__(self, url: str, service_key: str) -> None:
        self.url, self.key = url.rstrip("/"), service_key

    def _h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}", "apikey": self.key}

    def put(self, bucket: str, path: str, data: bytes, mime: str) -> None:
        r = httpx.post(f"{self.url}/storage/v1/object/{bucket}/{path}", content=data,
                       headers={**self._h(), "Content-Type": mime, "x-upsert": "false"}, timeout=60)
        r.raise_for_status()

    def get(self, bucket: str, path: str) -> bytes:
        r = httpx.get(f"{self.url}/storage/v1/object/authenticated/{bucket}/{path}", headers=self._h(), timeout=60)
        r.raise_for_status()
        return r.content

    def delete(self, bucket: str, path: str) -> None:
        httpx.request("DELETE", f"{self.url}/storage/v1/object/{bucket}", headers=self._h(),
                      json={"prefixes": [path]}, timeout=30).raise_for_status()

    def signed_url(self, bucket: str, path: str, seconds: int = SIGNED_URL_SECONDS) -> str:
        r = httpx.post(f"{self.url}/storage/v1/object/sign/{bucket}/{path}", headers=self._h(),
                       json={"expiresIn": min(seconds, SIGNED_URL_SECONDS)}, timeout=30)
        r.raise_for_status()
        return f"{self.url}/storage/v1{r.json()['signedURL']}"


class LocalStorage:
    def __init__(self, root: str, secret: str, public_base: str) -> None:
        self.root, self.secret, self.base = Path(root), secret.encode(), public_base.rstrip("/")

    def _p(self, bucket: str, path: str) -> Path:
        p = (self.root / bucket / path).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("bad path")
        return p

    def put(self, bucket: str, path: str, data: bytes, mime: str) -> None:
        p = self._p(bucket, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, bucket: str, path: str) -> bytes:
        return self._p(bucket, path).read_bytes()

    def delete(self, bucket: str, path: str) -> None:
        self._p(bucket, path).unlink(missing_ok=True)

    def sign(self, bucket: str, path: str, exp: int) -> str:
        return hmac.new(self.secret, f"{bucket}/{path}:{exp}".encode(), hashlib.sha256).hexdigest()

    def signed_url(self, bucket: str, path: str, seconds: int = SIGNED_URL_SECONDS) -> str:
        exp = int(time.time()) + min(seconds, SIGNED_URL_SECONDS)
        return f"{self.base}/files/{bucket}/{path}?exp={exp}&sig={self.sign(bucket, path, exp)}"

    def verify(self, bucket: str, path: str, exp: int, sig: str) -> bool:
        return exp >= time.time() and hmac.compare_digest(sig, self.sign(bucket, path, exp))


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            _storage = SupabaseStorage(url, key)
        else:
            _storage = LocalStorage(os.environ.get("LOCAL_STORAGE_DIR", ".local-storage"),
                                    os.environ.get("SUPABASE_JWT_SECRET", "dev-secret"),
                                    os.environ.get("API_PUBLIC_URL", "http://localhost:8000"))
    return _storage
