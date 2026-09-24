# Working in this repo

A starter Blueprint for a chatbot over live enterprise data. It shows two ways
a Render service reaches CData Connect AI: **MCP** for the agent (`app/`), and
the **`cdata-connect-ai` Python connector** for an optional cron job (`jobs/`).
`render.yaml` deploys both plus Postgres. The goal is getting people from zero
to a working chatbot as fast as possible; weigh every change against that.

Ignore `../AGENTS.md`. It describes a Mintlify documentation site and applies to
a different project in the parent directory, not to this one.

See `CONTRIBUTING.md` for the change checklist and `README.md` for user-facing
setup. This file holds what neither of those makes obvious.

## Layout

| Path | Role |
| --- | --- |
| `app/main.py` | FastAPI app. Startup (Postgres check, agent build, retention task), `/chat`, `/chat/stream`, `/healthz`, `/tools`, the chat page at `/`, `/static` |
| `app/steps.py` | Human labels for tool calls; extracts this turn's SQL (`queries_in`) |
| `app/retention.py` | Deletes conversations idle past `CONVERSATION_RETENTION_DAYS` |
| `app/suggest.py` | One extra LLM call after each streamed answer for three follow-up questions |
| `app/agent.py` | `create_agent` over MCP tools; `TruncateToolOutput` middleware caps tool results |
| `app/config.py` | Env parsing and validation; `LLM_API_KEYS` maps provider to key variable |
| `app/errors.py` | `SetupError`, `root_cause()`, `describe_mcp_error()`, `describe_llm_error()` |
| `app/static/index.html` | Single-file chat page; reads `/chat/stream` |
| `app/static/vendor/` | marked + DOMPurify, copied unmodified from npm; versions, hashes and licenses in its README |
| `app/static/brand/` | CData logos, favicon and DM fonts (from the brand kit) and Render's mark; sources and rules in its README |
| `jobs/pipeline_digest.py` | Optional Salesforce digest over the SQL connector |
| `render.yaml` | Blueprint; uses Render's native Python runtime |
| `compose.yaml`, `Dockerfile`, `.dockerignore` | Local development only |
| `requirements.in` → `requirements.txt` | Top-level deps → compiled exact pins |
| `docs/chat-screenshot.png` | README screenshot, taken of the real page with a stub agent returning sample data |
| `tests/`, `pytest.ini`, `requirements-dev.*` | Test suite and its pinned dependencies |
| `.github/workflows/ci.yml` | Tests, pin check, and Docker build on each PR |
| `.github/` (other) | `CODEOWNERS`, PR template, bug-report form, issue chooser links |
| `SECURITY.md`, `CONTRIBUTING.md`, `LICENSE` | Community files; MIT, matching CData's other public repos |

## Current state (2026-09-24)

**Verified live** against a real Connect AI tenant, running locally in Docker:
startup loads 12 MCP tools; chat answers from real connections; conversation
memory persists in Postgres; bad SQL goes back to the model as a tool error
rather than failing the request; the digest reads 369 opportunities and
writes the snapshot; all startup error paths print one `Startup failed:` line
naming the variable to fix. The chat page is browser-tested (desktop, phone
width, dark mode, XSS sanitizing, key and no-key modes).

Streaming was verified live too: a real question streamed its steps over 73
seconds (two failed `IsClosed = 0` queries, then a working one), and the
answer (6,699 open opportunities) matched a direct Connect AI query.

**Deployed to Render** only before the current round of changes (an earlier
version was tested on Render in 2026-09). The chat page, streaming, error
handling, size cap, retention, optional `APP_API_KEY`, and the
`ANTHROPIC_API_KEY` prompt have not yet been deployed. Streaming through
Render's proxy is the thing most worth checking: `/chat/stream` sends a
`start` event at once and `X-Accel-Buffering: no`, but has not been tested
behind Render.

**Not yet verified:**

- **Toolkit URLs.** The default endpoint uses HTTP Basic auth with base64 of
  `email:PAT`. Whether Toolkit MCP URLs accept the same auth is unconfirmed.
- **Slack posting.** Tested runs had no `SLACK_WEBHOOK_URL`.
- **Preview environments.** Render does not copy prompted secrets into
  previews, so set the Connect AI credentials by hand there.
- **Anthropic and `gpt-4o` end to end.** Chat was verified live only through
  an OpenAI-compatible gateway to local Qwen3 models. Anthropic and OpenAI
  errors are unit-tested with the real SDK exception types.

**Known limitations:**

- Small local models are unreliable agents. `qwen3:8b` skipped the tools and
  invented an answer; `qwen3:14b` handled single-tool questions but drifted on
  multi-step ones (described columns instead of querying) and took ~3 minutes.
