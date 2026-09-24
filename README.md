# CData Connect AI + Render Starter

Deploy an AI agent with live, governed access to hundreds of enterprise systems,
plus a scheduled data job, in one click.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/jerodj-cdata/connect-ai-render-starter)

> **This button does not work yet.** Render has to read `render.yaml` from the
> repo anonymously, and this repo is private. Use **New → Blueprint** in the
> Render dashboard instead. The button starts working once a public copy exists.

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

Nothing here has been run end to end yet. Test these first:

- **Toolkit URL auth.** The default MCP endpoint uses HTTP Basic auth with
  base64 of `email:PAT`. Toolkit URLs are unconfirmed.
- **The Salesforce query.** Verify `IsClosed = false` and the `%(cutoff)s` date
  string behave as expected for your connection. `CloseDate` may come back as a
  datetime string that needs trimming.
- **Package versions.** `requirements.txt` uses minimums only. Pin exact
  versions once it runs. Newer LangGraph releases prefer
  `langchain.agents.create_agent` over `create_react_agent`.
- **Plans.** No compute plans are set, so Render uses defaults. For demos, put
  the web service on a paid plan — free instances idle out.
- **Preview environments.** Render doesn't copy prompted secrets into previews.

## Publishing

The **Deploy to Render** button at the top needs a public repo. When this moves
to the `CDataSoftware` org, repoint it and delete the warning note beneath it:

```markdown
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/CDataSoftware/connect-ai-render-starter)
```
