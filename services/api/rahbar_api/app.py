"""FastAPI app: REST + SSE. Run: uvicorn rahbar_api.app:app"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from rahbar_agent import knowledge, llm
from rahbar_agent.db import fetch_all, fetch_one
from rahbar_agent.i18n import VISA_TYPES, country_name
from rahbar_agent.storage import LocalStorage, get_storage

from . import chat, dev_auth, routes_customer, routes_ops
from .security import sentry_before_send

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
if os.environ.get("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], before_send=sentry_before_send, send_default_pii=False,
                    traces_sample_rate=float(os.environ.get("SENTRY_TRACES", "0.05")))

app = FastAPI(title="Rahbar API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(chat.router)
app.include_router(routes_customer.router)
app.include_router(routes_ops.router)
llm.set_usage_hook(chat.record_usage)
if dev_auth.enabled():
    logging.getLogger(__name__).warning("DEV_AUTH is enabled — local development only")
    app.include_router(dev_auth.router)


@app.get("/health")
def health() -> dict[str, Any]:
    db_ok = bool(fetch_one("select 1 as ok"))
    s = llm.get_settings()
    return {"ok": db_ok, "llm": "anthropic" if s.use_anthropic else "offline",
            "models": {"fast": s.model_fast, "standard": s.model_standard, "deep": s.model_deep}}


@app.get("/public/visa/{country}")
def visa_page(country: str) -> dict[str, Any]:
    """Destination page data: requirements and fees, each with source + last verified."""
    c = country.upper()
    if c not in VISA_TYPES:
        raise HTTPException(404, "not covered yet")
    facts = knowledge.get_policy(c, VISA_TYPES[c])
    return {"country": c, "name_en": country_name(c), "name_ur": country_name(c, "ur"), "visa_type": VISA_TYPES[c],
            "facts": {k: v.model_dump() for k, v in facts.items()}}


@app.get("/public/destinations")
def destinations() -> list[dict[str, str]]:
    return [{"code": c, "name_en": country_name(c), "name_ur": country_name(c, "ur"), "visa_type": v} for c, v in VISA_TYPES.items()]


@app.get("/public/refund-policies")
def refund_policies() -> list[dict[str, Any]]:
    return fetch_all("select service_type, rules, text_en, text_ur from refund_policies order by service_type")


@app.get("/public/service-fees")
def service_fees() -> list[dict[str, Any]]:
    return fetch_all("""select service_type, destination_country, amount_minor, currency, per, description_en, description_ur
                        from service_fees where active order by service_type""")


@app.get("/files/{bucket}/{path:path}")
def local_file(bucket: str, path: str, exp: int, sig: str) -> Response:
    """Dev-only signed file access (LocalStorage). Supabase serves signed URLs directly in deployed envs."""
    st = get_storage()
    if not isinstance(st, LocalStorage) or not st.verify(bucket, path, exp, sig):
        raise HTTPException(403, "link expired")
    return Response(st.get(bucket, path), headers={"Cache-Control": "no-store"})


@app.post("/webhooks/payments/{provider}")
def payment_webhook(provider: str) -> dict[str, str]:
    # Phase 6: verify gateway signature, then update payments idempotently by provider_ref.
    raise HTTPException(501, f"payment gateway '{provider}' not configured; MVP uses manual bank transfer")
