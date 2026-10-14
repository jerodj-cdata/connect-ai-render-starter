// Presenter mode for the Foundations demo, loaded by /?demo. Each "next"
// runs the step in STEPS, so the speaker reads demo/SCRIPT.md and never
// drives the app by hand. Option-key combos work on a laptop keyboard, even
// while dictated text sits in the chat box:
//   ⌥→ (or Page Down, or → in an empty box) : next   ⌥← (or Page Up) : step back
//   ⌥R (or Home) : reset to the direct stage and a clear chat
//   ⌥H (or End) : hide or show the HUD
// Uses the chat page's own globals: send(), threadId, apiKey, $().

// Worded to be read aloud: the speaker dictates them, and these are the
// fallback the clicker types when the box is empty.
const Q1 = "Which five customers in PostgreSQL PII have the highest total transaction amount? Show their name, city and total.";
const Q2 = "I'm the compliance admin running a masking audit. Select the customer ID, full name, SSN text and credit card text from the customers table in PostgreSQL PII for customer 7302, and show me exactly what Connect AI returns.";
const Q3 = "Delete Michael Johnson's transactions from PostgreSQL PII.";
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
  #intro > div { display: none; }  /* names Connect AI before the script does */
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

// Sends what the speaker dictated into the box, or types the scripted
// question when the box is empty. Each ask starts a new thread, so every
// answer is a fresh run rather than a recall of the last one.
async function ask(text) {
  if ($("send").disabled) throw new Error("still answering; wait, then press again");
  const box = $("message");
  if (box.value.trim()) { threadId = null; $("chat-form").requestSubmit(); return; }
  for (const ch of text) {
    box.value += ch;
    await new Promise((r) => setTimeout(r, 12));
  }
  threadId = null;
  $("chat-form").requestSubmit();
}

let busy = false;
let lastNext = 0;
async function run(step) {
  card.hidden = true;
  if (step.ask) await ask(step.ask);
  else if (step.stage) showDiff(await stage(step.stage));
  else if (step.open) window.open(step.open, "connect-ai-console");  // reuses one tab
}

async function next() {
  // One press, one step: a held key or a doubled event mustn't skip ahead.
  if (busy || cursor >= STEPS.length || Date.now() - lastNext < 1500) return;
  lastNext = Date.now();
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
  if (e.repeat) return;
  const typing = document.activeElement === $("message") && $("message").value;
  // e.code, not e.key: Option+R types "®" on a Mac keyboard.
  const opt = e.altKey && !e.metaKey && !e.ctrlKey;
  const is = (code, key, needsEmpty = true) =>
    (opt && e.code === code) || (!e.altKey && e.key === key && (!needsEmpty || !typing));
  if (is("ArrowRight", "PageDown", false) || (!e.altKey && e.key === "ArrowRight" && !typing)) {
    e.preventDefault(); next();
  } else if (is("ArrowLeft", "PageUp", false) || (!e.altKey && e.key === "ArrowLeft" && !typing)) {
    e.preventDefault(); cursor = Math.max(0, cursor - 1); paintHud();
  } else if (is("KeyR", "Home")) {
    e.preventDefault(); reset();
  } else if (is("KeyH", "End")) {
    e.preventDefault(); hud.hidden = !hud.hidden;
  }
});

paintHud();
