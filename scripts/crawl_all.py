"""Crawl every active source once, with inline extraction.
Uses live Firecrawl/Apify if keys are set (CRAWL_PROVIDER=auto), otherwise the labelled test fixtures."""

from rahbar_agent.crawl import pipeline
from rahbar_agent.db import fetch_all, pool

ok = failed = 0
for row in fetch_all("select id, url from sources where active order by url"):
    try:
        r = pipeline.crawl_source(str(row["id"]), extract_inline=True)
        ok += 1
        print(f"ok   {row['url']}  changed={r['changed']}")
    except Exception as e:  # report and continue
        failed += 1
        print(f"fail {row['url']}  {e}")
print(f"{ok} crawled, {failed} failed")


pool().close()
