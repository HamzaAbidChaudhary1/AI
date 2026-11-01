"""Shared pytest fixtures. Tests run against a LOCAL Postgres (scripts/db_reset_local.sh)."""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
os.environ.setdefault("DATABASE_URL", "postgresql://postgres@localhost:54322/rahbar_test")
os.environ.setdefault("LLM_MODE", "offline")
os.environ.setdefault("ALLOW_TEST_DATA", "true")
os.environ.setdefault("CRAWL_PROVIDER", "fixture")
os.environ.setdefault("DOCS_ENCRYPTION_KEY", "k1:" + base64.b64encode(b"t" * 32).decode())
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret-with-at-least-32-characters!!")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ["DATABASE_URL"]
    subprocess.run([str(ROOT / "scripts/db_reset_local.sh")], check=True, env={**os.environ, "DATABASE_URL": url},
                   capture_output=True)
    return url


@pytest.fixture(scope="session")
def db(database_url: str):
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from rahbar_agent import db as dbmod

    p = ConnectionPool(database_url, min_size=1, max_size=5, kwargs={"row_factory": dict_row}, open=True)
    dbmod.set_pool(p)
    yield dbmod
    p.close()
    dbmod.set_pool(None)
