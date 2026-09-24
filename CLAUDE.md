# Working in this repo

A starter Blueprint showing two ways a Render service reaches CData Connect AI:
**MCP** for the agent (`app/`), and the **`cdata-connect-ai` Python connector**
for the scheduled job (`jobs/`). `render.yaml` deploys both plus Postgres.

Ignore `../AGENTS.md`. It describes a Mintlify documentation site and applies to
a different project in the parent directory, not to this one.

## Secrets

Never commit credentials. Every secret is supplied by Render at deploy time:
`sync: false` prompts the operator, `generateValue: true` lets Render create it.
The git history is clean — keep it that way. Local dev reads a gitignored
`.env` copied from `.env.example`; only the example is committed.

## Connect AI facts worth not re-deriving

All verified against a live tenant, 2026-09:

- Tables are `[Catalog].[Schema].[Table]`. The catalog is the **connection name**
  in Connect AI, so it varies per account; it is set by `CDATA_SF_CATALOG`. For
  Salesforce the schema is always `Salesforce`.
- `Salesforce1` is the one default for `CDATA_SF_CATALOG`, in the code,
  `render.yaml` and the README. Keep all three in step.
- Connection names often contain hyphens (`Salesforce-Prod`), so identifier
  validation must allow them. Only `]` can escape a bracketed identifier.
- A missing catalog fails with `The catalog 'X' either does not exist or is
  inaccessible`. The connector has no metadata API to list catalogs.
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

- `render.yaml` uses Render's native Python runtime. The `Dockerfile` and
  `compose.yaml` are for local development only; keep the Python version in
  step with `PYTHON_VERSION`.
- Blank `sync: false` values are accepted at deploy time (the tested deploy
  left `SLACK_WEBHOOK_URL` blank). That is what lets the agent prompt for both
  `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` and use whichever is filled in.

## Error handling

Operator-fixable failures raise `app.errors.SetupError` with a message naming
the variable to change. Startup logs it as `Startup failed: ...`; `/chat` maps
MCP and LLM failures to a 502 with the same kind of message. When adding a
failure mode, extend `describe_mcp_error` / `describe_llm_error` rather than
catching locally.

- MCP transport errors arrive wrapped in nested `ExceptionGroup`s; use
  `root_cause()`.
- The MCP SDK reports an HTTP 404 (wrong URL) as `McpError: Session terminated`.
- Tool errors such as bad SQL never reach `/chat`: `langchain-mcp-adapters`
  returns them to the model, which retries. Only transport failures escape.

## Dependencies

`requirements.in` lists top-level packages; `requirements.txt` is compiled from
it with exact pins (`--universal`, so it resolves for Render's Linux too).
Never hand-edit `requirements.txt`. The regenerate command is at the top of
`requirements.in`. Adding an LLM provider means a package there plus a line in
`LLM_API_KEYS` in `app/config.py`.

## Gotchas

- **Strip every env var before use.** A PAT pasted into Render with a trailing
  newline authenticates in one service and 401s in another. `app/config.py` and
  `jobs/pipeline_digest.py` both strip; keep it that way in new code.
- A 401 from the connector means credentials, not SQL — the query never ran.
- The agent loads its MCP tools during startup, so bad credentials kill the boot
  rather than the first request. `/healthz` reporting `mcp_tools > 0` means auth
  succeeded *at boot*; a PAT revoked since then will not show up until a redeploy.

- In `.env`, keep comments on their own lines. python-dotenv reads an inline
  comment after an *empty* value as the value.

## Running and testing locally

`docker compose up` runs Postgres and the agent with hot reload on
<http://localhost:8000>; `docker compose run --rm digest` runs the cron job.
Compose overrides `DATABASE_URL` to reach its `db` service, so the one in
`.env` only matters when running outside Docker.

There is no test suite, and a full run needs live credentials. For quick
checks, `python3 -m py_compile` the changed files. To exercise startup error
paths, `docker compose run --rm --no-deps -T -e VAR=bad agent uvicorn
app.main:app` exits after printing `Startup failed: ...`. To exercise routes
without network access, import `app.main` from the venv, override
`app.router.lifespan_context` with a no-op async context manager, set
`app.state.settings`, `tool_names` and a stub `agent` whose `ainvoke` returns or
raises what you need, and drive it with FastAPI's `TestClient`.

## Not yet verified

- **Toolkit URLs.** The default endpoint uses HTTP Basic auth with base64 of
  `email:PAT`. Whether Toolkit MCP URLs accept the same auth is unconfirmed.
- **Slack posting.** Tested runs had no `SLACK_WEBHOOK_URL`.
- **Preview environments.** Render does not copy prompted secrets into
  previews, so set the Connect AI credentials by hand there.

## Publishing

The Deploy button points at `jerodj-cdata/connect-ai-render-starter`. When the
repo moves to the `CDataSoftware` org, change the URL in the README's button.
The repo must stay public for the button to work.
