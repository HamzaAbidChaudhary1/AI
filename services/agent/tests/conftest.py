import pytest
from rahbar_agent.crawl import pipeline
from rahbar_agent.crawl.providers import FixtureProvider, set_crawl_provider


@pytest.fixture(scope="session")
def crawled(db):
    """All seeded official sources crawled from fixtures, with policy extraction."""
    set_crawl_provider(FixtureProvider())
    for r in db.fetch_all("select id from sources where active"):
        try:
            pipeline.crawl_source(str(r["id"]), extract_inline=True)
        except Exception:
            pass
    yield
    set_crawl_provider(None)


@pytest.fixture
def user(db):
    import uuid

    uid = str(uuid.uuid4())
    db.execute("insert into auth.users (id, email, raw_user_meta_data) values (%s,%s,'{\"full_name\":\"Test User\"}')",
               (uid, f"{uid}@t.test"))
    return uid
