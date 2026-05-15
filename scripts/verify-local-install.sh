#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bin_dir="${HYPRLAND_AGENT_BIN_DIR:-"$HOME/.local/bin"}"
unit_path="$HOME/.config/systemd/user/hyprland-agent.service"

# discover expected launchers from [project.scripts] in pyproject.toml
mapfile -t script_names < <(
	awk '/^\[project\.scripts\]/{found=1;next} found && /^\[/{exit} found{print}' \
		"$repo_root/pyproject.toml" | grep -oP '^[a-z][a-z0-9-]+'
)
if [[ ${#script_names[@]} -eq 0 ]]; then
	script_names=(agent agent-waybar fuzzel-agent)
fi

fail=0

for name in "${script_names[@]}"; do
	link="$bin_dir/$name"
	if [[ ! -e "$link" ]]; then
		echo "missing launcher: $link" >&2
		fail=1
		continue
	fi
	if [[ ! -L "$link" ]]; then
		echo "launcher is not a symlink: $link" >&2
		fail=1
		continue
	fi
	target="$(readlink -f "$link")"
	case "$target" in
	"$repo_root"/*)
		echo "$name still points into repo: $target" >&2
		fail=1
		;;
	*)
		echo "launcher[$name]: $target"
		;;
	esac
done

[[ $fail -ne 0 ]] && exit 1

# module origin check via the primary agent launcher
agent_bin="$bin_dir/agent"
agent_target="$(readlink -f "$agent_bin")"
venv_python="$(dirname "$agent_target")/python"
agent_module="$(
	"$venv_python" - <<'PY'
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

# systemd checks: skipped if unit file is absent (--no-systemd install)
if [[ -f "$unit_path" ]]; then
	unit_exec="$(systemctl --user show hyprland-agent.service -p ExecStart --value)"
	if [[ "$unit_exec" != *"$agent_bin service start"* ]]; then
		echo "service ExecStart does not use '$agent_bin service start': $unit_exec" >&2
		exit 1
	fi
	systemctl --user is-active --quiet hyprland-agent.service
	"$agent_bin" status >/dev/null
	echo "module:  $agent_module"
	echo "service: active"
else
	echo "module:  $agent_module"
	echo "service: skipped (unit file not present)"
fi
