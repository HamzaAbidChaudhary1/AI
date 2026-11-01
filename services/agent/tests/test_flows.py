"""Phase 4 + 5 acceptance:
- J1 up to pack_ready with an issue detected in a deliberately mismatched bank statement,
  then -> submitted with the real reference number visible to the user.
- Umrah package quoted, paid (manual), booked with vouchers delivered in-app.
- Irreversible executors refuse to run without user confirmation + ops approval."""

import uuid
from datetime import date, timedelta

import pytest
from rahbar_agent import actions, cases, documents, fulfilment, ledger, packs, pricing, umrah
from rahbar_agent.actions import ActionNotApproved
from rahbar_agent.cases import TransitionError


def _ops(db):
    uid = str(uuid.uuid4())
    db.execute("insert into auth.users (id, email) values (%s,%s)", (uid, f"{uid}@ops.test"))
    db.execute("update profiles set role='ops' where id=%s", (uid,))
    return uid


def _traveller(conn, owner, name="ALI RAZA KHAN"):
    t = conn.execute("""insert into travellers (owner_id, full_name_as_passport, date_of_birth, passport_expiry)
                        values (%s,%s,'1985-03-02',%s) returning *""", (owner, name, date.today() + timedelta(days=2000))).fetchone()
    conn.execute("""insert into traveller_profiles (traveller_id, employment_status, employer, monthly_income_minor, travel_history)
                    values (%s,'employed','Engro Corp',35000000,'[{"country":"AE","year":2023}]')""", (t["id"],))
    return t


def _doc(conn, case_id, tid, doc_type, extracted):
    return conn.execute("""insert into documents (case_id, traveller_id, doc_type, storage_path, mime, extracted, uploaded_by)
                           values (%s,%s,%s,%s,'image/jpeg',%s,null) returning *""",
                        (case_id, tid, doc_type, f"test/{uuid.uuid4()}", __import__("psycopg").types.json.Jsonb(extracted))).fetchone()


def events(db, case_id, visible_only=True):
    return db.fetch_all("select * from case_events where case_id=%s and (visible_to_user or not %s) order by created_at",
                        (case_id, visible_only))


