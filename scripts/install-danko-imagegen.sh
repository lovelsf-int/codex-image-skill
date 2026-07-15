#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_command=""

for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
    && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    python_command="$(command -v "$candidate")"
    break
  fi
done

if [[ -z "$python_command" ]]; then
  echo "Python 3.10+ is required. Install Python, then rerun this installer." >&2
  exit 1
fi

venv_dir="$repo_root/.venv"
"$python_command" -m venv "$venv_dir"
venv_python="$venv_dir/bin/python"
"$venv_python" -m pip install -r "$repo_root/requirements.txt"

codex_home="${CODEX_HOME:-$HOME/.codex}"
"$venv_python" "$repo_root/scripts/write_mcp_config.py" \
  --config "$codex_home/config.toml" \
  --python "$venv_python" \
  --server "$repo_root/skills/third-party-imagegen/mcp_server/danko_imagegen_server.py" \
  --cwd "$repo_root"

echo "Danko ImageGen MCP installed. Restart Codex to load the updated configuration."
