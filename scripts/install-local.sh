#!/usr/bin/env bash
set -euo pipefail

# --- defaults (override via env vars or CLI flags) ---
install_root="${HYPRLAND_AGENT_INSTALL_ROOT:-"$HOME/.local/share/hyprland-agent"}"
bin_dir="${HYPRLAND_AGENT_BIN_DIR:-"$HOME/.local/bin"}"
skip_systemd="${HYPRLAND_AGENT_SKIP_SYSTEMD:-}"
prebuilt_wheel="${HYPRLAND_AGENT_WHEEL:-}"
python_ver="${HYPRLAND_AGENT_PYTHON:-}"

# --- CLI flag parsing ---
while [[ $# -gt 0 ]]; do
	case "$1" in
	--no-systemd)
		skip_systemd=1
		shift
		;;
	--bin-dir)
		bin_dir="$2"
		shift 2
		;;
	--install-root)
		install_root="$2"
		shift 2
		;;
	--python)
		python_ver="$2"
		shift 2
		;;
	--wheel)
		prebuilt_wheel="$2"
		shift 2
		;;
	--help | -h)
		cat <<'EOF'
Usage: install-local.sh [OPTIONS]

Options:
  --no-systemd         Skip systemd unit installation and daemon restart
  --bin-dir DIR        Symlink target directory (default: ~/.local/bin)
  --install-root DIR   Venv and constraints root (default: ~/.local/share/hyprland-agent)
  --python VERSION     Python version for uv venv (default: from pyproject.toml requires-python)
  --wheel PATH         Use a pre-built wheel instead of running uv build
  --help               Show this message

Environment variables (equivalent to flags):
  HYPRLAND_AGENT_INSTALL_ROOT   --install-root
  HYPRLAND_AGENT_BIN_DIR        --bin-dir
  HYPRLAND_AGENT_SKIP_SYSTEMD   --no-systemd  (any non-empty value)
  HYPRLAND_AGENT_PYTHON         --python
  HYPRLAND_AGENT_WHEEL          --wheel
EOF
		exit 0
		;;
	*)
		echo "Unknown option: $1" >&2
		exit 1
		;;
	esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_path="$install_root/venv"
unit_path="$HOME/.config/systemd/user/hyprland-agent.service"
wheel_dir="$repo_root/dist"
constraints_path="$install_root/constraints.txt"

# --- Python version: detect from pyproject.toml if not set ---
if [[ -z "$python_ver" ]]; then
	python_ver="$(grep 'requires-python' "$repo_root/pyproject.toml" |
		grep -oP '\d+\.\d+' | head -1)"
	python_ver="${python_ver:-3.13}"
fi

cd "$repo_root"

mkdir -p "$install_root" "$bin_dir" "$(dirname "$unit_path")"

# --- Build or use pre-built wheel ---
if [[ -n "$prebuilt_wheel" ]]; then
	wheel_path="$prebuilt_wheel"
else
	uv build --wheel --out-dir "$wheel_dir"
	wheel_path="$(find "$wheel_dir" -maxdepth 1 -name 'hyprland_agent-*.whl' \
		-printf '%T@ %p\n' | sort -nr | awk 'NR==1{print $2}')"
	if [[ -z "${wheel_path:-}" ]]; then
		echo "No hyprland-agent wheel found in $wheel_dir" >&2
		exit 1
	fi
fi

# --- Export constraints ---
uv export \
	--frozen \
	--no-dev \
	--no-emit-project \
	--no-hashes \
	--format requirements.txt \
	--output-file "$constraints_path" \
	>/dev/null

# --- Create venv if missing ---
if [[ ! -x "$venv_path/bin/python" ]]; then
	uv venv --python "$python_ver" "$venv_path"
fi

# --- Install wheel ---
uv pip install \
	--python "$venv_path/bin/python" \
	--constraint "$constraints_path" \
	--reinstall \
	"$wheel_path"

# --- Symlink project console scripts (from [project.scripts] in pyproject.toml) ---
mapfile -t script_names < <(
	awk '/^\[project\.scripts\]/{found=1;next} found && /^\[/{exit} found{print}' \
		"$repo_root/pyproject.toml" | grep -oP '^[a-z][a-z0-9-]+'
)
launcher_lines=()
for name in "${script_names[@]}"; do
	script_bin="$venv_path/bin/$name"
	link="$bin_dir/$name"
	if [[ ! -x "$script_bin" ]]; then
		echo "Warning: expected script not found in venv: $script_bin" >&2
		continue
	fi
	if [[ -e "$link" && ! -L "$link" ]]; then
		backup="$link.bak.$(date +%Y%m%d%H%M%S)"
		mv "$link" "$backup"
		echo "Backed up existing $name to $backup"
	fi
	ln -sfn "$script_bin" "$link"
	launcher_lines+=("Launcher:    $link -> $script_bin")
done

# --- Copy .env template if missing ---
env_dest="$HOME/.config/hyprland-agent/env"
if [[ ! -f "$env_dest" && -f "$repo_root/.env.example" ]]; then
	mkdir -p "$(dirname "$env_dest")"
	install -Dm600 "$repo_root/.env.example" "$env_dest"
	echo "Created template: $env_dest (edit before adding provider keys)"
fi

# --- Systemd: optional ---
if [[ -z "$skip_systemd" ]] && command -v systemctl &>/dev/null; then
	agent_launcher="$bin_dir/agent"
	cat >"$unit_path" <<UNIT
[Unit]
Description=Hyprland agent daemon
After=graphical-session.target
PartOf=graphical-session.target
ConditionEnvironment=HYPRLAND_INSTANCE_SIGNATURE

[Service]
Type=simple
ExecStart=$agent_launcher service start
Restart=on-failure
RestartSec=5
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin
EnvironmentFile=-%h/.config/hyprland-agent/env

[Install]
WantedBy=graphical-session.target
UNIT
	systemctl --user daemon-reload
	systemctl --user enable hyprland-agent.service
	systemctl --user restart hyprland-agent.service
	unit_line="Unit:        $unit_path"
else
	unit_line="Unit:        skipped (--no-systemd or systemctl unavailable)"
	echo "systemd skipped. Run manually: agent service start"
fi

# --- Summary ---
echo "Installed:   $wheel_path"
echo "Runtime:     $venv_path"
echo "Python:      $python_ver"
echo "Constraints: $constraints_path"
for line in "${launcher_lines[@]}"; do
	echo "$line"
done
echo "$unit_line"
