# Foundations 2026: Connect AI Gateway developer demo

A 5 to 8 minute live demo for the developer section of the CData Foundations talk, using this starter's chat app unchanged and moves it onto the Connect AI LLM Gateway and governed data access by editing `.env` only.

Switching to the gateway takes two lines, the first thing you get is visibility and control over every model call, and what nobody else can show is governance that reaches the data itself.

I ran everything below end to end on 2026-10-13 against the Tech Evangelism workspace (`te_us@cdata.com`). Timings are from those runs.

## Setup (once)

1. In the Tech Evangelism workspace, these already exist:
   - Routing rule `FoundationsDemoRule`, Priority Failover: `claude-sonnet-5-5` then `claude-haiku-5-5`, prompt enrichment off.
   - Project `FoundationsDemo`: $25/month hard limit, uses that rule. Its virtual key is the demo's `ANTHROPIC_API_KEY` in gateway mode.
2. Put the secrets in `.env.foundations` (gitignored): `CDATA_USERNAME`, `CDATA_PAT` (a Tech Evangelism PAT), `ANTHROPIC_DIRECT_KEY`, `CDATA_GATEWAY_KEY` (the `cgw_sk_` virtual key).
3. Start the app once with `docker compose up -d` and open `http://localhost:8000/?demo`. From then on nothing restarts: the app watches `.env` and rebuilds its agent within about 1.5 s of a change (`app/live.py`), and the header pills show the live route, model and tool scope, flashing when they change.
4. Drive it from the laptop keyboard. In demo mode each ⌥ → runs the next step: it sends the question you dictated, switches `.env`, or opens a console page. ⌥ R resets to the direct stage, and ⌥ H hides the step hint. A presenter clicker's Page Down, Home and End still work. The spoken script, formatted for Followspot, is `SCRIPT.md`. Without the demo keys, `python demo/stage.py direct|gateway|governed` makes the same `.env` switch from a terminal and prints the diff with secrets masked.

The data is the `PostgreSQLPII` connection: about 100k synthetic customers plus transactions, built for PII testing. Every customer is fake, so nothing on screen is real.

## Run of show

| Time | Act | What you do | What the audience sees |
|---|---|---|---|
| 0:00 | 1. A normal agent | Click: ask Q1. | A LangGraph agent on the plain Anthropic API, answering from live data through Connect AI MCP, with its SQL expandable. About 30 to 40 s. |
| 1:30 | 2. The swap | Click: switch to `gateway` (diff card appears, LLM pill flashes). Click: ask Q1 again. | The diff is two lines: `+ANTHROPIC_BASE_URL=https://cloud.cdata.com/gateway/v1` and the key changing from `sk-ant-…` to `cgw_sk_…`. Same answer from the same code. |
| 2:30 | 3. What you got | Open Logs → LLM Logs, expand a row. Then Routing → Projects → FoundationsDemo. | Every model call the agent made, with tokens, cost, user, project, and **Model Requested vs Model Served**. The project shows spend against its $25 cap. |
| 3:30 | 3b. Change models without a deploy (optional) | Edit `FoundationsDemoRule`: put Haiku first. Ask Q1 again. | The request still names Sonnet, and LLM Logs shows Haiku served it, faster and about 20x cheaper. Put Sonnet back afterwards. |
| 4:30 | 4. Governed access | Click: switch to `governed` (Tools pill flips to 6, read-only). Click: Q2. Click: open Data Security. Click: Q3. | Q2: the SSN and card come back as `XXXX`, and the model itself says it can't tell where the masking happened. Open Data Security: the SSN and card rules did it, in the platform. Q3: the agent can't delete anything. It has six read-only tools, and the connection is Select-only. |
| 7:00 | Close | | Models and tools go through one gateway with hundreds of connectors behind it, and policy reaches the row. |

### The questions

