"""RLS policy tests (CLAUDE.md: write tests for RLS policies)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import psycopg
import pytest
from psycopg.rows import dict_row


@pytest.fixture(scope="module")
def conn(database_url):
    with psycopg.connect(database_url, row_factory=dict_row, autocommit=True) as c:
        yield c


def _user(conn, role="customer", partner_id=None) -> str:
    uid = str(uuid.uuid4())
    conn.execute("insert into auth.users (id, email) values (%s, %s)", (uid, f"{uid}@t.test"))
    conn.execute("update public.profiles set role=%s, partner_id=%s where id=%s", (role, partner_id, uid))
    return uid


@contextmanager
def as_user(conn, uid: str | None):
    with conn.transaction(force_rollback=True):
        if uid is None:
            conn.execute("set local role anon")
        else:
            conn.execute("set local role authenticated")
            conn.execute("select set_config('request.jwt.claim.sub', %s, true)", (uid,))
        yield conn


@pytest.fixture(scope="module")
def world(conn):
    partner = conn.execute(
        "insert into partners (name, kind) values ('P', 'umrah_operator') returning id").fetchone()["id"]
    alice, bob = _user(conn), _user(conn)
    ops = _user(conn, "ops")
    puser = _user(conn, "partner", partner)
    case_a = conn.execute(
        "insert into cases (owner_id, service_type, partner_id) values (%s,'umrah_package',%s) returning id",
        (alice, partner)).fetchone()["id"]
    case_b = conn.execute(
        "insert into cases (owner_id, service_type) values (%s,'visit_visa') returning id", (bob,)).fetchone()["id"]
    for cid in (case_a, case_b):
        conn.execute("""insert into case_events (case_id, actor_type, event_type, message_en, message_ur, visible_to_user)
                        values (%s,'ai','x','visible','v',true), (%s,'ops','note','internal','i',false)""", (cid, cid))
    conn.execute("insert into travellers (owner_id, full_name_as_passport) values (%s,'ALICE A')", (alice,))
    snap_src = conn.execute("select id from sources limit 1").fetchone()["id"]
    snap = conn.execute("""insert into source_snapshots (source_id, content_markdown, content_hash)
                           values (%s,'x','h') returning id""", (snap_src,)).fetchone()["id"]
    conn.execute("""insert into policy_records (country, visa_type, field, value, source_snapshot_id, status)
                    values ('ZZ','v','gov_fee','1',%s,'auto'), ('ZZ','v','gov_fee','2',%s,'disputed')""", (snap, snap))
    return dict(alice=alice, bob=bob, ops=ops, puser=puser, case_a=case_a, case_b=case_b)


def test_customer_sees_only_own_cases(conn, world):
    with as_user(conn, world["alice"]) as c:
        ids = {r["id"] for r in c.execute("select id from cases")}
        assert ids == {world["case_a"]}


def test_customer_sees_only_visible_events(conn, world):
    with as_user(conn, world["alice"]) as c:
        msgs = [r["message_en"] for r in c.execute("select message_en from case_events")]
        assert msgs == ["visible"]


def test_customer_cannot_write_cases_or_events(conn, world):
    with as_user(conn, world["alice"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update cases set status='submitted' where id=%s", (world["case_a"],))
    with as_user(conn, world["alice"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("""insert into case_events (case_id, actor_type, event_type, message_en, message_ur)
                         values (%s,'user','x','a','b')""", (world["case_a"],))


def test_customer_cannot_escalate_role(conn, world):
    with as_user(conn, world["alice"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update profiles set role='admin' where id=%s", (world["alice"],))
    with as_user(conn, world["alice"]) as c:
        c.execute("update profiles set preferred_locale='ur' where id=%s", (world["alice"],))
        assert c.execute("select preferred_locale from profiles where id=%s", (world["alice"],)).fetchone()["preferred_locale"] == "ur"


def test_customer_travellers_isolated_and_no_enc_writes(conn, world):
    with as_user(conn, world["bob"]) as c:
        assert c.execute("select count(*) n from travellers").fetchone()["n"] == 0
    with as_user(conn, world["alice"]) as c:
        assert c.execute("select count(*) n from travellers").fetchone()["n"] == 1
    with as_user(conn, world["alice"]) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("update travellers set cnic_enc='x' where owner_id=%s", (world["alice"],))
    with as_user(conn, world["bob"]) as c:  # cannot create a traveller for someone else
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("insert into travellers (owner_id, full_name_as_passport) values (%s,'X')", (world["alice"],))


def test_ops_reads_everything_incl_internal(conn, world):
    with as_user(conn, world["ops"]) as c:
        assert c.execute("select count(*) n from cases").fetchone()["n"] >= 2
        assert c.execute("select count(*) n from case_events where not visible_to_user").fetchone()["n"] >= 2


def test_partner_sees_only_assigned_cases(conn, world):
    with as_user(conn, world["puser"]) as c:
        ids = {r["id"] for r in c.execute("select id from cases")}
        assert ids == {world["case_a"]}
        msgs = [r["message_en"] for r in c.execute("select message_en from case_events")]
        assert msgs == ["visible"]


def test_public_knowledge_hides_disputed(conn, world):
    with as_user(conn, None) as c:
        vals = [r["value"] for r in c.execute("select value from policy_records where country='ZZ'")]
        assert vals == [1]
        assert c.execute("select count(*) n from sources").fetchone()["n"] > 0
        assert c.execute("select count(*) n from cases").fetchone()["n"] == 0
        assert c.execute("select count(*) n from scam_checks").fetchone()["n"] == 0
