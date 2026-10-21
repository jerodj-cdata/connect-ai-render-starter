"""Drive the chat page in a real browser against the stub server.

Uses the installed Chrome when there is one, else Playwright's Chromium
(`playwright install chromium`). Every non-local request is blocked, which
proves the page needs no CDN.
"""
import os
import re
import socket
import subprocess
import sys
import time

import httpx
import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from tests.conftest import skip_or_fail  # noqa: E402

pytestmark = pytest.mark.ui
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "test-key"


def _serve(api_key):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.ui_server:app", "--port", str(port)],
        cwd=ROOT, env={**os.environ, "UI_STUB_API_KEY": api_key},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(f"{url}/healthz", timeout=0.5)
            return proc, url
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.kill()
    pytest.fail("stub server did not start")


@pytest.fixture(scope="module")
def open_server():
    proc, url = _serve("")
    yield url
    proc.kill()


@pytest.fixture(scope="module")
def keyed_server():
    proc, url = _serve(KEY)
    yield url
    proc.kill()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            try:
                b = p.chromium.launch()
            except Exception as exc:
                skip_or_fail(f"no browser available ({exc}); run `playwright install chromium`")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1100, "height": 760})
    block_the_internet(context)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    yield page
    context.close()
    assert not errors, f"JavaScript errors: {errors}"


def block_the_internet(context):
    context.route(re.compile(r"^https?://(?!127\.0\.0\.1)"), lambda route: route.abort())


def send(page, text):
    page.fill("#message", text)
    page.press("#message", "Enter")


# ---------- local mode: no APP_API_KEY ----------

