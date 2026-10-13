"""Switch .env between the Foundations demo acts and show what changed.

    python demo/stage.py direct     # Act 1: the agent calls Anthropic directly
    python demo/stage.py gateway    # Act 2: same agent, models through Connect AI
    python demo/stage.py governed   # Act 4: gateway plus a read-only tool set

Secrets come from .env.foundations (gitignored). The diff printed after each
switch masks them, so it is safe to show on a projector. Run
`docker compose up -d` afterwards: .env is only read when the container starts.
"""

import difflib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
SECRETS = ROOT / ".env.foundations"

GATEWAY_URL = "https://cloud.cdata.com/gateway/v1"
READ_ONLY_MCP = (
    "https://mcp.cloud.cdata.com/mcp"
    "?ops=get_catalogs,get_schemas,get_tables,get_columns,get_instructions,queryData"
)
SECRET_VARS = {"CDATA_PAT", "ANTHROPIC_API_KEY"}


def _read_env(path: pathlib.Path) -> dict[str, str]:
    pairs = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            pairs[key.strip()] = value.strip()
    return pairs


def build(stage: str, s: dict[str, str]) -> list[str]:
    lines = [
        f"CDATA_USERNAME={s['CDATA_USERNAME']}",
        f"CDATA_PAT={s['CDATA_PAT']}",
        "LLM_MODEL=anthropic:claude-sonnet-5-5",
    ]
    if stage == "direct":
        lines.append(f"ANTHROPIC_API_KEY={s['ANTHROPIC_DIRECT_KEY']}")
    else:
        lines += [
            f"ANTHROPIC_BASE_URL={GATEWAY_URL}",
            f"ANTHROPIC_API_KEY={s['CDATA_GATEWAY_KEY']}",
        ]
    if stage == "governed":
        lines.append(f"CDATA_MCP_URL={READ_ONLY_MCP}")
    lines.append("DATABASE_URL=postgresql://agent:agent@localhost:5432/agent")
    return lines


def _mask(line: str) -> str:
    key, _, value = line.partition("=")
    if key.lstrip("+- ") in SECRET_VARS and value:
        return f"{key}={value[:7]}…"
    return line


def main() -> None:
    stages = ("direct", "gateway", "governed")
    if len(sys.argv) != 2 or sys.argv[1] not in stages:
        sys.exit(f"usage: python demo/stage.py {{{','.join(stages)}}}")
    if not SECRETS.exists():
        sys.exit(f"Missing {SECRETS.name}: see demo/FOUNDATIONS.md, Setup")

    secrets = _read_env(SECRETS)
    missing = [k for k in ("CDATA_USERNAME", "CDATA_PAT", "ANTHROPIC_DIRECT_KEY",
                           "CDATA_GATEWAY_KEY") if not secrets.get(k)]
    if missing:
        sys.exit(f"{SECRETS.name} is missing: {', '.join(missing)}")

    old = ENV.read_text().splitlines() if ENV.exists() else []
    new = build(sys.argv[1], secrets)
    ENV.write_text("\n".join(new) + "\n")
    ENV.chmod(0o600)

    diff = [
        _mask(line)
        for line in difflib.unified_diff(old, new, ".env", ".env", lineterm="", n=0)
        if not line.startswith("@@")
    ]
    print("\n".join(diff[2:]) if diff else ".env unchanged")
    print("\nNow run: docker compose up -d")


if __name__ == "__main__":
    main()