- Nothing tests `render.yaml` except deploying it.

## Local development

```bash
cp .env.example .env    # CDATA_USERNAME, CDATA_PAT, an LLM key
docker compose up       # Postgres + agent on http://127.0.0.1:8000
docker compose run --rm digest
```

- **Docker engine.** Maintainers here use Colima (`brew install colima docker
  docker-compose docker-buildx`), with
  `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]` in
  `~/.docker/config.json`. Colima shares only `$HOME` with its VM: a bind mount
  from `/tmp` or the scratchpad is silently empty inside the container
  (`Could not import module "app.main"`).
- **Hot reload** relies on `WATCHFILES_FORCE_POLLING`. On Colima, file events
  never reach the container, and without polling `--reload` silently never
  fires. Check the log for `WatchFiles detected changes` after an edit.
- **`.env` changes** need `docker compose up` (container recreation); the
  reloader does not see them.
- **`DATABASE_URL`**: compose overrides it to reach its `db` service; the value
  in `.env` only matters when running the app outside Docker. The agent
  service has its own `environment:` block, which *replaces* the anchor's
  rather than merging, so it repeats `DATABASE_URL`.
- **LLM gateway.** Set `LLM_MODEL=openai:<gateway model>`, `OPENAI_BASE_URL`,
  and `OPENAI_API_KEY`. `host.docker.internal` reaches the host from a
  container (defined by Colima and Docker Desktop, and by `extra_hosts` in
  `compose.yaml` for Linux).
- **Do not print resolved config.** `docker compose config` expands `.env`
  into the output, secrets included.
- **Without Docker for the app**: `uv venv --python 3.12 .venv`, `uv pip sync
  --python .venv requirements.txt`, then `uvicorn app.main:app --reload
  --env-file .env` with `docker compose up -d db`.

## Tests

`.venv/bin/pytest` (about 10 seconds; `docker compose up -d db` first for the
database tests). `CONTRIBUTING.md` describes the layers and the live opt-in.
What a future session needs to know:

- **Fakes, not network.** `tests/fakes.py` has `FakeMCPClient` (patched over
  `app.agent.MultiServerMCPClient`) and `ScriptedModel`, a chat model that
  calls listed tools once and then reports what it saw (`humans=<n>
  truncated=<bool>`), so tests can assert on the conversation the agent built.
  `make_client` in `conftest.py` stubs the lifespan for route tests;
  `test_startup.py` runs the real lifespan against real Postgres.
- **Realistic failures.** Build them from the real types:
  `openai.AuthenticationError(..., response=httpx.Response(401, ...))`,
  `httpx.HTTPStatusError` inside nested `ExceptionGroup`s, `McpError`.
- **Environment is cleared before every test** (`clean_env`), so `.env` never
  leaks in. The live tests read credentials at import time for that reason.
- **The digest reads its config at import**, so its tests set env and
  `importlib.reload` the module (`load_digest` fixture).
- **Database tests use `agent_test`**, created on first use; they never touch
  the `agent` database that holds local dev data.
- **Browser tests** run `tests/ui_server.py` under uvicorn in a subprocess,
  with the installed Chrome if present, else Playwright's Chromium.
- **In CI, missing Postgres or browser fails** instead of skipping
  (`skip_or_fail`).
- **Verified by mutation (2026-09-24):** each of the twelve bugs fixed in
  this round, and nine plausible bugs in streaming, the SQL trace, vendoring
  and retention, and eight in follow-up suggestions, was reintroduced by
  hand, and some test failed each time.
  When fixing a bug, check the new test fails without the fix.
- `StubAgent` (route tests) plays scripted `tool_step()` messages through both
  `ainvoke` and `astream`, and can fail mid-stream (`fail_after_steps`).
  `ScriptedModel` takes `(name, args)` pairs and replays its script each turn.
- Naming a scratch script `inspect.py` shadows the stdlib module and breaks
  LangChain imports.

## Conventions

### Secrets

Never commit credentials. Every secret is supplied by Render at deploy time:
`sync: false` prompts the operator, `generateValue: true` lets Render create it.
The git history is clean — keep it that way. Local dev reads a gitignored
`.env` copied from `.env.example`; only the example is committed.

### Auth

`APP_API_KEY` is optional. Empty disables the bearer check on `/chat` and
`/tools` (startup logs a warning) and `/healthz` reports
`auth_required: false`, so the chat page skips its key prompt. That is only
safe because `render.yaml` always generates a key and `compose.yaml` publishes
ports on `127.0.0.1`. Keep both true.

### Error handling

Operator-fixable failures raise `app.errors.SetupError` with a message naming
the variable to change. Startup logs it as `Startup failed: ...`; `/chat` maps
MCP and LLM failures to a 502 with the same kind of message. When adding a
failure mode, extend `describe_mcp_error` / `describe_llm_error` rather than
catching locally.

