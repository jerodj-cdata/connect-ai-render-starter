"""Weekday Salesforce pipeline digest.

Reads open opportunities live through CData Connect AI (no ETL), saves a
snapshot to Render Postgres, and optionally posts a summary to Slack.
"""
import datetime as dt
import logging
import os
import re
import sys

import cdata_connect_ai
import psycopg
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("pipeline_digest")

def _required(name: str) -> str:
    # Strip like app/config.py does: a PAT pasted into Render with a trailing
    # newline authenticates in the web service but 401s here otherwise.
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


CATALOG = os.environ.get("CDATA_SF_CATALOG", "Salesforce1").strip()
LOOKAHEAD_DAYS = int(os.environ.get("DIGEST_LOOKAHEAD_DAYS", "14").strip())

if not re.fullmatch(r"[A-Za-z0-9_]+", CATALOG):
    sys.exit(f"Invalid CDATA_SF_CATALOG: {CATALOG!r}")

QUERY = f"""
SELECT Id, Name, StageName, Amount, CloseDate
FROM [{CATALOG}].[Salesforce].[Opportunity]
WHERE IsClosed = false AND CloseDate <= %(cutoff)s
ORDER BY Amount DESC
"""

DDL = """
CREATE TABLE IF NOT EXISTS pipeline_snapshot (
    snapshot_date  date    NOT NULL,
    opportunity_id text    NOT NULL,
    name           text,
    stage          text,
    amount         numeric,
    close_date     date,
    PRIMARY KEY (snapshot_date, opportunity_id)
)
"""

UPSERT = """
INSERT INTO pipeline_snapshot
    (snapshot_date, opportunity_id, name, stage, amount, close_date)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (snapshot_date, opportunity_id) DO UPDATE SET
    name = EXCLUDED.name, stage = EXCLUDED.stage,
    amount = EXCLUDED.amount, close_date = EXCLUDED.close_date
"""


def fetch_open_opportunities(cutoff: dt.date) -> list[dict]:
    base_url = os.environ.get("CDATA_API_URL", "https://cloud.cdata.com/api").strip()
    username = _required("CDATA_USERNAME")
    pat = _required("CDATA_PAT")
    # Enough to tell a wrong account or a truncated paste apart from a 401 that
    # means the PAT itself was revoked. The PAT value is never logged.
    log.info("Connecting to %s as %s (PAT length %d)", base_url, username, len(pat))
    conn = cdata_connect_ai.connect(
        base_url=base_url, username=username, password=pat
    )
    try:
        cur = conn.cursor()
        cur.execute(QUERY, {"cutoff": cutoff.isoformat()})
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def save_snapshot(today: dt.date, opps: list[dict]) -> None:
    with psycopg.connect(_required("DATABASE_URL")) as pg:
        pg.execute(DDL)
        with pg.cursor() as cur:
            cur.executemany(
                UPSERT,
                [
                    (today, o["Id"], o["Name"], o["StageName"], o["Amount"], o["CloseDate"])
                    for o in opps
                ],
            )


def post_to_slack(opps: list[dict], cutoff: dt.date) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        log.info("SLACK_WEBHOOK_URL not set; skipping Slack post")
        return
    total = sum(float(o["Amount"] or 0) for o in opps)
    top = "\n".join(
        f"- {o['Name']} ({o['StageName']}): ${float(o['Amount'] or 0):,.0f}, closes {o['CloseDate']}"
        for o in opps[:5]
    )
    text = (
        f"*Pipeline closing by {cutoff}*: {len(opps)} open deals, ${total:,.0f} total\n{top}"
    )
    requests.post(webhook, json={"text": text}, timeout=10).raise_for_status()


def main() -> None:
    today = dt.date.today()
    cutoff = today + dt.timedelta(days=LOOKAHEAD_DAYS)
    opps = fetch_open_opportunities(cutoff)
    log.info("Fetched %d open opportunities closing by %s", len(opps), cutoff)
    save_snapshot(today, opps)
    post_to_slack(opps, cutoff)


if __name__ == "__main__":
    main()  # any exception exits non-zero, so Render marks the run as failed
