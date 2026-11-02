"""HTTP-level tests: auth, roles, SSE chat, scam check, customer + ops flows, interrupt/resume."""

from __future__ import annotations

import json
import os
import time
import uuid

import jwt
import pytest

os.environ.setdefault("CHECKPOINTER", "memory")
os.environ.setdefault("LOCAL_STORAGE_DIR", "/tmp/rahbar-test-storage")  # noqa: S108

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(db, crawled):
    from rahbar_api.app import app

    return TestClient(app)


def token(uid: str, aal: str = "aal1") -> dict[str, str]:
    t = jwt.encode({"sub": uid, "aud": "authenticated", "exp": int(time.time()) + 600, "aal": aal, "role": "authenticated"},
                   os.environ["SUPABASE_JWT_SECRET"], algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


def mk_user(db, role="customer") -> str:
    uid = str(uuid.uuid4())
    db.execute("insert into auth.users (id, email) values (%s,%s)", (uid, f"{uid}@t.test"))
    if role != "customer":
        db.execute("update profiles set role=%s where id=%s", (role, uid))
    return uid


def sse_events(resp) -> list[tuple[str, dict]]:
    out = []
    for block in resp.text.split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_health_and_public(client):
    assert client.get("/health").json()["ok"]
    gb = client.get("/public/visa/GB").json()
    assert gb["facts"]["gov_fee"]["citation"]["url"].startswith("https://www.gov.uk")
    assert client.get("/public/visa/ZZ").status_code == 404
    assert len(client.get("/public/refund-policies").json()) == 6


def test_auth_required_and_bad_tokens(client):
    assert client.get("/cases").status_code == 401
    assert client.get("/cases", headers={"Authorization": "Bearer nope"}).status_code == 401
    bad = jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated"}, "wrong-secret-wrong-secret-wrong-secret!!", algorithm="HS256")
    assert client.get("/cases", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_ops_routes_need_role_and_2fa(client, db):
    cust, ops = mk_user(db), mk_user(db, "ops")
    assert client.get("/ops/cases", headers=token(cust)).status_code == 403
    assert client.get("/ops/cases", headers=token(ops, "aal1")).status_code == 403  # no 2FA
    assert client.get("/ops/cases", headers=token(ops, "aal2")).status_code == 200


def test_chat_sse_urdu(client):
    r = client.post("/chat", json={"message": "میرے والدین کے لیے برطانیہ کا وزٹ ویزا، انہیں کیا چاہیے؟", "locale": "ur",
                                   "session_id": "s-" + uuid.uuid4().hex})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = sse_events(r)
    kinds = [e for e, _ in ev]
    assert kinds[0] == "session" and kinds[-1] == "done"
    assert "progress" in kinds and "citation" in kinds and "token" in kinds and "card" in kinds
    text = "".join(d["text"] for e, d in ev if e == "token")
    assert "GBP 127" in text


def test_chat_threads_are_private(client, db):
    alice, bob = mk_user(db), mk_user(db)
    r = client.post("/chat", headers=token(alice), json={"message": "quote", "payload": {"action": "build_quote", "destination": "GB"}})
    case_id = next(d["case_id"] for e, d in sse_events(r) if e == "case")
    assert client.post("/chat", headers=token(bob), json={"message": "hi", "case_id": case_id}).status_code == 404
    assert client.get(f"/cases/{case_id}", headers=token(bob)).status_code == 404
    assert client.get(f"/cases/{case_id}", headers=token(alice)).json()["quote"]["lines"]


def test_public_scam_check(client):
    r = client.post("/scam-check", data={"text": "100% guaranteed Canada work visa, pay 15 lakh cash"})
    assert r.status_code == 200
    res = r.json()["result"]
    assert res["risk"] == "high" and {"guarantee", "work_visa", "cash_no_receipt"} <= {f["code"] for f in res["red_flags"]}
    r = client.post("/scam-check", data={"text": "x"}, files={"files": ("offer.txt", b"Licence 0987/KHI guaranteed visa", "text/plain")})
    assert any(f["code"] == "licence_not_valid" for f in r.json()["result"]["red_flags"])
    assert client.post("/scam-check", data={"text": ""}).status_code == 422


def test_full_visa_flow_over_http(client, db):
    user, ops = mk_user(db), mk_user(db, "ops")
    H, OPS = token(user), token(ops, "aal2")
    t = client.post("/travellers", headers=H, json={
        "full_name_as_passport": "Sara Ahmed", "date_of_birth": "1990-05-01", "passport_number": "AB1234567",
        "passport_expiry": "2032-01-01", "cnic": "35202-1234567-8",
        "profile": {"employment_status": "employed", "employer": "HBL", "monthly_income_minor": 40000000}}).json()
    assert t["passport_number_masked"] == "*****4567" and "passport_number_enc" not in t
    raw = db.fetch_one("select passport_number_enc from travellers where id=%s", (t["id"],))
    assert b"AB1234567" not in bytes(raw["passport_number_enc"])  # encrypted at rest

    r = client.post("/chat", headers=H, json={"message": "quote", "payload": {"action": "build_quote", "destination": "GB"}})
    cid = next(d["case_id"] for e, d in sse_events(r) if e == "case")
    client.post(f"/cases/{cid}/travellers", headers=H, json={"traveller_ids": [t["id"]]})
    bundle = client.get(f"/cases/{cid}", headers=H).json()
    assert client.post(f"/quotes/{bundle['quote']['quote_id']}/accept", headers=H).status_code == 200

    from datetime import date, timedelta
    pe = date.today() - timedelta(days=2)
    files = {
        "passport": "Full name: SARA AHMED\nDate of birth: 1990-05-01\nExpiry date: 2032-01-01\n",
        "cnic": "Full name: Sara Ahmed\nDate of birth: 1990-05-01\n",
        "photo": "Legible: yes\n",
        "employment_letter": "Full name: Sara Ahmed\nEmployer: HBL\n",
        "bank_statement": f"Full name: SARA AHMED\nPeriod start: {(pe - timedelta(days=185)).isoformat()}\nPeriod end: {pe.isoformat()}\n"
                          "Closing balance: 3000000\nCurrency: PKR\n",
    }
    for doc_type, body in files.items():
        r = client.post(f"/cases/{cid}/documents", headers=H, data={"doc_type": doc_type, "traveller_id": t["id"]},
                        files={"file": (f"{doc_type}.txt", body.encode(), "text/plain")})
        assert r.status_code == 200, r.text
    assert client.post(f"/cases/{cid}/documents", headers=H, data={"doc_type": "x"},
                       files={"file": ("a.exe", b"MZ", "application/x-msdownload")}).status_code == 415
    doc_id = client.get(f"/cases/{cid}", headers=H).json()["documents"][0]["id"]
    url = client.get(f"/documents/{doc_id}/url", headers=H).json()["url"]
    assert "sig=" in url and client.get(url.replace("http://localhost:8000", "")).status_code == 200
    assert client.get(f"/documents/{doc_id}/url", headers=token(mk_user(db))).status_code == 404

    job = client.post(f"/cases/{cid}/review", headers=H).json()
    from rahbar_worker.main import run_once
    assert run_once(["review_documents"]) == job["job_id"]
    assert client.get(f"/cases/{cid}", headers=H).json()["case"]["status"] == "documents_review"
    assert client.post(f"/cases/{cid}/pack", headers=H).status_code == 200

    # submit from chat -> LangGraph interrupt -> confirm card -> resume
    r = client.post("/chat", headers=H, json={"message": "please submit", "case_id": cid, "payload": {"action": "submit_pack"}})
    card = next(d for e, d in sse_events(r) if e == "card" and d.get("type") == "confirm_action")
    decl = [{"code": d["code"], "accepted": True} for d in card["declarations"]]
    r = client.post("/chat", headers=H, json={"message": "", "case_id": cid, "resume": {"confirmed": True, "declarations": decl}})
    assert "confirmed" in "".join(d["text"] for e, d in sse_events(r) if e == "token")

    ops_case = client.get(f"/ops/cases/{cid}", headers=OPS).json()
    assert any(not e["visible_to_user"] for e in ops_case["events"]) or ops_case["tasks"]
    ids = client.get(f"/ops/travellers/{t['id']}/sensitive", headers=OPS, params={"case_id": cid}).json()
    assert ids["passport_number"] == "AB1234567"
    assert db.fetch_one("select count(*) n from audit_log where action='reveal_ids' and entity_id=%s", (t["id"],))["n"] == 1
    action_id = card["action_id"]
    assert client.post(f"/ops/cases/{cid}/submission", headers=OPS,
                       json={"action_id": action_id, "reference": "GWF099887766", "portal": "gov.uk"}).status_code == 409
    assert client.post(f"/ops/actions/{action_id}/approve", headers=OPS, json={"approve": True}).status_code == 200
    assert client.post(f"/ops/cases/{cid}/submission", headers=OPS,
                       json={"action_id": action_id, "reference": "GWF099887766", "portal": "gov.uk"}).status_code == 200
    b = client.get(f"/cases/{cid}", headers=H).json()
    assert b["case"]["status"] == "submitted"
    assert any("GWF099887766" in e["message_en"] for e in b["events"])
    assert any(bk["provider_ref"] == "GWF099887766" for bk in b["bookings"])
    assert all(e["visible_to_user"] for e in b["events"])  # customer never sees internal notes
    r = client.post(f"/ops/cases/{cid}/status", headers=OPS, json={"status": "biometrics_scheduled", "when": "2027-01-03 10:00",
                                                                  "where": "VFS Lahore"})
    assert r.status_code == 200

    exp = client.get("/me/export", headers=H).json()
    assert exp["travellers"][0]["passport_number_masked"] == "*****4567" and "passport_number_enc" not in exp["travellers"][0]


def test_ops_sources_review(client, db):
    ops = mk_user(db, "ops")
    OPS = token(ops, "aal2")
    srcs = client.get("/ops/sources", headers=OPS).json()
    gb = next(s for s in srcs if s["url"] == "https://www.gov.uk/standard-visitor")
    d = client.get(f"/ops/sources/{gb['id']}", headers=OPS).json()
    rec = next(r for r in d["policy_records"] if r["field"] == "gov_fee" and r["status"] == "auto")
    assert client.post(f"/ops/policy/{rec['id']}", headers=OPS, json={"decision": "verify"}).json()["status"] == "verified"
    assert client.post("/ops/sources", headers=OPS, json={"url": "https://agent-scam.example.com/x", "title": "x",
                                                         "topic": "fees"}).status_code == 422


def test_checkpoint_tables_locked_down(db, database_url):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from rahbar_api.chat import lock_down_checkpoint_tables

    db.execute("create table if not exists public.checkpoints (id int)")
    db.execute("grant select on public.checkpoints to anon, authenticated")
    with ConnectionPool(database_url, kwargs={"row_factory": dict_row, "autocommit": True}, open=True) as p:
        lock_down_checkpoint_tables(p)
    row = db.fetch_one("select relrowsecurity, has_table_privilege('anon','public.checkpoints','select') anon_sel from pg_class where relname='checkpoints'")
    assert row["relrowsecurity"] and not row["anon_sel"]
