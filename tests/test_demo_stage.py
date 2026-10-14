"""demo/stage.py: what reaches the screen when the demo shows .env."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("demo_stage", ROOT / "demo" / "stage.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

SECRETS = {"CDATA_USERNAME": "u@example.com", "CDATA_PAT": "realpat123",
           "ANTHROPIC_DIRECT_KEY": "sk-ant-real", "CDATA_GATEWAY_KEY": "cgw_sk_real"}


def test_prerun_uses_the_real_key_and_direct_shows_the_fake_one():
    assert "ANTHROPIC_API_KEY=sk-ant-real" in stage.build("prerun", SECRETS)
    assert f"ANTHROPIC_API_KEY={stage.FAKE_KEY}" in stage.build("direct", SECRETS)


def test_masking_hides_the_pat_entirely_and_keeps_only_key_prefixes():
    assert stage._mask("CDATA_PAT=realpat123") == "CDATA_PAT=••••••••"
    assert stage._mask("+ANTHROPIC_API_KEY=cgw_sk_real") == "+ANTHROPIC_API_KEY=cgw_sk_…"
    assert stage._mask(f"ANTHROPIC_API_KEY={stage.FAKE_KEY}").endswith(stage.FAKE_KEY)


def test_switch_and_show(tmp_path, monkeypatch):
    env, secrets = tmp_path / ".env", tmp_path / ".env.foundations"
    secrets.write_text("\n".join(f"{k}={v}" for k, v in SECRETS.items()))
    monkeypatch.setattr(stage, "ENV", env)
    monkeypatch.setattr(stage, "SECRETS", secrets)
    stage.switch("direct")
    diff = stage.switch("gateway")
    assert f"-ANTHROPIC_API_KEY={stage.FAKE_KEY}" in diff
    assert "+ANTHROPIC_API_KEY=cgw_sk_…" in diff
    shown = "\n".join(stage.show())
    assert "realpat123" not in shown and "cgw_sk_real" not in shown