def test_visit_visa_flow_to_submitted(db, crawled, user):
    ops = _ops(db)
    with db.tx() as conn:
        t = _traveller(conn, user)
        case = cases.create_case(conn, user, "visit_visa", destination="GB", purpose="tourism",
                                 trip={"days": 10, "depart_date": "2027-01-10", "return_date": "2027-01-20"},
                                 traveller_ids=[str(t["id"])])
        cid = str(case["id"])
        from rahbar_agent import knowledge
        facts = knowledge.get_policy("GB", "visitor", ["gov_fee", "service_centre_fee"])
        q = pricing.build_quote(conn, cid, pricing.items_from_policy(facts, 1, "UK"))
    with db.tx() as conn, pytest.raises(pricing.QuoteError):
        pricing.accept_quote(conn, str(q["id"]), str(uuid.uuid4()))  # someone else can't accept
    with db.tx() as conn:
        pricing.accept_quote(conn, str(q["id"]), user)
        assert conn.execute("select status from cases where id=%s", (cid,)).fetchone()["status"] == "collecting_documents"
        checklist = documents.request_documents(conn, cid)
        assert {"passport", "cnic", "bank_statement"} <= {i["doc_type"] for i in checklist}
        tid = str(t["id"])
        exp = (date.today() + timedelta(days=2000)).isoformat()
        _doc(conn, cid, tid, "passport", {"full_name": "ALI RAZA KHAN", "date_of_birth": "1985-03-02", "expiry_date": exp, "legible": True})
        _doc(conn, cid, tid, "cnic", {"full_name": "Ali Raza Khan", "date_of_birth": "1985-03-02", "legible": True})
        _doc(conn, cid, tid, "photo", {"legible": True})
        _doc(conn, cid, tid, "employment_letter", {"full_name": "Ali Raza Khan", "employer": "Engro Corp", "legible": True})
        # deliberately mismatched bank statement + a large deposit just before the end date
        pe = date.today() - timedelta(days=3)
        bad = _doc(conn, cid, tid, "bank_statement", {
            "full_name": "ASIF MAHMOOD", "period_start": (pe - timedelta(days=185)).isoformat(), "period_end": pe.isoformat(),
            "closing_balance": 2_500_000, "currency": "PKR", "legible": True,
            "deposits": [{"date": (pe - timedelta(days=10)).isoformat(), "amount": 2_000_000, "description": "cash"}]})
        r = documents.run_review(conn, cid)
    codes = {f["code"] for f in r["findings"]}
    assert {"name_mismatch", "large_recent_deposit"} <= codes and r["blockers"] >= 2
    with db.tx() as conn:
        st = conn.execute("select status from cases where id=%s", (cid,)).fetchone()["status"]
        assert st == "collecting_documents"
        assert conn.execute("select review_status from documents where id=%s", (bad["id"],)).fetchone()["review_status"] == "issues"
        with pytest.raises(packs.PackError):
            packs.generate_application_pack(conn, cid)
    # user replaces the statement with their own, genuine one
    with db.tx() as conn:
        conn.execute("update documents set deleted_at=now() where id=%s", (bad["id"],))
        _doc(conn, cid, str(t["id"]), "bank_statement", {
            "full_name": "ALI RAZA KHAN", "period_start": (pe - timedelta(days=185)).isoformat(), "period_end": pe.isoformat(),
            "closing_balance": 2_500_000, "currency": "PKR", "deposits": [], "legible": True})
        r2 = documents.run_review(conn, cid)
        assert r2["blockers"] == 0
        pack = packs.generate_application_pack(conn, cid)
        assert conn.execute("select status from cases where id=%s", (cid,)).fetchone()["status"] == "pack_ready"
    c = pack["content"]
    form = {f["label"]: f["value"] for f in c["applicants"][0]["form_data"]}
    assert form["Full name (as in passport)"] == "ALI RAZA KHAN"
    assert "ops only" in form["Passport number"]  # passport number never in the pack
    assert "Ali" not in c["applicants"][0]["cover_letter_en"] or "guarantee" not in c["applicants"][0]["cover_letter_en"].lower()
    assert len(c["document_index"]) == 5

    with db.tx() as conn:
        a = packs.request_submission(conn, cid, user)
        aid = str(a["id"])
        # ops can't record a submission before the user confirms
        with pytest.raises(ActionNotApproved):
            packs.record_submission(conn, cid, aid, ops, "GWF012345678", "gov.uk")
    with db.tx() as conn, pytest.raises(ActionNotApproved):
        actions.confirm_by_user(conn, aid, user, [{"code": "truthful", "accepted": True}])  # missing declarations
    with db.tx() as conn:
        decl = [{"code": d["code"], "accepted": True} for d in a["payload"]["required_declarations"]]
        a2 = actions.confirm_by_user(conn, aid, user, decl)
        assert a2["status"] == "awaiting_ops"
        with pytest.raises(ActionNotApproved):  # still needs ops approval
            packs.record_submission(conn, cid, aid, ops, "GWF012345678", "gov.uk")
    with db.tx() as conn:
        actions.approve_by_ops(conn, aid, ops)
        packs.record_submission(conn, cid, aid, ops, "GWF012345678", "gov.uk")
        st = conn.execute("select status from cases where id=%s", (cid,)).fetchone()["status"]
    assert st == "submitted"
    evs = events(db, cid)
    assert any("GWF012345678" in e["message_en"] and "GWF012345678" in e["message_ur"] for e in evs)
    assert {e["actor_type"] for e in evs} >= {"ai", "user", "ops"}
    with db.tx() as conn, pytest.raises(TransitionError):
        cases.transition(conn, cid, "pack_ready", actor_type="ops")  # no going back from submitted


def test_umrah_flow_paid_and_booked(db, crawled, user):
    ops = _ops(db)
    opts = umrah.build_options(date(2026, 12, 10), 7, 5, 2)
    opt = opts[1]
    with db.tx() as conn:
        t1, t2 = _traveller(conn, user, "FATIMA BIBI"), _traveller(conn, user, "MUHAMMAD ASLAM")
        case = cases.create_case(conn, user, "umrah_package", destination="SA", purpose="umrah",
                                 traveller_ids=[str(t1["id"]), str(t2["id"])])
        cid = str(case["id"])
        q = pricing.build_quote(conn, cid, umrah.option_quote_items(opt), travellers=2)
        card = pricing.quote_card(q)
        assert [li["payee"] for li in card["lines"]][-1] == "rahbar"
        assert card["total_minor"] == opt["total_minor"] + 2 * 1_000_000
        pricing.accept_quote(conn, str(q["id"]), user)
        pay = ledger.create_payment_request(conn, str(q["id"]), user)
        assert pay["amount_minor"] == card["collect_minor"] and pay["instructions"]["payment_reference"]
        a = fulfilment.request_booking_confirmation(conn, cid, user)
        aid = str(a["id"])
    with db.tx() as conn:
        actions.confirm_by_user(conn, aid, user, [{"code": d["code"], "accepted": True} for d in a["payload"]["required_declarations"]])
        actions.approve_by_ops(conn, aid, ops)
        with pytest.raises(fulfilment.FulfilmentError):  # not paid yet
            fulfilment.record_partner_booking(conn, cid, aid, ops, partner_ref="P-1", items=[])
    with db.tx() as conn:
        ledger.attach_receipt(conn, str(pay["id"]), user, "receipts/r1.jpg")
        ledger.verify_payment(conn, str(pay["id"]), ops, "IBFT-778812")
        fulfilment.record_partner_booking(conn, cid, aid, ops, partner_ref="SUMR-2026-0042", items=[
            {"kind": "visa_application", "reference": "UMR-VISA-55102", "documents": [{"name": "Umrah e-visa (2 pilgrims)"}]},
            {"kind": "flight", "reference": "PNR7Q2X", "documents": [{"name": "E-tickets"}]},
            {"kind": "hotel", "reference": "MKH-88310", "documents": [{"name": "Makkah hotel voucher"}]},
            {"kind": "hotel", "reference": "MDN-11902", "documents": [{"name": "Madinah hotel voucher"}]},
            {"kind": "transport", "reference": "TRN-5521", "documents": [{"name": "Transport voucher"}]},
        ])
        st = conn.execute("select status from cases where id=%s", (cid,)).fetchone()["status"]
        refs = {b["provider_ref"] for b in conn.execute("select provider_ref from bookings where case_id=%s", (cid,))}
    assert st == "booked" and {"UMR-VISA-55102", "PNR7Q2X", "MKH-88310"} <= refs
    msgs = " ".join(e["message_en"] for e in events(db, cid))
    assert "Makkah hotel voucher" in msgs and "IBFT-778812" in msgs and "SUMR-2026-0042" in msgs


