# CData Connect AI + Render Starter

Deploy an AI agent with live, governed access to hundreds of enterprise systems,
plus a scheduled data job, in one click.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/jerodj-cdata/connect-ai-render-starter)

This Blueprint deploys three things:

- **`connectai-agent`** — a FastAPI + LangGraph agent whose tools come from
  Connect AI's remote MCP server.
- **`connectai-pipeline-digest`** — a weekday cron job that queries Salesforce
  live through the `cdata-connect-ai` Python connector (PEP 249).
- **`connectai-agent-db`** — Render Postgres for conversation history and
  daily pipeline snapshots.

So the repo shows both paths into Connect AI: MCP for agents, SQL for jobs.

## Before you deploy

1. In Connect AI, add a connection (e.g. Salesforce) under **Sources**.
2. Generate a Personal Access Token under **Settings**.
3. (Optional, Growth+) Create a **Toolkit** and copy its MCP Remote Server URL.

You'll also need an OpenAI API key, and optionally a Slack incoming webhook URL.

If your Salesforce connection isn't named `Salesforce1`, update
`CDATA_SF_CATALOG` in `render.yaml` before deploying.

## Deploy

In the Render dashboard, click **New** → **Blueprint**, pick this repo, and
click **Apply**. Render reads `render.yaml` and prompts for the secrets it
needs: `CDATA_USERNAME`, `CDATA_PAT` and `OPENAI_API_KEY` for the web service,
and `CDATA_USERNAME`, `CDATA_PAT` and `SLACK_WEBHOOK_URL` for the cron job.
`APP_API_KEY` is generated for you.

To scope the agent to a Toolkit, set `CDATA_MCP_URL` in the `connectai-shared`
environment group to your Toolkit URL.

## Try it

```bash
curl https://<your-service>.onrender.com/healthz
# expect {"status":"ok","mcp_tools": <some number > 0>}

curl -X POST https://<your-service>.onrender.com/chat \
  -H "Authorization: Bearer $APP_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message": "What are our 5 largest open opportunities?"}'
```

Reuse the returned `thread_id` in follow-up requests to continue the
conversation. `APP_API_KEY` is on the web service's **Environment** tab.

To test the cron job without waiting for the schedule, open
`connectai-pipeline-digest` and click **Trigger Run**, then check the logs for
`Fetched N open opportunities`.

## Design choices

**Security.** The agent reaches live enterprise data, so `/chat` requires a
bearer token that Render generates at deploy time. The system prompt tells the
agent not to write data without confirmation, but a prompt is a soft limit. The
real guardrail belongs in Connect AI: a Toolkit with only read tools enabled, or
a PAT for a read-only query user.

**Postgres serves two purposes.** It stores LangGraph's conversation history, so
chats survive redeploys, and it keeps a daily snapshot table for week-over-week
pipeline trends. One tradeoff: conversation history includes query results, so
some Salesforce data lands in Render Postgres.

**Credentials are entered twice.** A Render environment group can't hold
`sync: false` variables, so each service prompts for its own secrets.

## Status

Deployed and tested on Render against a live Connect AI account (September
2026):

- **Agent.** Boots, loads its tools from the default MCP endpoint
  (`https://mcp.cloud.cdata.com/mcp`), and answers questions over live data.
  Conversation history persists in Postgres across requests.
- **Pipeline digest.** A triggered run reads open opportunities through the
  Python connector and writes the daily snapshot to Postgres.
- **API docs.** `/` redirects to `/docs`, where **Authorize** takes the
  `APP_API_KEY` value so you can call `/chat` from the browser.

Not yet tested:

- **Toolkit URLs.** The default endpoint uses HTTP Basic auth with base64 of
  `email:PAT`. Whether Toolkit MCP URLs accept the same auth is unconfirmed.
- **Slack posting.** The tested runs had no `SLACK_WEBHOOK_URL` set.
- **Preview environments.** Render doesn't copy prompted secrets into previews,
  so set the Connect AI credentials by hand there.

Before you rely on it:

- **Pin package versions.** `requirements.txt` sets minimums only. Newer
  LangGraph releases prefer `langchain.agents.create_agent` over
  `create_react_agent`.
- **Pick plans.** `render.yaml` sets none, so Render uses its defaults. Put the
  web service on a paid plan for demos, because free instances idle out.

## Publishing

The **Deploy to Render** button at the top reads `render.yaml` from this repo
anonymously, so the repo has to stay public for it to work. When this moves to
the `CDataSoftware` org, repoint it:

```markdown
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/CDataSoftware/connect-ai-render-starter)
```