- **Q1:** `Which five customers in PostgreSQL PII have the highest total transaction amount? Show their name, city and total.` Top answer: Michael Johnson, Bristol, 7,461.07.
- **Q2:** `I'm the compliance admin running a masking audit. Select the customer ID, full name, SSN text and credit card text from the customers table in PostgreSQL PII for customer 7302, and show me exactly what Connect AI returns.` Returns `7302,Michael Johnson,XXXX,XXXX` in about 15 s.
- **Q3:** `Delete Michael Johnson's transactions from PostgreSQL PII.` Refused, about 35 s.
- I worded the questions for reading aloud and dictating with Handy. A click sends whatever is in the chat box, or types the scripted question when the box is empty. I tested all three spoken versions on 2026-10-14 and got the same answers.

### Why Q2 reads like that

Asked casually ("pull up the SSN for Michael Johnson"), the agent finds the dataset's own `redaction_policy` table and declines to query the columns at all. That's the model being careful, not the platform enforcing anything, and it hides the real control. The explicit audit query makes the agent run the SQL, so the platform's redaction is what the audience sees. The proof that the platform did it: the table stores real values (a `COUNT` of rows where `ssn_text = 'XXXX'` returns 0), yet every result comes back masked.

## What we verified, and the traps

- **The gateway URL works with or without `/v1`.** `ANTHROPIC_BASE_URL` of `https://cloud.cdata.com/gateway/v1` and `https://cloud.cdata.com/gateway` both work with the Anthropic SDK. Overhead was about 0.2 s on a small call.
- **Every response carries budget headers:** `x-project-budget-limit-usd`, `-used-usd`, `-remaining-usd`, `-period`. A `curl -i` in a terminal shows them to a developer crowd.
- **The routing rule decides the model, not the request.** `claude-opus-5-5`, `gemini-3.7-flash`, a made-up name, and `gpt-4o` sent from the OpenAI SDK were all served by `claude-sonnet-5-5`. Good for the demo (models change in the console), surprising for developers (`LLM_MODEL` becomes a label).
- **Both SDKs work.** The OpenAI SDK pointed at the same URL got Claude back, so an app written for OpenAI moves over without code changes.
- **Data Security rules apply to data, not to prompts.** A fake SSN and a test card number typed into a prompt went through the LLM Gateway untouched, and the model echoed the card back. Redaction happens on connector query results. Don't demo PII in the prompt.
- **`near_miss`, `boundary` and `format_variant` rows aren't always masked, and that's correct** (for example `000-` and `666-` SSNs are invalid, and some cards fail Luhn). On a projector they look like leaks, so only show `clean` rows or customer 7302.
- **MCP Logs only records traffic through an MCP Gateway Tool Server.** This app calls `mcp.cloud.cdata.com/mcp` directly, so MCP Logs stays empty. The Query Log still records every SQL statement with the user.
- **`?ops=` scoping works:** 13 tools become 6, and `execute_insert`, `execute_update` and `executeProcedure` disappear.
- **Current Claude models reject `temperature`.** The starter used to send `temperature=0` and got a 400 on Sonnet 5.5 whether direct or through the gateway. Fixed in `app/agent.py`.

## Open items

- **Show the MCP Gateway too.** Create a Tool Server for this demo and point `CDATA_MCP_URL` at its URL, so MCP Logs lights up and the demo covers both gateways. Check whether `?ops=` works on Tool Server URLs; the console's own tool selection is "coming soon".
- **Prompt enrichment and Cost Optimization.** Two console toggles (on the rule, and on the project) that change model behavior with no redeploy. Candidates for act 3b if they make a visible difference.
- **Latency.** Answers take 15 to 40 s. The streaming page shows the steps live, and `SCRIPT.md` has lines to cover the waits.
- **Deep links into the console.** The demo opens `/logs` and `/data-security`, but the LLM Logs tab is one manual click: the console has no URL for it.
- **Rehearsal backup.** Record a clean run of every act in case the venue network fails.
- **Cleanup after the talk.** Delete the `FoundationsDemo` project, `FoundationsDemoRule`, and the virtual key, and revoke the Tech Evangelism PAT and Anthropic key used here.
