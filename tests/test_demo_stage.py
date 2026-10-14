"""demo/stage.py: the .env layout the VS Code swap edits, and what gets printed."""
import importlib.util
import pathlib

from dotenv import dotenv_values

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("demo_stage", ROOT / "demo" / "stage.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

SECRETS = {"CDATA_USERNAME": "u@example.com", "CDATA_PAT": "realpat123",
           "ANTHROPIC_DIRECT_KEY": "sk-ant-real", "CDATA_GATEWAY_KEY": "cgw_sk_real"}


def active(stage_name, tmp_path):
    env = tmp_path / ".env"
    env.write_text("\n".join(stage.build(stage_name, SECRETS)) + "\n")
    return dotenv_values(env)


def test_each_stage_is_the_same_file_with_lines_commented_in_or_out(tmp_path):
    direct = active("direct", tmp_path)
    assert direct["ANTHROPIC_API_KEY"] == "sk-ant-real" and "ANTHROPIC_BASE_URL" not in direct
    gateway = active("gateway", tmp_path)
    assert gateway["ANTHROPIC_API_KEY"] == "cgw_sk_real" and gateway["ANTHROPIC_BASE_URL"] == stage.GATEWAY_URL
    assert "CDATA_MCP_URL" not in gateway
    assert active("governed", tmp_path)["CDATA_MCP_URL"] == stage.READ_ONLY_MCP
    # Only comment markers move between stages, so the on-camera edit is ⌘/.
    strip = lambda name: [l.removeprefix("# ") for l in stage.build(name, SECRETS)]
    assert strip("direct") == strip("gateway") == strip("governed")


def test_printed_diff_masks_secrets_even_in_comments():
    assert stage._mask("CDATA_PAT=realpat123") == "CDATA_PAT=••••••••"
    assert stage._mask("+# ANTHROPIC_API_KEY=sk-ant-real") == "+# ANTHROPIC_API_KEY=sk-ant-…"
