"""LOCAL DEVELOPMENT ONLY: mint a session without Supabase so the app can run end-to-end on a laptop.
Mounted only when DEV_AUTH=true AND no SUPABASE_URL is configured. Never enable in staging/prod."""

from __future__ import annotations

import os
import time
import uuid
from typing import Literal

import jwt
from fastapi import APIRouter
from pydantic import BaseModel, Field
from rahbar_agent.db import tx

router = APIRouter(prefix="/dev")


def enabled() -> bool:
    return os.environ.get("DEV_AUTH") == "true" and not os.environ.get("SUPABASE_URL")


class DevLogin(BaseModel):
    email: str = Field(max_length=120)
    role: Literal["customer", "ops", "admin"] = "customer"


@router.post("/login")
def dev_login(body: DevLogin) -> dict[str, str]:
    with tx() as conn:
        row = conn.execute("select id from auth.users where email=%s", (body.email,)).fetchone()
        uid = str(row["id"]) if row else str(uuid.uuid4())
        if not row:
            conn.execute("insert into auth.users (id, email, raw_user_meta_data) values (%s,%s,'{}')", (uid, body.email))
        conn.execute("update profiles set role=%s where id=%s", (body.role, uid))
    token = jwt.encode({"sub": uid, "email": body.email, "aud": "authenticated", "aal": "aal2",
                        "exp": int(time.time()) + 8 * 3600}, os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")
    return {"access_token": token, "user_id": uid}
