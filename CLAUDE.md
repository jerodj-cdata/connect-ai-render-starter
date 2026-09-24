# Working in this repo

A starter Blueprint showing two ways a Render service reaches CData Connect AI:
**MCP** for the agent (`app/`), and the **`cdata-connect-ai` Python connector**
for the scheduled job (`jobs/`). `render.yaml` deploys both plus Postgres.

Ignore `../AGENTS.md`. It describes a Mintlify documentation site and applies to
a different project in the parent directory, not to this one.

## Secrets

Never commit credentials. Every secret is supplied by Render at deploy time:
`sync: false` prompts the operator, `generateValue: true` lets Render create it.
The git history is clean — keep it that way. There is no `.env` in this repo.

## Connect AI facts worth not re-deriving

All verified against a live tenant, 2026-09:

- Tables are `[Catalog].[Schema].[Table]`. The catalog is the **connection name**
  in Connect AI, so it varies per account; it is set by `CDATA_SF_CATALOG`. For
  Salesforce the schema is always `Salesforce`.
- The connector declares `paramstyle = "pyformat"`, so `%(name)s` with a dict is
  correct. Its signature is
  `connect(config_path, base_url, username, password, workspace, timeout, ...)`.
- `IsClosed = false` parses, despite the driver guide documenting `IsClosed = 0`.
- Salesforce `CloseDate` comes back as a plain `YYYY-MM-DD`, not a datetime.
- `Opportunity.IsClosed` / `IsWon` are readonly; `StageName` drives them.
- The connector's connections are not thread-safe. Use one per request or per
  worker, never a shared global.

## Render constraints that shaped render.yaml

- An `envVarGroup` cannot hold `sync: false` variables. That is why each service
  prompts for its own `CDATA_USERNAME` / `CDATA_PAT` rather than sharing them.
- Preview environments do not inherit prompted secrets.
- The Deploy to Render button reads `render.yaml` anonymously, so this repo must
  stay public for it to work.

## Gotchas

- **Strip every env var before use.** A PAT pasted into Render with a trailing
  newline authenticates in one service and 401s in another. `app/config.py` and
  `jobs/pipeline_digest.py` both strip; keep it that way in new code.
- A 401 from the connector means credentials, not SQL — the query never ran.
- The agent loads its MCP tools during startup, so bad credentials kill the boot
  rather than the first request. `/healthz` reporting `mcp_tools > 0` means auth
  succeeded *at boot*; a PAT revoked since then will not show up until a redeploy.

## Testing locally

There is no test suite and the full app needs Postgres plus live credentials.
For quick checks, `python3 -m py_compile` the changed files. To exercise routes,
import `app.main` with `langgraph`, `psycopg`, `psycopg_pool` and `app.agent`
stubbed into `sys.modules`, override `app.router.lifespan_context` with a no-op
async context manager, and set `app.state` by hand. The same stub trick works on
`jobs.pipeline_digest` for testing env handling without network access.
