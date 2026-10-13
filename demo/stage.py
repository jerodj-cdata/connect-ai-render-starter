"""Switch .env between the Foundations demo acts and show what changed.

    python demo/stage.py direct     # Act 1: the agent calls Anthropic directly
    python demo/stage.py gateway    # Act 2: same agent, models through Connect AI
    python demo/stage.py governed   # Act 4: gateway plus a read-only tool set

Secrets come from .env.foundations (gitignored). The diff printed after each
switch masks them, so it is safe to show on a projector. A running app sees
the new .env and rebuilds its agent within a second (see app/live.py).
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


STAGES = ("direct", "gateway", "governed")


def switch(stage: str) -> list[str]:
    """Rewrite .env for `stage` and return the changed lines, secrets masked.

    The chat page's demo mode calls this too (through the /demo/stage route),
    so a clicker press and the command line make the same change.
    """
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; use one of {', '.join(STAGES)}")
    if not SECRETS.exists():
        raise FileNotFoundError(f"Missing {SECRETS.name}: see demo/FOUNDATIONS.md, Setup")
    secrets = _read_env(SECRETS)
    missing = [k for k in ("CDATA_USERNAME", "CDATA_PAT", "ANTHROPIC_DIRECT_KEY",
                           "CDATA_GATEWAY_KEY") if not secrets.get(k)]
    if missing:
        raise ValueError(f"{SECRETS.name} is missing: {', '.join(missing)}")

    old = ENV.read_text().splitlines() if ENV.exists() else []
    new = build(stage, secrets)
    # Same file, rewritten in place: a replaced file would not show through
    # the container's mount.
    ENV.write_text("\n".join(new) + "\n")
    diff = difflib.unified_diff(old, new, ".env", ".env", lineterm="", n=0)
    return [_mask(line) for line in list(diff)[2:] if not line.startswith("@@")]


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
        sys.exit(f"usage: python demo/stage.py {{{','.join(STAGES)}}}")
    try:
        diff = switch(sys.argv[1])
    except (ValueError, FileNotFoundError) as exc:
        sys.exit(str(exc))
    ENV.chmod(0o600)
    print("\n".join(diff) if diff else ".env unchanged")
    print("\nThe running app picks this up within a second (docker compose up -d if it isn't running).")


if __name__ == "__main__":
    main()
