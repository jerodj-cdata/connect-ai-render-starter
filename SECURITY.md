# Security policy

This starter gives an AI agent live access to enterprise data, so we take
reports about it seriously.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately instead:

1. Go to this repository's **Security** tab.
2. Click **Report a vulnerability** ([how private reporting works](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately)).
3. Describe the issue, how to reproduce it, and what an attacker could do.

We aim to acknowledge reports within five business days. Fixes land on
`main`; there are no separately maintained release branches.

## In scope

Problems in this repository's code and configuration, for example:

- Reaching `/chat` or `/tools` on a deployed service without `APP_API_KEY`
- The chat page rendering attacker-controlled HTML or script
- SQL injection through `CDATA_SF_CATALOG` or other settings
- Credentials leaking into logs, error messages, or API responses
- A `render.yaml` or `compose.yaml` default that exposes a service or secret

## Out of scope

- **CData Connect AI itself**, including its MCP server and API. Report those
  to CData through [Connect AI support](https://docs.cloud.cdata.com).
- **Your LLM provider**, Render, or other third-party services.
- **Prompt injection that stays within the agent's permissions.** The agent
  can do whatever its Connect AI credentials allow; limit that with a
  read-only Toolkit or a read-only user (see the README's
  [Design choices](README.md#design-choices)).

## If you leaked a credential

Revoke it first, then clean up:

- **Connect AI PAT:** delete it under **Settings** → **Access Tokens** in
  Connect AI, create a new one, and update `CDATA_PAT` on both Render services.
- **`APP_API_KEY`:** change it on the web service's **Environment** tab in
  Render.
- **LLM API key:** revoke it in your provider's console.

Removing a secret from git history does not un-leak it. Treat anything that
was pushed to a public repository as compromised.
