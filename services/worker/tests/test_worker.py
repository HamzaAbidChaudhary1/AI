"""Phase 0 acceptance: the worker processes a dummy job. Plus retries and scheduling."""

from rahbar_agent import jobs
from rahbar_worker.main import run_once, schedule_due


def _drain(db):
    db.execute("update jobs set status='done' where status='queued'")


def test_worker_processes_dummy_job(db):
    _drain(db)
    jid = jobs.enqueue("dummy", {"hello": "world"})
    assert run_once() == jid
    j = jobs.get_job(jid)
    assert j["status"] == "done" and j["result"] == {"echo": {"hello": "world"}}
    assert run_once() is None


def test_failed_job_retries_then_fails(db):
    _drain(db)
    jid = jobs.enqueue("no_such_type", {}, max_attempts=2)
    run_once()
    j = jobs.get_job(jid)
    assert j["status"] == "queued" and j["attempts"] == 1 and "no handler" in j["last_error"]
    db.execute("update jobs set run_at=now() where id=%s", (jid,))
    run_once()
    assert jobs.get_job(jid)["status"] == "failed"


def test_scheduler_enqueues_due_jobs(db):
    _drain(db)
    db.execute("update scheduled_jobs set next_run_at=now() - interval '1 minute'")
    assert schedule_due() == 4
    assert schedule_due() == 0
    _drain(db)
