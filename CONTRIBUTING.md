# Contributing

Thanks for helping improve the Connect AI + Render starter. Its job is to get
someone from zero to a working chatbot over their own data as fast as
possible, so the bar for any change is: does it keep setup quick and failures
obvious?

## Set up

Follow [Run locally](README.md#option-b-run-locally) in the README. In short:

```bash
cp .env.example .env    # set CDATA_USERNAME, CDATA_PAT and an LLM key
docker compose up       # http://localhost:8000, reloads on edits under app/
```

You need a Connect AI account with at least one connection. A throwaway or
sandbox account is best: with the default MCP endpoint, the agent can reach
everything your PAT can, and query results are sent to your LLM provider.

## Project layout

| Path | What it is |
| --- | --- |
| `app/main.py` | FastAPI app: startup, `/chat`, `/chat/stream`, `/healthz`, `/tools`, serves the chat page |
| `app/agent.py` | Builds the LangGraph agent from Connect AI's MCP tools; caps tool output size |
| `app/steps.py` | Labels for each tool call, and the SQL behind each answer |
| `app/retention.py` | Deletes old conversations (`CONVERSATION_RETENTION_DAYS`) |
| `app/suggest.py` | Suggests follow-up questions after each answer |
| `app/config.py` | Reads and validates environment variables |
| `app/errors.py` | Turns low-level failures into messages that name the fix |
| `app/static/index.html` | The chat page: one file, no build step |
| `app/static/vendor/` | The page's two libraries, vendored; see its README before updating |
| `jobs/pipeline_digest.py` | Optional cron job using the `cdata-connect-ai` SQL connector |
| `render.yaml` | The Render Blueprint (what the Deploy button creates) |
| `compose.yaml`, `Dockerfile` | Local development only; Render does not use them |
| `requirements.in` / `requirements.txt` | Top-level dependencies / compiled exact pins |
| `requirements-dev.in` / `requirements-dev.txt` | Test dependencies, constrained to the app's pins |
| `tests/` | The test suite; `fakes.py` and `ui_server.py` are its offline stand-ins |

## Making a change

1. Branch from `main`.
2. Keep the change focused, and match the surrounding code's style and comment
   density.
3. Verify it (below), then open a pull request that says what changed, why,
   and how you checked it.

### Rules of the road

- **Never commit credentials.** `.env` is gitignored; only `.env.example` is
  committed, with empty values. Secrets on Render come from `sync: false`
  prompts or `generateValue: true`. Search your diff for keys before pushing.
- **Strip every environment variable** before use. A value pasted with a
  trailing newline otherwise fails authentication in confusing ways.
- **Make failures name the fix.** Raise `SetupError` (from `app/errors.py`) for
  anything an operator can correct, with a message naming the variable to
  change. For new MCP or LLM failure modes, extend `describe_mcp_error` /
  `describe_llm_error` rather than catching locally.
- **Don't hand-edit `requirements.txt`.** Edit `requirements.in`, then run the
  compile command at the top of that file (it needs
  [uv](https://docs.astral.sh/uv/)). Commit both files.
- **Keep defaults in step.** `CDATA_SF_CATALOG` defaults to `Salesforce1` in
  `jobs/pipeline_digest.py`, `render.yaml`, and the README. Change all three
  together.
- **Don't weaken local-only auth.** An empty `APP_API_KEY` disables the API
  key check. That is only safe because `render.yaml` always generates a key and
  `compose.yaml` binds ports to `127.0.0.1`. Keep both.

## Verifying a change

### Run the tests

```bash
uv venv --python 3.12 .venv   # uv fetches Python 3.12 if you don't have it
uv pip install --python .venv -r requirements.txt -r requirements-dev.txt
docker compose up -d db       # for the database tests
.venv/bin/pytest             # about 10 seconds
```

The suite runs offline: the MCP server and the model are faked. It has four
layers:

| Layer | Files | Needs |
| --- | --- | --- |
| Unit | `test_config`, `test_errors`, `test_agent`, `test_routes`, `test_stream`, `test_steps`, `test_suggest`, `test_pipeline_digest` | nothing |
| Database (`-m db`) | `test_startup`, `test_retention`, plus the snapshot test | Postgres; uses a separate `agent_test` database |
| Browser (`-m ui`) | `test_ui` | Chrome, or `.venv/bin/playwright install chromium`; runs with the internet blocked |
| Live (`-m live`) | `test_live` | a real Connect AI account; opt-in, see below |

Database and browser tests skip locally when their dependency is missing, and
fail in CI instead, so CI never goes green without them.

To check behaviour against real Connect AI (no LLM is called):

```bash
set -a; source .env; set +a
RUN_LIVE_TESTS=1 .venv/bin/pytest -m live
```

CI (`.github/workflows/ci.yml`) runs everything except the live tests on each
pull request, checks that `requirements*.txt` match their `.in` files, and
builds the Docker image.

### Check by hand

Tests don't replace trying the change. Before opening a pull request:

- [ ] **Tests pass:** `.venv/bin/pytest`, with a test added for new behaviour
      or a fixed bug.
- [ ] **It boots:** `docker compose up` logs `Loaded N tools` and
      `Application startup complete`, and `curl localhost:8000/healthz`
      reports `mcp_tools` above 0.
- [ ] **Chat works:** ask "What data sources can you reach?" in the chat page
      and get your real connections back.
- [ ] **A clean clone still works** if you changed setup, Docker, or
      `.env.example`: clone your branch into a new folder and follow the
      README's local steps exactly.
- [ ] **The digest runs** if you touched `jobs/`:
      `docker compose run --rm digest` logs `Fetched N open opportunities`.
- [ ] **The chat page looks right** in a browser if you touched
      `app/static/`. The tests check behaviour, not appearance.

You cannot test `render.yaml` locally. If you change it, say in the pull
request whether you deployed it to Render.

## Documentation

Update the docs in the same pull request:

- **README.md** for anything a user sees: setup steps, variables, or a new
  error message (add it to the Troubleshooting table).
- **CLAUDE.md** for anything a maintainer would otherwise rediscover the hard
  way: a Connect AI or Render quirk, or a verified fact about a dependency.

## Reporting a security issue

Please don't open a public issue for a vulnerability. See
[SECURITY.md](SECURITY.md) for how to report one privately, and what to do if
you leaked a credential.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