- MCP transport errors arrive wrapped in nested `ExceptionGroup`s; use
  `root_cause()`.
- The MCP SDK reports an HTTP 404 (wrong URL) as `McpError: Session terminated`.
- Tool errors such as bad SQL never reach `/chat`: `langchain-mcp-adapters`
  returns them to the model as a `ToolMessage` with `status="error"` (verified
  live). Only transport failures escape.
- Startup checks Postgres with a direct connection first. Otherwise the pool
  retries quietly and dies 30 seconds later with an uninformative
  `PoolTimeout`.

### Streaming and the trace

`/chat/stream` runs `agent.astream(..., stream_mode="updates")`, which yields
`{"model": ...}` updates (AIMessages, with `tool_calls` when calling tools)
and `{"tools": ...}` updates (ToolMessages). It maps them to NDJSON events:
`start`, `step` (id, tool, label, sql), `step_done` (id, ok), then `done`
(reply, queries) or `error` (detail), then optionally `suggestions` (items).
The README documents the format for API users; keep it stable. Labels come from `describe_step` in
`app/steps.py`, one place for both the page and the API.

- The chat page sets every server string with `textContent`; only the model's
  reply goes through marked + DOMPurify. SQL is model output: treat it as
  hostile (`test_sql_is_shown_as_text_never_html`).
- With a checkpointer, `ainvoke` returns the whole thread. Use
  `current_turn()` before extracting anything per-reply.

### Follow-up suggestions

After `done`, `/chat/stream` calls `suggest_followups` with the question, the
reply, and the SQL that succeeded, and sends a `suggestions` event if it gets
a usable list. `build_agent` returns the model as a third value for this
(`app.state.llm`). The rules:

- **Never break or delay the answer.** It runs after `done`; errors, a
  45-second timeout, and unparseable output all mean "no suggestions", logged
  as a warning. `parse_suggestions` tolerates code fences, prose, and Qwen3
  `<think>` blocks.
- **Stream only.** `/chat` never calls it, so the JSON API has no extra
  latency or cost. `SUGGEST_FOLLOWUPS=false` turns it off everywhere.
- **Model output is hostile.** Chips are set with `textContent`
  (`test_suggestions_are_shown_as_text_never_html`).
- **The page re-enables Send on `done`**, not at stream end, and numbers each
  request so a slower, older stream can't re-enable Send or attach chips to
  an old answer (`test_a_new_question_discards_late_suggestions`).
- Tested live with `qwen3:14b`: suggestions arrived 3.8 s after the answer. The
  first prompt suggested a question the answer already answered; the "NOT
  already answered" rule fixed that. Expect better suggestions from larger
  models.

### Branding

The chat page follows the CData Brand Guidelines (Feb 2026). The kit lives in
the internal skills repo at `../skills/assets/brand` (`PALETTE.md` has the
colours and usage rules); `app/static/brand/README.md` records how this page
applies them. The rules that matter when editing the page:

- **Agility yellow `#FFE500` is an accent, never text**, and only ever with
  Depth `#15151C` on it. It is on the Send button, the header rule, focus
  rings, and dark-mode link underlines.
- **Navy (Resolve) fills take white text.** Small secondary text is Gray 8
  `#5E5D60` or darker on light backgrounds; never Gray 6/7.
- **Grafier stays out of the repo** (commercially licensed). DM Sans and DM
  Mono are OFL and vendored with their licenses.
- **Logos are trademarks outside the MIT license**, noted in the README.
- `test_text_contrast_meets_wcag_aa` measures 14 text/background pairs in
  both themes; a colour change that breaks AA fails it. Mutation-checked:
  Gray 6 text and white-on-yellow both fail it.

### Retention

`retention_loop` runs at startup and daily in the web service, deleting
threads whose *newest* checkpoint `ts` is older than the limit (via
`adelete_thread`, which clears all three checkpoint tables). Every instance
runs it; that is harmless because the delete is idempotent. It never touches
`pipeline_snapshot`.

### Vendored scripts

`app/static/vendor/` holds unmodified npm files. The browser tests block all
non-local requests, so a CDN reference sneaking back in fails them. To
update, follow `app/static/vendor/README.md` and refresh its hashes.

### Dependencies

