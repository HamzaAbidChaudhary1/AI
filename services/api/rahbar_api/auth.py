"""Supabase JWT verification. Supports asymmetric keys (JWKS) and the legacy HS256 secret."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request
from rahbar_agent.db import fetch_one


@dataclass
class User:
    id: str
    role: str
    locale: str
    email: str | None = None


@lru_cache
def _jwks() -> jwt.PyJWKClient | None:
    url = os.environ.get("SUPABASE_URL")
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json") if url else None


def decode_token(token: str) -> dict:
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
    except jwt.PyJWTError as e:
        raise HTTPException(401, "invalid token") from e
    try:
        if alg == "HS256":
            secret = os.environ.get("SUPABASE_JWT_SECRET")
            if not secret:
                raise HTTPException(401, "auth not configured")
            return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
        client = _jwks()
        if client is None or alg not in ("ES256", "RS256"):
            raise HTTPException(401, "unsupported token")
        key = client.get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=[alg], audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(401, "invalid token") from e


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:] if h.lower().startswith("bearer ") else None


def optional_user(request: Request) -> User | None:
    token = _bearer(request)
    if not token:
        return None
    claims = decode_token(token)
    prof = fetch_one("select role, preferred_locale from profiles where id=%s", (claims["sub"],))
    if prof is None:
        raise HTTPException(401, "no profile")
    if prof["role"] in ("ops", "admin", "partner") and os.environ.get("REQUIRE_STAFF_MFA", "true") == "true":
        if claims.get("aal") != "aal2":
            prof = {**prof, "role": "customer_mfa_required"}
    return User(id=claims["sub"], role=prof["role"], locale=prof["preferred_locale"], email=claims.get("email"))


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "sign in required")
    return user


def staff_user(user: User = Depends(current_user)) -> User:
    if user.role == "customer_mfa_required":
        raise HTTPException(403, "two-factor authentication required for staff accounts")
    if user.role not in ("ops", "admin"):
        raise HTTPException(403, "ops only")
    return user


def admin_user(user: User = Depends(staff_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "admin only")
    return user
