"""Weekday Salesforce pipeline digest.

Reads open opportunities live through CData Connect AI (no ETL), saves a
snapshot to Render Postgres, and optionally posts a summary to Slack.

This job is an optional example of the SQL path into Connect AI. The agent does
not depend on it. To use another source, change QUERY to any table your
Connect AI connections expose; to skip it, delete the cron service from
render.yaml.
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


# Connect AI names a new Salesforce connection Salesforce1 unless you rename it.
CATALOG = os.environ.get("CDATA_SF_CATALOG", "").strip() or "Salesforce1"
LOOKAHEAD_DAYS = int(os.environ.get("DIGEST_LOOKAHEAD_DAYS", "14").strip() or "14")

# Connection names often contain hyphens (e.g. Salesforce-Prod). Only "]"
# could escape the bracketed identifier, and it is not in this set.
if not re.fullmatch(r"[A-Za-z0-9_-]+", CATALOG):
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


def _explain_connect_ai_error(exc: Exception) -> str:
    text = str(exc)
    if "401" in text or "403" in text:
        return (
            "Connect AI rejected the credentials, so the query never ran. Check "
            "that CDATA_USERNAME is your Connect AI login email and CDATA_PAT is "
            "a current Personal Access Token."
        )
    return f"Connect AI query failed: {text}"


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
        if cur.description is None:
            # Connect AI reports query errors as HTTP 200 with an "error" body,
            # which cdata-connect-ai 1.2.0 drops: execute() returns normally
            # with no result schema. The usual cause here is the catalog.
            sys.exit(
                f"Connect AI returned no result set. Most likely there is no "
                f"connection named {CATALOG!r}: set CDATA_SF_CATALOG to your "
                "Salesforce connection's name, exactly as it appears under "
                "Sources in Connect AI. (The connector hides the error text.)"
            )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except cdata_connect_ai.Error as exc:
        sys.exit(_explain_connect_ai_error(exc))
    finally:
        conn.close()


def save_snapshot(today: dt.date, opps: list[dict]) -> None:
    try:
        pg = psycopg.connect(_required("DATABASE_URL"), connect_timeout=10)
    except psycopg.OperationalError as exc:
        sys.exit(
            f"Could not connect to Postgres ({str(exc).strip().splitlines()[-1]}). "
            "Check DATABASE_URL; locally, start it with `docker compose up -d db`."
        )
    with pg:
        pg.execute(DDL)
        with pg.cursor() as cur:
            cur.executemany(
                UPSERT,
                [
                    (today, o["Id"], o["Name"], o["StageName"], o["Amount"], o["CloseDate"])
                    for o in opps
                ],
            )
    log.info("Saved %d rows to pipeline_snapshot for %s", len(opps), today)


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
    try:
        requests.post(webhook, json={"text": text}, timeout=10).raise_for_status()
    except requests.RequestException as exc:
        # The snapshot is already saved; say so, but still fail the run.
        sys.exit(f"Snapshot saved, but the Slack post failed: {exc}. Check SLACK_WEBHOOK_URL.")
    log.info("Posted digest to Slack")


def main() -> None:
    today = dt.date.today()
    cutoff = today + dt.timedelta(days=LOOKAHEAD_DAYS)
    opps = fetch_open_opportunities(cutoff)
    log.info("Fetched %d open opportunities closing by %s", len(opps), cutoff)
    save_snapshot(today, opps)
    post_to_slack(opps, cutoff)


if __name__ == "__main__":
    main()  # any exception exits non-zero, so Render marks the run as failed
