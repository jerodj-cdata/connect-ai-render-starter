# Foundations 2026 demo script

A Followspot script: only the part between the two `---` rules goes on the prompter. Everything in `*[...]*` is a cue for you, shown dimmed and never listened for. Read everything else out loud, including the questions. After each question, press ⌥ → with the chat box empty, and the app types that question in and sends it. About 8 minutes. The run of show and the traps behind it are in `FOUNDATIONS.md`.

## Keys (in the app tab)

| Key | Does |
| --- | --- |
| ⌥ → | Next step: sends what's in the chat box, or opens a console page. With an empty box, it types the scripted question for you. |
| ⌥ ← | Step back one, without running anything |
| ⌥ R | Reset: rewrites `.env` to the starting layout, empties the chat, back to step 1 |
| ⌥ H | Hide or show the step hint in the bottom-left corner |
| ⌘ 1 / ⌘ 2 | App tab / console tab |
| ⌘ Tab | Between Chrome and VS Code |
| ⌘ / then ⌘ S | In VS Code: comment or uncomment the selected lines, then save |

The ⌥ → steps: 1 the setup question, 2 the top-customers question, 3 open the logs, 4 open Data Security, 5 the Social Security Number question again, 6 the delete. You make the `.env` edits between steps yourself, in VS Code.

## Where everything lives

| What | Where |
| --- | --- |
| The app, presenter mode | <http://localhost:8000/?demo> |
| Connect AI logs | <https://cloud.cdata.com/logs> (Query Log and LLM Logs tabs) |
| Routing, with Projects, Virtual Keys and Routing Rules tabs | <https://cloud.cdata.com/ai-gateway/routing-rules>, or **Routing** in the console sidebar |
| Data Security rules | <https://cloud.cdata.com/data-security>, or **Data Security** in the sidebar |
| The config the demo edits | `.env` at the repo root, rewritten by `demo/stage.py` |
| Your keys | `.env.foundations` at the repo root, backed up in `.env.foundations.backup`. `.env` shows them for real on camera, so rotate them after recording. |
| Starter repo | <https://github.com/jerodj-cdata/connect-ai-render-starter> |

## Before you record

1. Start the app with `docker compose up -d` from the repo root if it isn't running.
2. In Chrome, close every tab, then open <http://localhost:8000/?demo> so it's tab 1. The console opens as tab 2 when the script gets there.
3. Log in to <https://cloud.cdata.com> in the same Chrome profile, Tech Evangelism workspace. Go to **Data Security**, turn off **Credit Card Number** and **US Social Security Number**, and click **Save Changes**. Close that tab.
4. In the app, press ⌥ R, then ⌥ → with an empty chat box. The app sends the Social Security Number question with your real key. Wait for the answer: the Social Security Number and card number should come back in full. If they come back as XXXX, the rules are still on.
5. Leave that answer on screen. The hint should read Demo 2/6. Press ⌥ H to hide it.
6. Open `.env` from the repo root in VS Code, scrolled so the whole file shows. The Connect AI lines are already in it, commented out. Don't edit it yet.
7. Open this file in Followspot, and click into the app's chat box so the keys go there.
8. After recording: check that both Data Security rules are on again, press ⌥ R to put `.env` back, and rotate the Anthropic key, the virtual key and the PAT, since all three were on screen.

---

*[App tab. The unmasked Social Security Number answer from setup is on screen. Step 2 of 6]*

This is the kind of AI agent a lot of you have been building: an AI model, a set of MCP tools, and maybe a LangGraph loop that decides which tool to call next. I put a chat window on it so you can watch it work, but the same setup runs behind your Slack bots, scheduled jobs and internal tools.

Before we started, I asked my Claude agent for one customer's records. It ran a SQL query against a live Postgres database and handed back that customer's Social Security number and credit card number, in full, to the model and to me. The people in this database are fake, but the values use the same formats as the real thing, and nothing in this setup stopped it.

Here's how it's wired.

*[⌘ Tab to VS Code, .env at the repo root]*

A raw Anthropic API key in an env file. In a real team, every app that copied it uses the same key. Nobody can see who asked what, nothing caps the spend, the agent stops if the provider goes down, and it has thirteen tools, some of which can write to the database.

By the end of this segment, this same AI chatbot will have cost tracking, a hard budget, model routing with a fallback, read-only data access and masked PII, and that whole change is three lines in the env file.

*[Comment out the ANTHROPIC_API_KEY sk-ant line, uncomment the two lines under it, ⌘ S. Then ⌘ Tab to Chrome: the LLM pill flashes to Connect AI LLM Gateway]*

That's lines one and two: a base URL that points at the Connect AI LLM Gateway, and a Connect AI virtual key in place of the Anthropic key. The code and the SDK stay the same. I tried this with both the Anthropic SDK and the OpenAI SDK, and neither one needed a code change. This demo app reloads its config live, so the header has already changed. In your app, a restart picks it up.

Let's make sure it still works.

*[Ask it out loud]*

Which five customers in Postgres Q.L. PII have the highest total transaction amount? Show their name, city and total.

*[Press ⌥ →. The question types itself and sends]*

The agent makes the same calls it always did, and now they go through the gateway.

