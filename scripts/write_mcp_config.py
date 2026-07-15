#!/usr/bin/env python3
"""Install or replace the managed Danko MCP block in a Codex config file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


BEGIN_MARKER = "# BEGIN DANKO_IMAGEGEN MCP"
END_MARKER = "# END DANKO_IMAGEGEN MCP"
SERVER_TABLE = "[mcp_servers.danko_imagegen]"
MANAGED_BLOCK = re.compile(
    rf"(?ms)^{re.escape(BEGIN_MARKER)}\r?\n.*?^{re.escape(END_MARKER)}\r?\n?"
)


def toml_string(value: str) -> str:
    return json.dumps(value)


def build_block(python: Path, server: Path, cwd: Path) -> str:
    env_vars = [
        "DANKOTOKEN_API_KEY",
        "DANKOTOKEN_BASE_URL",
        "DANKOTOKEN_ALLOW_CODEX_FALLBACK",
    ]
    return "\n".join(
        (
            BEGIN_MARKER,
            SERVER_TABLE,
            f"command = {toml_string(str(python))}",
            f"args = [{toml_string(str(server))}]",
            f"cwd = {toml_string(str(cwd))}",
            "env_vars = [" + ", ".join(toml_string(name) for name in env_vars) + "]",
            'default_tools_approval_mode = "writes"',
            END_MARKER,
            "",
        )
    )


def update_config(config: Path, block: str) -> None:
    content = config.read_text(encoding="utf-8") if config.exists() else ""
    if MANAGED_BLOCK.search(content):
        unmanaged_content = MANAGED_BLOCK.sub("", content)
        if re.search(r"(?m)^\[mcp_servers\.danko_imagegen\]\s*$", unmanaged_content):
            raise RuntimeError(
                f"{config} also contains {SERVER_TABLE} outside the managed installer block. "
                "Remove or migrate the unmanaged entry before rerunning."
            )
        content = MANAGED_BLOCK.sub(block, content)
    elif re.search(r"(?m)^\[mcp_servers\.danko_imagegen\]\s*$", content):
        raise RuntimeError(
            f"{config} already contains {SERVER_TABLE} outside the managed installer block. "
            "Remove that entry or migrate it into the managed block before rerunning."
        )
    else:
        if content and not content.endswith("\n"):
            content += "\n"
        if content:
            content += "\n"
        content += block

    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--server", required=True, type=Path)
    parser.add_argument("--cwd", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    update_config(args.config, build_block(args.python, args.server, args.cwd))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
