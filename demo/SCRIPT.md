# Foundations 2026 demo script

About 7 to 8 minutes. Read the plain text out loud. Every **[CLICK]** is one press of the presenter clicker (Page Down), and the app does the rest: it switches the config, types the question, and sends it. You never touch the keyboard. Lines in *italics* are stage directions, not things to say.

The run of show, the questions and the traps behind this script are in `FOUNDATIONS.md`.

## Before you go on

*Open `http://localhost:8000/?demo` full screen, and log in to `cloud.cdata.com` in the same browser (Tech Evangelism). Press **Home** once: the app resets to the direct act and clears the chat. The bottom-left corner should read "Demo 1/8". Press **End** to hide that hint if you don't want the room to see it; the clicker still works.*

*Run one warm-up question during setup so the first live answer isn't the slowest one, then press Home again.*

## 1. A normal agent (0:00)

So this is a pretty normal AI agent. It's a chat app on LangGraph, it calls Claude through the regular Anthropic API, and it reaches live data through Connect AI's MCP server. The header shows how it's wired up. It's on the Anthropic API with a provider key, running Claude Sonnet, with thirteen tools.

Let's ask it something real.

**[CLICK]** *(types and sends the top-customers question)*

While it works, watch the steps. It's not guessing. It's finding the connection, looking at the tables, checking the columns, and then writing SQL against a live Postgres database, right where the data sits.

*(Wait for the table. Top row: Michael Johnson, Bristol, 7,461.)*

There we go. Five customers with real totals, and if I open that trace I can see the exact SQL it ran.

That's fine on my laptop. Now picture it on a team. Each app carries its own Anthropic key. Nobody knows what it costs per team. And if we want to switch models, that's a code change and a redeploy.

## 2. The swap (1:30)

So let's move it onto the Connect AI gateway. Here's the whole change.

**[CLICK]** *(the .env diff appears top right, and the LLM pill flashes yellow)*

Two lines. A base URL that points at Connect AI, and the key goes from an Anthropic key to a Connect AI virtual key. That's it. Same code, same SDK. The Anthropic SDK already knows how to talk to a different base URL, and the OpenAI one does too, so this works with whatever you've already built.

And I didn't restart anything. The app picked up the new config on its own. Look at the header: we're on the Connect AI LLM Gateway now, with a virtual key.

Same question.

**[CLICK]** *(asks the top-customers question again)*

*(While it runs.)* The app's code is identical. It makes the exact same calls, and they go through the gateway now.

*(Wait for the table.)*

Same answer. Same Michael Johnson. So what did we actually get for those two lines?

## 3. What you got (2:45)

**[CLICK]** *(opens the Connect AI console in a second tab)*

*(Click the **LLM Logs** tab. Expand the newest row.)*

Every model call that agent made is here. Tokens, cost, how long it took. And it's attributed: this is the user, and this is the project it's billed to. That project has a twenty-five dollar monthly budget with a hard limit. A runaway agent stops at twenty-five dollars, not at the end of the month.

And check out these two fields: model requested, model served. The app asks for a model, but the routing rule on the gateway decides which one actually answers, with a failover chain behind it. So the platform team can change models, or add a fallback, without anybody redeploying the app.

*(Optional, if you're ahead on time: edit FoundationsDemoRule, move Haiku to the top, save, and ask a follow-up in the app. The Model pill shows "served claude-haiku-5-5." Put Sonnet back afterwards.)*

Now, a lot of gateways can do this part. Routing, logs, budgets, that's getting pretty standard. Here's what's different.

## 4. Governed access (4:15)

*(Switch back to the app tab.)*

Model calls are half of it. The other half is what the agent can touch. This agent has thirteen tools right now, and some of them write. So let's lock it down.

**[CLICK]** *(the diff shows the new CDATA_MCP_URL line; the Tools pill flips to "6 · read-only")*

One more line. Same MCP endpoint, scoped to six read-only tools. The insert, update and procedure tools are gone. And the app stayed up the whole time.

Now for some sensitive data. This Postgres database is full of synthetic customer records: names, Social Security numbers, card numbers. I'm going to play a compliance admin and ask for one customer's SSN and card number.

**[CLICK]** *(types and sends the masking audit)*

*(While it runs.)* The agent's running real SQL. It's selecting the SSN column and the card column directly. Nothing in the prompt is stopping it.

*(Wait for the result: `7302,Michael Johnson,XXXX,XXXX`.)*

XXXX. Both of them. And read what the model says: it can't tell where the masking happened. It doesn't know. It got the data back that way.

**[CLICK]** *(opens Data Security in the console tab)*

*(Switch to that tab.)*

Here's where it happened. Data Security in Connect AI. Credit card numbers get redacted. SSNs get redacted on the way out, and blocked on the way in. And the database actually stores the real values. These rules run in the platform on every query from every agent, whichever model is on the other end and whatever the prompt says.

That's the difference. You're relying on the data layer, not on the model being polite.

*(Switch back to the app tab.)*

One more. Let's ask it to do something it shouldn't.

**[CLICK]** *(asks it to delete Michael Johnson's transactions)*

*(While it runs.)* The agent has no delete tool to call, and this user only has read access to that connection anyway. So that's two layers.

*(Wait for the refusal.)*

It won't, and it can't. And every query it did run is in the Query Log with my name on it.

## Close (7:00)

So, recap. I changed two lines and got routing, failover, cost tracking and budgets on every model call. I changed one more and got governed, read-only access to live data, with PII masked by the platform, not by the prompt. And behind that same gateway are hundreds of connectors, Salesforce, NetSuite, Snowflake, SAP, with the same rules applied to every one.

You can try the agent from this demo yourself. It's open source, it runs with one `docker compose up`, and Connect AI is free for developers.

Thanks.

## If something goes wrong

- **An answer hangs past a minute:** say "live demos, right?", press **Page Up** to step back one, and press **[CLICK]** again to resend.
- **The HUD shows an error:** it names the problem. A failed config switch leaves the previous agent running, so the demo keeps working on the last good setup.
- **The venue network drops:** switch to the recorded backup run.
