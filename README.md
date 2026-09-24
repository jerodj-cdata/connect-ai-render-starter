# CData Connect AI + Render Starter

Deploy a chatbot with live, governed access to hundreds of enterprise systems
(Salesforce, NetSuite, Snowflake, Jira, SharePoint and more) in one click.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/jerodj-cdata/connect-ai-render-starter)

This Blueprint deploys:

- **`connectai-agent`**: a chat UI and API backed by a LangGraph agent. Its
  tools come from Connect AI's remote MCP server, so it can explore and query
  any source you connect.
- **`connectai-agent-db`**: Render Postgres, which keeps conversation history.
- **`connectai-pipeline-digest`** *(optional)*: a weekday cron job showing the
  other path into Connect AI, plain SQL through the `cdata-connect-ai` Python
  connector. It snapshots open Salesforce opportunities. See
  [The pipeline digest](#the-pipeline-digest-optional).

## Before you start

1. In [Connect AI](https://cloud.cdata.com), add a connection to any source
   under **Sources**.
2. Create a Personal Access Token under **Settings** → **Access Tokens**.
3. Have an API key for an LLM provider: OpenAI or Anthropic out of the box
   ([others](#choose-a-model) take one line).
4. *Recommended (Growth plan and up):* create a **Toolkit** with only read tools
   enabled and copy its MCP Remote Server URL. Without one, the agent sees
   every connection your PAT can reach.

## Deploy to Render

Click **Deploy to Render** above. Render prompts for:

| Service | Variable | Value |
| --- | --- | --- |
| both | `CDATA_USERNAME` | your Connect AI login email |
| both | `CDATA_PAT` | the Personal Access Token |
| agent | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | fill in the one for your provider, leave the other blank |
| digest | `SLACK_WEBHOOK_URL` | optional; blank skips Slack |

`APP_API_KEY`, the bearer token that protects the agent, is generated for you.

When the deploy finishes, open the agent's URL. The chat UI asks for
`APP_API_KEY` once; copy it from the web service's **Environment** tab.

To scope the agent to a Toolkit, set `CDATA_MCP_URL` in the `connectai-shared`
environment group to the Toolkit's URL.

## Run locally

You need Docker and the same credentials as above.

```bash
cp .env.example .env      # fill in CDATA_USERNAME, CDATA_PAT and an LLM key
docker compose up         # Postgres + agent, with hot reload
```

Open <http://localhost:8000> and enter `local-dev-key` (the `APP_API_KEY` in
`.env`). Edits under `app/` reload automatically.

Other commands:

```bash
docker compose run --rm digest    # run the cron job once
docker compose logs -f agent      # follow the agent's logs
docker compose exec db psql -U agent    # inspect the database
docker compose down               # stop; add -v to also wipe the database
```

<details>
<summary>No Docker on your Mac?</summary>

[Colima](https://github.com/abiosoft/colima) is a free, lightweight engine:

```bash
brew install colima docker docker-compose docker-buildx
colima start
```

Then add `"cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]` to
`~/.docker/config.json` so `docker compose` and `docker buildx` are found.
</details>

<details>
<summary>Without Docker for the app</summary>

Keep Postgres in Docker and run the app directly with Python 3.12:

```bash
docker compose up -d db
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --env-file .env
set -a; source .env; set +a; .venv/bin/python -m jobs.pipeline_digest
```
</details>

## Choose a model

`LLM_MODEL` takes any `provider:model` string that LangChain's
`init_chat_model` understands. OpenAI and Anthropic are installed:

| `LLM_MODEL` | Key |
| --- | --- |
| `openai:gpt-4o` (default) | `OPENAI_API_KEY` |
| `anthropic:claude-sonnet-5` | `ANTHROPIC_API_KEY` |

On Render, change `LLM_MODEL` in the `connectai-shared` environment group and
set the key on the web service. Locally, edit `.env`.

To add another provider, such as Google or Bedrock, add its `langchain-*`
package to `requirements.in`, regenerate `requirements.txt` (the command is at
the top of `requirements.in`), and add its key variable to `LLM_API_KEYS` in
`app/config.py` so a missing key is caught at startup.

## The pipeline digest (optional)

The cron job reads open Salesforce opportunities closing in the next 14 days,
stores a daily snapshot in Postgres for week-over-week trends, and optionally
posts a summary to Slack. It exists to show the SQL path into Connect AI
alongside MCP, and the agent works without it.

- **Salesforce:** it queries `[Salesforce1].[Salesforce].[Opportunity]`. If
  your connection has a different name, set `CDATA_SF_CATALOG` on the cron
  job's **Environment** tab.
- **Another source:** change `QUERY` in `jobs/pipeline_digest.py` to any
  `[Connection].[Schema].[Table]` your connections expose.
- **Not needed:** delete the cron service from `render.yaml`.

To test it on Render, open `connectai-pipeline-digest` and click **Trigger
Run**. The logs should show `Fetched N open opportunities`.

## Use the API

The chat UI is a thin client over a small API. `/docs` has interactive docs;
click **Authorize** and paste `APP_API_KEY`.

```bash
curl https://<your-service>.onrender.com/healthz
# {"status":"ok","mcp_tools":12,"llm_model":"openai:gpt-4o"}

curl -X POST https://<your-service>.onrender.com/chat \
  -H "Authorization: Bearer $APP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "What data sources can you reach?"}'
```

Send the returned `thread_id` back with follow-up messages to continue the
conversation.

## Troubleshooting

Startup and chat errors name the variable to fix. The common ones:

| Message | Fix |
| --- | --- |
| `Connect AI rejected the credentials (HTTP 401)` | `CDATA_USERNAME` must be your login email and `CDATA_PAT` a current token. Re-paste it; stray whitespace is stripped, but a truncated paste is not. |
| `LLM_MODEL=... needs OPENAI_API_KEY` | Set the key for your provider, or change `LLM_MODEL`. |
| `The LLM provider rejected the API key` | The LLM key is wrong or revoked. |
| `Could not connect to Postgres` | Locally, run `docker compose up -d db`. On Render, check `DATABASE_URL` is wired to the database. |
| `ended the session (Session terminated)` | `CDATA_MCP_URL` is wrong. Copy it from Connect AI again. |
| `No Connect AI connection named 'Salesforce1'` | Set `CDATA_SF_CATALOG` to your connection's name, as shown under **Sources**. |
| `mcp_tools: 0` in `/healthz` | The Toolkit has no tools enabled. |

The agent loads its tools at startup, so a PAT revoked after a deploy shows up
as a 502 on `/chat`. Redeploy once it is fixed.

## Design choices

**Security.** The agent reaches live enterprise data, so `/chat` requires a
bearer token that Render generates at deploy time. The system prompt tells the
agent not to write data without confirmation, but a prompt is a soft limit. The
real guardrail belongs in Connect AI: a Toolkit with only read tools enabled, or
a PAT for a read-only user.

**Conversation history lives in Postgres**, so chats survive redeploys. It
includes query results, so some source data lands in Render Postgres.

**Credentials are entered twice.** A Render environment group can't hold
prompted (`sync: false`) variables, so each service prompts for its own.

**Plans.** `render.yaml` sets none, so Render uses its defaults. Free web
instances spin down when idle, so use a paid plan for anything you demo live.
