#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
install_root="${HYPRLAND_AGENT_INSTALL_ROOT:-"$HOME/.local/share/hyprland-agent"}"
venv_path="$install_root/venv"
bin_dir="$HOME/.local/bin"
launcher="$bin_dir/agent"
unit_path="$HOME/.config/systemd/user/hyprland-agent.service"
wheel_dir="$repo_root/dist"
constraints_path="$install_root/constraints.txt"

cd "$repo_root"

mkdir -p "$install_root" "$bin_dir" "$(dirname "$unit_path")"

uv build --wheel --out-dir "$wheel_dir"
wheel_path="$(find "$wheel_dir" -maxdepth 1 -name 'hyprland_agent-*.whl' -printf '%T@ %p\n' | sort -nr | awk 'NR == 1 {print $2}')"
if [[ -z "${wheel_path:-}" ]]; then
  echo "No hyprland-agent wheel produced in $wheel_dir" >&2
  exit 1
fi

uv export \
  --frozen \
  --no-dev \
  --no-emit-project \
  --no-hashes \
  --format requirements.txt \
  --output-file "$constraints_path" \
  >/dev/null

if [[ ! -x "$venv_path/bin/python" ]]; then
  uv venv --python 3.13 "$venv_path"
fi
uv pip install \
  --python "$venv_path/bin/python" \
  --constraint "$constraints_path" \
  --reinstall \
  "$wheel_path"

target="$venv_path/bin/agent"
if [[ -e "$launcher" && ! -L "$launcher" ]]; then
  backup="$launcher.bak.$(date +%Y%m%d%H%M%S)"
  mv "$launcher" "$backup"
  echo "Backed up existing launcher to $backup"
fi
ln -sfn "$target" "$launcher"

cat > "$unit_path" <<UNIT
[Unit]
Description=Hyprland agent daemon
After=graphical-session.target
PartOf=graphical-session.target
ConditionEnvironment=HYPRLAND_INSTANCE_SIGNATURE

[Service]
Type=simple
ExecStart=$launcher daemon
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

echo "Installed hyprland-agent from $wheel_path"
echo "Runtime venv: $venv_path"
echo "Constraints: $constraints_path"
echo "Launcher: $launcher -> $target"
echo "Unit: $unit_path"