def test_opens_straight_to_chat_without_a_key(page, open_server):
    page.goto(open_server)
    expect(page.locator("#chat-form")).to_be_visible()
    expect(page.locator("#key-form")).to_be_hidden()
    expect(page.locator("#change-key")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("4 Connect AI tools · openai:gpt-4o")


def test_reply_renders_markdown_and_strips_scripts(page, open_server):
    page.goto(open_server)
    send(page, "top deals?")
    expect(page.locator(".thinking")).to_be_visible()
    expect(page.locator(".bot table")).to_be_visible()
    expect(page.locator(".thinking")).to_have_count(0)
    expect(page.locator(".bot th")).to_have_count(3)
    expect(page.locator(".bot strong")).to_have_text("Two")
    expect(page.locator(".bot img[onerror]")).to_have_count(0)
    assert page.title() != "XSS"


def test_follow_ups_reuse_the_thread_and_new_chat_resets_it(page, open_server):
    page.goto(open_server)
    send(page, "first")
    expect(page.locator(".bot table")).to_be_visible()
    thread = page.evaluate("threadId")
    assert thread
    page.click("#new-chat")
    expect(page.locator("#intro")).to_be_visible()
    assert page.evaluate("threadId") is None


def test_suggestion_chip_sends_its_text(page, open_server):
    page.goto(open_server)
    page.click(".chips button >> nth=0")
    expect(page.locator(".user")).to_have_text("What data sources can you reach?")


def test_server_errors_are_shown_inline(page, open_server):
    page.goto(open_server)
    send(page, "please break")
    expect(page.locator(".error")).to_contain_text(
        "Error: The LLM provider rejected the API key for LLM_MODEL=openai:gpt-4o"
    )
    expect(page.locator(".thinking")).to_have_count(0)
    expect(page.locator("#send")).to_be_enabled()


def test_phone_width_has_no_horizontal_scroll(browser, open_server):
    context = browser.new_context(viewport={"width": 390, "height": 760}, color_scheme="dark")
    block_the_internet(context)
    page = context.new_page()
    page.goto(open_server)
    send(page, "top deals?")
    expect(page.locator(".bot table")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(21, 21, 28)"  # CData Depth
    context.close()


# ---------- deployed mode: APP_API_KEY set ----------

def test_asks_for_the_key_and_remembers_it(page, keyed_server):
    page.goto(keyed_server)
    expect(page.locator("#key-form")).to_be_visible()
    expect(page.locator("#chat-form")).to_be_hidden()
    page.fill("#key", KEY)
    page.press("#key", "Enter")
    send(page, "top deals?")
    expect(page.locator(".bot table")).to_be_visible()
    page.reload()
    expect(page.locator("#chat-form")).to_be_visible()


def test_a_rejected_key_asks_again(page, keyed_server):
    page.goto(keyed_server)
    page.fill("#key", "wrong")
    page.press("#key", "Enter")
    send(page, "hi")
    expect(page.locator(".error")).to_contain_text("That API key was rejected")
    expect(page.locator("#key-form")).to_be_visible()


# ---------- progress and SQL ----------

def test_steps_appear_live_then_fold_into_the_answer(page, open_server):
    page.goto(open_server)
    send(page, "top deals?")
    running = page.locator(".thinking .steps li")
    expect(running.first).to_have_text("Listing tables in Salesforce1")
    expect(page.locator(".thinking .elapsed")).to_contain_text("Working…")
    expect(page.locator(".thinking .steps li.ok")).to_have_count(1)  # first step finished
    expect(page.locator(".bot table")).to_be_visible()
    expect(page.locator(".thinking")).to_have_count(0)

    summary = page.locator(".trace summary")
    expect(summary).to_have_text(re.compile(r"^2 steps · 1 SQL query · \d+s$"))
    expect(page.locator(".trace .steps")).to_be_hidden()  # collapsed until clicked
    summary.click()
    expect(page.locator(".trace .steps li.ok")).to_have_count(2)
    from tests.ui_server import SQL
    expect(page.locator(".trace pre code")).to_have_text(SQL)


def test_failed_run_keeps_the_progress_it_made(page, open_server):
    page.goto(open_server)
    send(page, "please break")
    expect(page.locator(".thinking .steps li")).to_have_count(1)  # a step arrived first
    expect(page.locator(".error")).to_contain_text("Check OPENAI_API_KEY")


def test_sql_is_shown_as_text_never_html(page, open_server):
    from tests.ui_server import HOSTILE_SQL
    page.goto(open_server)
    send(page, "hostile query")
    expect(page.locator(".trace summary")).to_be_visible()
    page.click(".trace summary")
    expect(page.locator(".trace pre code")).to_have_text(HOSTILE_SQL)
    expect(page.locator(".trace img")).to_have_count(0)
    assert page.title() != "XSS-SQL"


# ---------- follow-up suggestions ----------

def test_followups_appear_and_can_be_clicked(page, open_server):
    from tests.ui_server import followups_for
    page.goto(open_server)
    send(page, "top deals?")
    chips = page.locator(".followups button")
    expect(chips).to_have_text(followups_for("top deals?"))
    chips.first.click()
    expect(page.locator(".user").last).to_have_text("More about top deals?")
    expect(page.locator(".followups")).to_have_count(0)  # cleared on the next question
    expect(page.locator(".followups button").first).to_have_text("More about More about top deals?")
    expect(page.locator(".followups")).to_have_count(1)  # only the latest answer has them


def test_you_can_type_before_suggestions_arrive(page, open_server):
    page.goto(open_server)
    send(page, "top deals?")
    expect(page.locator(".bot table")).to_be_visible()
    expect(page.locator("#send")).to_be_enabled()
    expect(page.locator(".followups")).to_have_count(0)  # still on their way


def test_a_new_question_discards_late_suggestions(page, open_server):
    from tests.ui_server import STEP_DELAY, SUGGEST_DELAY
    page.goto(open_server)
    send(page, "first")
    expect(page.locator(".bot table")).to_be_visible()
    send(page, "second")  # before the first answer's suggestions land
    # The first request finishes while the second is still running. It must
    # neither show its chips nor re-enable Send.
    page.wait_for_timeout(int((SUGGEST_DELAY + 0.2) * 1000))
    assert page.locator(".bot table").count() == 1  # second answer not here yet
    expect(page.locator("#send")).to_be_disabled()
    expect(page.locator(".followups")).to_have_count(0)
    expect(page.locator(".followups button").first).to_have_text("More about second",
                                                                  timeout=(4 * STEP_DELAY + SUGGEST_DELAY + 5) * 1000)


def test_suggestions_are_shown_as_text_never_html(page, open_server):
    # Suggestions are model output; the stub echoes the question into one.
    hostile = """<img src=x onerror="document.title='XSS-CHIP'">"""
    page.goto(open_server)
    send(page, hostile)
    expect(page.locator(".followups button").first).to_have_text(f"More about {hostile}")
    expect(page.locator(".followups img")).to_have_count(0)
    assert page.title() != "XSS-CHIP"


# ---------- branding ----------

REPO = "https://github.com/jerodj-cdata/connect-ai-render-starter"


def test_logos_and_fonts_load_offline(page, open_server):
    page.goto(open_server)
    expect(page.locator("#chat-form")).to_be_visible()
    page.wait_for_load_state("networkidle")
    # Every <img> decoded (naturalWidth > 0), with the internet blocked.
    broken = page.evaluate("""[...document.images]
        .filter((img) => !img.complete || img.naturalWidth === 0).map((img) => img.src)""")
    assert broken == []
    assert page.locator("header .brand img").get_attribute("src") == "/static/brand/cdata-logotype-white.svg"
    assert page.locator("link[rel=icon]").get_attribute("href") == "/static/brand/cdata-favicon.svg"
    assert page.evaluate("document.fonts.ready.then(() => document.fonts.check('15px \"DM Sans\"'))")
    fonts = page.evaluate("[...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family)")
    assert {'"DM Sans"', '"DM Mono"'} <= set(fonts) or {"DM Sans"} <= {f.strip('"') for f in fonts}


def test_footer_links(page, open_server):
    page.goto(open_server)
    links = page.eval_on_selector_all("footer a", "els => els.map((a) => [a.textContent.trim().replace(/\\s+/g, ' '), a.getAttribute('href')])")
    assert links == [
        ["Powered by Connect AI", "https://docs.cloud.cdata.com"],
        ["Deployed on Render", "https://render.com/docs"],
        ["Connect AI MCP", "https://docs.cloud.cdata.com/en/API/MCP"],
        ["Toolkits", "https://docs.cloud.cdata.com/en/Toolkits"],
        ["Render Blueprints", "https://render.com/docs/blueprint-spec"],
        ["API docs", "/docs"],
        ["Source", REPO],
        ["Report an issue", f"{REPO}/issues"],
    ]
    # External links open in a new tab without handing it window.opener.
    for a in page.locator("footer a[href^='http']").all():
        assert a.get_attribute("target") == "_blank" and "noopener" in a.get_attribute("rel")


def test_only_the_right_cdata_logo_shows_per_theme(browser, open_server):
    for scheme, visible in (("light", "depth"), ("dark", "clarity")):
        context = browser.new_context(color_scheme=scheme)
        block_the_internet(context)
        page = context.new_page()
        page.goto(open_server)
        shown = page.eval_on_selector_all(
            "footer img.cdata", "els => els.filter((e) => e.offsetParent).map((e) => e.getAttribute('src'))")
        assert shown == [f"/static/brand/cdata-logotype-{visible}.svg"], scheme
        context.close()


CONTRAST_JS = """() => {
  const lum = (c) => {
    const [r, g, b] = c.match(/[\\d.]+/g).slice(0, 3).map(Number).map((v) => {
      v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const bg = (el) => {  // first opaque background up the tree
    for (; el; el = el.parentElement) {
      const c = getComputedStyle(el).backgroundColor;
      if (!/rgba\\(.*, 0\\)$/.test(c) && c !== "transparent") return c;
    }
    return "rgb(255, 255, 255)";
  };
  const ratio = (el) => {
    const a = lum(getComputedStyle(el).color), b = lum(bg(el));
    return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  };
  const pick = {
    "body text": "#intro h2", "intro text": "#intro > div:not(.chips)",
    "header title": "header .product", "header status": "#status",
    "header button": "#new-chat", "send button": "#send", "suggestion chip": ".chips button",
    "footer text": ".credits a", "footer link": "footer nav a",
    "your message": ".user", "answer": ".bot:not(.thinking)", "step label": ".trace .steps li",
    "trace summary": ".trace summary", "follow-up chip": ".followups button",
  };
  return Object.fromEntries(Object.entries(pick).map(([k, sel]) => {
    const el = document.querySelector(sel);
    return [k, el ? Math.round(ratio(el) * 100) / 100 : null];
  }));
}"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_text_contrast_meets_wcag_aa(browser, open_server, scheme):
    context = browser.new_context(color_scheme=scheme)
    block_the_internet(context)
    page = context.new_page()
    page.goto(open_server)
    before = page.evaluate(CONTRAST_JS)  # intro, header, footer
    send(page, "top deals?")
    expect(page.locator(".followups button")).to_have_count(3)
    page.click(".trace summary")
    after = page.evaluate(CONTRAST_JS)  # messages, trace, chips
    context.close()
    # Each element exists in one snapshot or the other; keep whichever measured it.
    ratios = {k: after[k] if after[k] is not None else before[k] for k in before}
    ratios = {k: v for k, v in ratios.items() if v is not None}
    assert len(ratios) == 14, ratios
    low = {k: v for k, v in ratios.items() if v < 4.5}
    assert not low, f"{scheme}: below WCAG AA 4.5:1: {low} (all: {ratios})"