`requirements.in` lists top-level packages; `requirements.txt` is compiled from
it with exact pins (`--universal`, so it resolves for Render's Linux too).
Never hand-edit `requirements.txt`. The regenerate command is at the top of
`requirements.in`. Adding an LLM provider means a package there plus a line in
`LLM_API_KEYS` in `app/config.py`.

### Env vars

- **Strip every env var before use.** A PAT pasted into Render with a trailing
  newline authenticates in one service and 401s in another. `app/config.py` and
  `jobs/pipeline_digest.py` both strip; keep it that way in new code.
- In `.env`, keep comments on their own lines. python-dotenv reads an inline
  comment after an *empty* value as the value.

## Connect AI facts worth not re-deriving

All verified against a live tenant, 2026-09:

- Tables are `[Catalog].[Schema].[Table]`. The catalog is the **connection name**
  in Connect AI, so it varies per account; it is set by `CDATA_SF_CATALOG`. For
  Salesforce the schema is always `Salesforce`.
- `Salesforce1` is the one default for `CDATA_SF_CATALOG`, in the code,
  `render.yaml` and the README. Keep all three in step.
- Connection names often contain hyphens (`Salesforce-Prod`), so identifier
  validation must allow them. Only `]` can escape a bracketed identifier.
- Connect AI reports query errors (such as a missing catalog) as **HTTP 200**
  with `{"error": {...}}` in the body. `cdata-connect-ai` 1.2.0 drops it:
  `execute()` returns normally and `cur.description` is `None`. Check for that;
  do not wait for an exception. Only HTTP errors (like a 401) raise. The
  connector has no metadata API to list catalogs either. Worth reporting
  upstream (`CDataSoftware/cdata-connect-ai-python`).
- The default MCP endpoint exposes 12 tools, including `execute_insert`,
  `execute_update` and `executeProcedure`. Whether writes succeed depends on the
  PAT's permissions per catalog (`getCatalogs` reports them).
- `getTables` accepts a `tableName` filter. Unfiltered, it returned ~440K
  characters (~110K tokens) for a large Salesforce org, and `getColumns` on
  `Opportunity` over 20K. `TruncateToolOutput` caps each result at
  `TOOL_OUTPUT_MAX_CHARS` and tells the model how to narrow the call. Without
  it, Ollama silently drops the *start* of an over-long prompt: the system
  prompt and the question.
- `OPENAI_BASE_URL` (read by the openai SDK, respected by `langchain-openai`)
  points `openai:` models at any OpenAI-compatible gateway with no code change.
- The connector declares `paramstyle = "pyformat"`, so `%(name)s` with a dict is
  correct. Its signature is
  `connect(config_path, base_url, username, password, workspace, timeout, ...)`.
- `IsClosed = false` works and `IsClosed = 0` **fails** against Salesforce,
  despite the driver guide documenting `0`. Models reach for `0` first (seen
  live), then recover after inspecting columns.
- Salesforce `CloseDate` comes back as a plain `YYYY-MM-DD`, not a datetime.
- `Opportunity.IsClosed` / `IsWon` are readonly; `StageName` drives them.
- The connector's connections are not thread-safe. Use one per request or per
  worker, never a shared global.
- A 401 from the connector means credentials, not SQL — the query never ran.
- The agent loads its MCP tools during startup, so bad credentials kill the boot
  rather than the first request. `/healthz` reporting `mcp_tools > 0` means auth
  succeeded *at boot*; a PAT revoked since then surfaces as a 502 on `/chat`.

## Render constraints that shaped render.yaml

- An `envVarGroup` cannot hold `sync: false` variables. That is why each service
  prompts for its own `CDATA_USERNAME` / `CDATA_PAT` rather than sharing them.
- Blank `sync: false` values are accepted at deploy time (the tested deploy
  left `SLACK_WEBHOOK_URL` blank). That is what lets the agent prompt for both
  `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` and use whichever is filled in.
- Preview environments do not inherit prompted secrets.
- `render.yaml` uses Render's native Python runtime, not the `Dockerfile`.
  Keep the Dockerfile's Python version in step with `PYTHON_VERSION`.
- The Deploy to Render button reads `render.yaml` anonymously, so this repo must
  stay public for it to work.

## Publishing checklist

- Several places hardcode `jerodj-cdata/connect-ai-render-starter`: the
  README's Deploy button and `git clone` URL, the security link in
  `.github/ISSUE_TEMPLATE/config.yml`, the chat page footer's Source and
  Report-an-issue links, and `REPO` in `tests/test_ui.py`. Update them
  together when the repo moves to the `CDataSoftware` org
  (`grep -rn jerodj-cdata --exclude-dir=.venv`).
- Enable GitHub private vulnerability reporting. `SECURITY.md` and the issue
  chooser send reports there, and the link 404s until it is on.
- `.github/CODEOWNERS` names @JoeKarlsson, @jerodj-cdata and @Ho1yShif. Owners
  need write access, so revisit it if the team or org changes. Turn on
  "Require review from Code Owners" in branch protection to enforce it.
- Deploy the current version to Render once and update "Current state" above.
