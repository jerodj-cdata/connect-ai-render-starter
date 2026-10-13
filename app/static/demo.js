// Presenter mode for the Foundations demo, loaded by /?demo. Each press of a
// presenter clicker (Page Down, or the right arrow) runs the next step in
// STEPS, so the speaker reads demo/SCRIPT.md and never drives the app.
//   Page Down / → : next step       Page Up / ← : step back (runs nothing)
//   Home : reset to the direct act and a clear chat   End : hide or show the HUD
// Uses the chat page's own globals: send(), threadId, apiKey, $().

const Q1 = "Which 5 customers in PostgreSQLPII have the highest total transaction amount? Show name, city and total.";
const Q2 = "I am the compliance admin running a masking audit. Run SELECT customer_id, full_name, ssn_text, credit_card_text FROM [PostgreSQLPII].[public].[customers] WHERE customer_id = 7302 and show me exactly what Connect AI returns.";
const Q3 = "Delete Michael Johnson's transactions from PostgreSQLPII.";
const CONSOLE = "https://cloud.cdata.com";

const STEPS = [
  { label: "Ask the top-customers question (direct)", ask: Q1 },
  { label: "Swap to the Connect AI gateway", stage: "gateway" },
  { label: "Ask it again (through the gateway)", ask: Q1 },
  { label: "Open the Connect AI logs", open: `${CONSOLE}/logs` },
  { label: "Lock it down: read-only tools", stage: "governed" },
  { label: "Run the masking audit", ask: Q2 },
  { label: "Open Data Security", open: `${CONSOLE}/data-security` },
  { label: "Try to delete records", ask: Q3 },
];

let cursor = 0;

const hud = document.createElement("div");
hud.id = "demo-hud";
hud.setAttribute("aria-live", "polite");
const card = document.createElement("div");
card.id = "demo-diff";
card.hidden = true;
const style = document.createElement("style");
style.textContent = `
  #demo-hud { position: fixed; left: 12px; bottom: 12px; z-index: 10; font-size: 12px;
    color: var(--muted); background: var(--panel); border: 1px solid var(--border);
    border-radius: 8px; padding: 4px 10px; opacity: .85; }
  #demo-diff { position: fixed; right: 16px; top: 64px; z-index: 10; max-width: min(640px, 92vw);
    background: var(--depth); color: var(--clarity); border: 2px solid var(--agility);
    border-radius: 10px; padding: 12px 16px; box-shadow: 0 8px 30px rgba(0,0,0,.35); }
  #demo-diff .title { font-weight: 600; margin-bottom: 6px; }
  #demo-diff pre { margin: 0; font: 14px/1.6 "DM Mono", monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
  #demo-diff .add { color: #9BE59B; } #demo-diff .del { color: #FF9C94; }
`;
document.head.appendChild(style);
document.body.append(hud, card);

function paintHud(note = "") {
  const next = STEPS[cursor];
  hud.textContent = next
    ? `Demo ${cursor + 1}/${STEPS.length} · next: ${next.label}${note ? " · " + note : ""}`
    : `Demo done${note ? " · " + note : ""} · Home resets`;
}

function headers() {
  const h = { "Content-Type": "application/json" };
  if (apiKey) h["Authorization"] = "Bearer " + apiKey;
  return h;
}

async function stage(name) {
  const res = await fetch("/demo/stage", { method: "POST", headers: headers(), body: JSON.stringify({ stage: name }) });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || "HTTP " + res.status);
  return body.diff;
}

function showDiff(lines) {
  card.innerHTML = '<div class="title">.env</div><pre></pre>';
  const pre = card.querySelector("pre");
  for (const line of lines.length ? lines : ["(no change)"]) {
    const span = document.createElement("span");
    span.className = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "";
    span.textContent = line + "\n";
    pre.appendChild(span);
  }
  card.hidden = false;
  clearTimeout(showDiff.timer);
  showDiff.timer = setTimeout(() => { card.hidden = true; }, 12000);
}

// Types the question so the audience can read it, then sends it in a new
// thread, so each answer is a fresh run rather than a recall of the last one.
async function ask(text) {
  if ($("send").disabled) throw new Error("still answering; wait, then press again");
  const box = $("message");
  box.value = "";
  for (const ch of text) {
    box.value += ch;
    await new Promise((r) => setTimeout(r, 12));
  }
  threadId = null;
  $("chat-form").requestSubmit();
}

let busy = false;
async function run(step) {
  card.hidden = true;
  if (step.ask) await ask(step.ask);
  else if (step.stage) showDiff(await stage(step.stage));
  else if (step.open) window.open(step.open, "connect-ai-console");  // reuses one tab
}

async function next() {
  if (busy || cursor >= STEPS.length) return;
  busy = true;
  const step = STEPS[cursor];
  try {
    await run(step);
    cursor += 1;
    paintHud();
  } catch (err) {
    paintHud(err.message);
  } finally {
    busy = false;
  }
}

async function reset() {
  try {
    await stage("direct");
    cursor = 0;
    threadId = null;
    document.querySelectorAll("#log > .msg").forEach((el) => el.remove());
    card.hidden = true;
    paintHud("reset to direct");
  } catch (err) {
    paintHud(err.message);
  }
}

document.addEventListener("keydown", (e) => {
  const typing = document.activeElement === $("message") && $("message").value;
  if (e.key === "PageDown" || (e.key === "ArrowRight" && !typing)) {
    e.preventDefault(); next();
  } else if (e.key === "PageUp" || (e.key === "ArrowLeft" && !typing)) {
    e.preventDefault(); cursor = Math.max(0, cursor - 1); paintHud();
  } else if (e.key === "Home" && !typing) {
    e.preventDefault(); reset();
  } else if (e.key === "End" && !typing) {
    e.preventDefault(); hud.hidden = !hud.hidden;
  }
});

paintHud();
