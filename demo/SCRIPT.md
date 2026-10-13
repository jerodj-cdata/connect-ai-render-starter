# Foundations 2026 demo script

About 7 to 8 minutes. Read the plain text out loud. Every **[CLICK]** is one press of the presenter clicker (Page Down), and the app does the rest: it switches the config, types the question, and sends it. You never touch the keyboard. Lines in *italics* are stage directions, not things to say.

The run of show, the questions and the traps behind this script are in `FOUNDATIONS.md`.

## Before you go on

*Open `http://localhost:8000/?demo` full screen, and log in to `cloud.cdata.com` in the same browser (Tech Evangelism). Press **Home** once: the app resets to the direct act and clears the chat. The bottom-left corner should read "Demo 1/8". Press **End** to hide that hint if you don't want the room to see it; the clicker still works.*

*Run one warm-up question during setup so the first live answer isn't the slowest one, then press Home again.*

## 1. A normal agent (0:00)

On screen is a working AI agent. It talks to Claude, and it queries live business data. Over the next few clicks, I'm going to change three lines of its config, and not one line of its code. When I'm done, every model call it makes will be tracked, budgeted and routed. And when it asks for a customer's Social Security number, it'll get back four X's.

Let's start with what it looks like today. It's a chat app built on LangGraph. It calls Claude through the regular Anthropic API, and it reaches live data through Connect AI's MCP server. You can see that in the header. Anthropic API, a provider key, Claude Sonnet, thirteen tools.

So let's ask it something real.

**[CLICK]** *(types and sends the top-customers question)*

Watch the steps while it works. It finds the connection, looks at the tables, checks the columns, and then writes SQL against a live Postgres database. The data stays where it is. Nothing gets copied into a warehouse first.

*(Wait for the table. Top row: Michael Johnson, Bristol, 7,461.)*

There we go. Five customers with real totals, and if I open the trace, there's the exact SQL it ran.

This is fine on one laptop. Now picture it across a team of fifty developers. Every app has its own Anthropic key in an env file somewhere. Nobody knows what it costs until the invoice arrives. And trying a different model means a code change and a redeploy.

## 2. The swap (1:30)

So let's put the Connect AI gateway in front of it. Here's the whole change.

**[CLICK]** *(the .env diff appears top right, and the LLM pill flashes yellow)*

That's two lines: a base URL that points at Connect AI, and a Connect AI virtual key in place of the Anthropic key. The code and the SDK stay the same. I tried this with both the Anthropic SDK and the OpenAI SDK, and neither one needed a code change.

And notice I didn't restart anything. The app picked up the new config on its own. The header now says Connect AI LLM Gateway, with a virtual key.

Same question.

**[CLICK]** *(asks the top-customers question again)*

*(While it runs.)* The app makes exactly the same calls it made a minute ago. They just go through the gateway now. When I measured it, the gateway added about two tenths of a second to a small call.

*(Wait for the table.)*

Same answer, same Michael Johnson. So what did those two lines get us?

## 3. What you got (2:45)

**[CLICK]** *(opens the Connect AI console in a second tab)*

*(Click the **LLM Logs** tab. Expand the newest row.)*

Every model call that agent made is here. Tokens, cost, and latency for each one. And each call is attributed to a user and to a project. This project has a twenty-five dollar monthly budget with a hard limit, so once it reaches twenty-five dollars, the gateway blocks new requests. Every response also carries headers with the budget used and remaining, so your app can see it coming.

Now look at these two fields. Model requested, and model served. They can differ, because the routing rule on the gateway picks the model, not the app. I tested this. I asked for Opus, for Gemini, for GPT-4o, and for a model name I made up. Sonnet answered every time, because that's what the rule says. So the model name in your code becomes a label, and the platform team can change models or add a fallback without anybody redeploying.

*(Optional, if you're ahead on time: edit FoundationsDemoRule, move Haiku to the top, save, and ask a follow-up in the app. The Model pill shows "served claude-haiku-5-5." Put Sonnet back afterwards.)*

Plenty of gateways do this part, and routing, logs and budgets are becoming standard. The part I think matters more is what the agent is allowed to touch.

## 4. Governed access (4:15)

*(Switch back to the app tab.)*

Model calls are half the problem. The other half is data. This agent has thirteen tools right now, and some of them can write. So let's lock it down.

**[CLICK]** *(the diff shows the new CDATA_MCP_URL line; the Tools pill flips to "6 · read-only")*

That's one more line. It's the same MCP endpoint, scoped down to six read-only tools, so insert, update and stored procedures are gone. And the app stayed up the whole time.

Now for sensitive data. This Postgres database holds synthetic customer records, with names, Social Security numbers and card numbers. The people are fake, but the data is formatted like the real thing.

One thing I found while building this. If you ask the agent casually for someone's SSN, it refuses on its own. It finds a policy table in the database and decides to follow it. That's the model choosing to be careful, and you can't count on that. So I'm going to play a compliance admin and tell it to run the query directly, which tests the platform instead.

**[CLICK]** *(types and sends the masking audit)*

*(While it runs.)* It's running real SQL, selecting the SSN column and the card column by name. Nothing in the prompt is holding it back.

*(Wait for the result: `7302,Michael Johnson,XXXX,XXXX`.)*

Four X's, for both of them. The agent ran the query, and the values came back masked.

*(If the answer says it can't tell where the masking happened, point at that line. It usually does, but it's model output, so it can vary.)*

From the model's side, the data simply came back that way.

**[CLICK]** *(opens Data Security in the console tab)*

*(Switch to that tab.)*

This is where the masking happened: Data Security in Connect AI. Card numbers and SSNs get redacted in query results. And the database stores the real values. I checked, and zero rows actually contain X's. These rules run on every query result, from every agent, whichever model is on the other end.

This covers what comes out of your data. It doesn't scrub what someone types into a prompt. When I typed a test card number into the chat, it went straight through to the model.

*(Switch back to the app tab.)*

One last test. Let's ask it to do something it shouldn't.

**[CLICK]** *(asks it to delete Michael Johnson's transactions)*

*(While it runs.)* It has no delete tool to call. And even if it did, this user only has read access to that connection. Either one alone would stop it.

*(Wait for the refusal.)*

It won't, and it can't. And every query it did run is in the Query Log, tied to the user who ran it.

## Close (7:00)

So, three lines of config. Two of them put every model call behind routing, logging and a budget. The third limited the agent to read-only tools on live data, with sensitive fields masked by the platform rather than by the model's good judgment. Politeness isn't a security model, so put the control where the data is.

Today I showed it on Postgres. Connect AI connects to hundreds of sources, including Salesforce, NetSuite, Snowflake and SAP, so the same agent and the same gateway work against those too.

The starter agent from this demo is open source under the MIT license. Clone it, add your keys, run `docker compose up`, and point it at your own Connect AI account. There's a free Developer Edition of Connect AI, and the LLM Gateway and Data Security are in early access. The links are on the slide.

Thank you.

## If something goes wrong

- **An answer hangs past a minute:** say "live demos, right?", press **Page Up** to step back one, and press **[CLICK]** again to resend.
- **The HUD shows an error:** it names the problem. A failed config switch leaves the previous agent running, so the demo keeps working on the last good setup.
- **The venue network drops:** switch to the recorded backup run.
