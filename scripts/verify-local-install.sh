#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
launcher="$HOME/.local/bin/agent"

if [[ ! -e "$launcher" ]]; then
  echo "missing launcher: $launcher" >&2
  exit 1
fi

launcher_target="$(readlink -f "$launcher")"
case "$launcher_target" in
  "$repo_root"/*)
    echo "launcher still points into repo: $launcher_target" >&2
    exit 1
    ;;
esac

venv_python="$(dirname "$launcher_target")/python"
agent_module="$("$venv_python" - <<'PY'
import agent
from pathlib import Path

print(Path(agent.__file__).resolve())
PY
)"
case "$agent_module" in
  "$repo_root"/*)
    echo "installed package still imports from repo: $agent_module" >&2
    exit 1
    ;;
esac

unit_exec="$(systemctl --user show hyprland-agent.service -p ExecStart --value)"
if [[ "$unit_exec" != *"$launcher daemon"* ]]; then
  echo "service ExecStart does not use $launcher: $unit_exec" >&2
  exit 1
fi

systemctl --user is-active --quiet hyprland-agent.service
"$launcher" status >/dev/null

echo "launcher: $launcher_target"
echo "module: $agent_module"
echo "service: active"