def test_refund_policy_math(db, crawled, user):
    ops = _ops(db)
    with db.tx() as conn:
        case = cases.create_case(conn, user, "visit_visa", destination="GB")
        cid = str(case["id"])
        q = pricing.build_quote(conn, cid, [], travellers=1)
        pricing.accept_quote(conn, str(q["id"]), user)  # -> collecting_documents
        rq = ledger.refund_quote(conn, cid)
        assert rq["percent"] == 100 and rq["refundable_minor"] == 1_500_000
        conn.execute("update cases set status='pack_ready' where id=%s", (cid,))
        assert ledger.refund_quote(conn, cid)["percent"] == 50
        a = actions.request_action(conn, cid, "refund", "Refund 50% of service fee", "سروس فیس کا 50٪ واپس")
    with db.tx() as conn, pytest.raises(ActionNotApproved):
        ledger.issue_refund(conn, cid, str(a["id"]), ops, 750_000, "customer cancelled")
    with db.tx() as conn:
        actions.confirm_by_user(conn, str(a["id"]), user, [])
        actions.approve_by_ops(conn, str(a["id"]), ops)
        ledger.issue_refund(conn, cid, str(a["id"]), ops, 750_000, "customer cancelled")
        assert conn.execute("select status from cases where id=%s", (cid,)).fetchone()["status"] == "refunded"


def test_irreversible_tools_need_confirmation_record(db, crawled, user):
    ops = _ops(db)
    with db.tx() as conn:
        case = cases.create_case(conn, user, "flight")
        cid = str(case["id"])
        for kind, fn in [("issue_ticket", fulfilment.issue_ticket), ("book_hotel", fulfilment.book_hotel)]:
            with pytest.raises(ActionNotApproved):
                fn(conn, cid, None, ops)
            a = actions.request_action(conn, cid, kind, "x", "x")
            with pytest.raises(ActionNotApproved):
                fn(conn, cid, str(a["id"]), ops)


def test_quote_expiry(db, crawled, user):
    from datetime import UTC, datetime
    with db.tx() as conn:
        case = cases.create_case(conn, user, "visit_visa", destination="TR")
        q = pricing.build_quote(conn, str(case["id"]), [], valid_until=datetime.now(UTC) - timedelta(minutes=1))
        assert pricing.expire_quotes(conn) >= 1
        with pytest.raises(pricing.QuoteError):
            pricing.accept_quote(conn, str(q["id"]), user)


def test_service_fee_cannot_be_injected():
    with pytest.raises(ValueError):
        pricing.QuoteItemIn(kind="service_fee", description_en="x", description_ur="x", unit_amount_minor=1,
                            currency="PKR", payee="rahbar")


def test_ops_refund_four_eyes(db, crawled, user):
    ops1, ops2 = _ops(db), _ops(db)
    with db.tx() as conn:
        case = cases.create_case(conn, user, "visit_visa", destination="GB")
        cid = str(case["id"])
        a = actions.request_ops_action(conn, cid, "refund", "Refund", "واپسی", {"amount_minor": 100}, ops1)
        with pytest.raises(ActionNotApproved):
            actions.approve_by_ops(conn, str(a["id"]), ops1)
        actions.approve_by_ops(conn, str(a["id"]), ops2)
        ledger.issue_refund(conn, cid, str(a["id"]), ops2, 100, "duplicate payment")
        internal = conn.execute("select count(*) n from case_events where case_id=%s and not visible_to_user", (cid,)).fetchone()["n"]
        assert internal >= 1