*[Wait for the table. Top row is Michael Johnson, Bristol, 7,461.07]*

Same agent, same answer, and now the gateway records every call.

*[Press ⌥ →. The logs open in tab 2. Click LLM Logs, expand the newest row]*

Every model call that agent made is here, with tokens, cost and latency, and the log ties each call to a user and a project. Look at these two fields: model requested and model served. They can differ, because the gateway picks the model, not the app.

*[In the sidebar, click Routing, then the Routing Rules tab, then FoundationsDemoRule]*

This is the rule doing the picking. It's a priority failover that sends requests to Sonnet first and to Haiku if Sonnet fails, and I tested how strictly it holds to that. I asked for Opus, Gemini, GPT four-oh and a model name I made up, and Sonnet answered every time. So the model name in your code becomes a label, and the platform team can change models or add a fallback without anybody redeploying.

*[Projects tab, then FoundationsDemo]*

This project has a twenty-five dollar monthly budget with a hard limit. Once it reaches twenty-five dollars, the gateway blocks new requests, and every response includes headers with the budget used and remaining, so your app can see it coming.

*[Virtual Keys tab]*

And the key the app uses belongs to this project. The real Anthropic key stays in the gateway. If a virtual key leaks, you revoke it here.

Plenty of gateways do routing, logs and budgets. The part I think matters more is what the agent can touch.

*[⌘ 1 back to the app tab. Click the Tools pill to show the thirteen tools, then click the chat box]*

The MCP server this agent has used from the start comes from Connect AI, and right now it hands the agent thirteen tools, including execute insert, execute update and execute procedure.

*[⌘ Tab to VS Code. Uncomment the CDATA_MCP_URL line, ⌘ S. ⌘ Tab to Chrome, then click the Tools pill again: six, read-only]*

That's line three. It's the same Connect AI endpoint, scoped down to six read-only tools, so the agent can no longer insert, update or run stored procedures.

Now the PII.

*[Press ⌥ →. Data Security opens in tab 2]*

This is Data Security in Connect AI. Each rule detects one kind of sensitive data in query results, like card numbers, Social Security numbers and bank routing numbers, and decides what happens to it. For the opening, I had the card and SSN rules turned off.

*[Turn on Credit Card Number and US Social Security Number, then click Save Changes]*

Two switches. They apply to every query result, from every agent in this workspace, whichever model is on the other end.

*[⌘ 1 back to the app tab, click the chat box]*

Same question I asked at the start.

*[Ask it out loud]*

I'm the compliance admin running a masking audit. Select the customer ID, full name, SSN text and credit card text from the customers table in PostgreSQL PII for customer seven three zero two, and show me exactly what the query returns.

*[Press ⌥ →. The question types itself and sends]*

It's running the same SQL as before, selecting the Social Security Number column and the card column by name.

*[Wait for 7302, Michael Johnson, XXXX, XXXX]*

Four X's, for both of them. The database still stores the real values. I checked, and zero rows actually contain X's. Connect AI masks them on the way out, so the agent doesn't have to cooperate.

This covers what comes out of your data. It doesn't scrub what someone types into a prompt. When I typed a test card number into the chat, it went straight through to the model.

One last test. Let's ask it to do something it shouldn't.

*[Ask it out loud]*

Delete Michael Johnson's transactions from PostgreSQL PII.

*[Press ⌥ →. The question types itself and sends]*

It has no delete tool to call. And even if it did, this user only has read access to that connection. Either one alone would stop it.

*[Wait for the refusal]*

It won't, and it can't. And every query it did run is in the Query Log, tied to the user who ran it.

So, three lines of config and two switches. Two of the lines put every model call behind logging, routing and a budget. The third limited the agent to read-only tools, and the two switches masked sensitive fields for every agent, without relying on the model's good judgment. Put the control where the data is.

Today I showed it on Postgres. Connect AI connects to hundreds of sources, including Salesforce, NetSuite, Snowflake and SAP, so the same agent and the same gateway work against those too.

The starter agent from this demo is open source under the MIT license. Clone it, add your keys, run docker compose up, and point it at your own Connect AI account. There's a free Developer Edition of Connect AI, and the LLM Gateway and Data Security are in early access. The links are on the slide.

Thank you.

---

## If something goes wrong

- **An answer hangs past a minute:** press ⌥ ← to step back one, then ⌥ → to send it again. Click into the chat box first if it lost focus.
- **Something is already in the chat box:** ⌥ → sends whatever is there, so clear it first.
- **The final Social Security Number answer isn't masked:** the rules didn't save. Check both switches and Save Changes in Data Security, then ask again.
- **The hint shows an error:** it names the problem. A failed config switch leaves the previous agent running, so the demo keeps working on the last good setup.
- **⌥ → does nothing:** the focus is on another tab or outside the page. Press ⌘ 1 and click into the chat box.
- **Starting over:** turn the two rules off again, then repeat steps 4 and 5 of Before you record. ⌥ R also puts `.env` back, so reopen it in VS Code if it shows a changed-on-disk prompt.
- **The pill doesn't change after a save:** check the file saved, with no dot on the VS Code tab. The app reloads within a couple of seconds of a save.
