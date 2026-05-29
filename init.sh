#!/usr/bin/env bash
# milanka installer.
# Run once on a fresh Raspberry Pi after cloning the repo:
#     ./init.sh
#   or
#     bash init.sh
#
# What it does:
#   1. Creates ./venv and installs requirements.txt into it.
#   2. On a Raspberry Pi only: configures labwc to hide the cursor
#      (XCURSOR_SIZE=1 in ~/.config/labwc/environment).
#   3. On a Raspberry Pi only: installs / refreshes the systemd user service
#      that runs the app on every boot (delegates to service/service.sh).
#
# Then reboot the Pi:  sudo reboot
# Re-running is safe — every step is idempotent.

set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as a regular user (not root). The service installs into your user's systemd." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

VENV_DIR="venv"

# 1. Virtualenv + Python requirements
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment $VENV_DIR already exists."
fi

if [ -f requirements.txt ]; then
    echo "Installing dependencies from requirements.txt..."
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r requirements.txt
fi

# 2. Pi-only: labwc cursor config
needs_reboot=0
if [ -f /etc/rpi-issue ]; then
    LABWC_ENV="$HOME/.config/labwc/environment"
    mkdir -p "$(dirname "$LABWC_ENV")"
    if ! grep -qxF 'XCURSOR_SIZE=1' "$LABWC_ENV" 2>/dev/null; then
        echo "Configuring labwc to hide the cursor (XCURSOR_SIZE=1)..."
        echo 'XCURSOR_SIZE=1' >> "$LABWC_ENV"
        needs_reboot=1
    else
        echo "labwc cursor config already in place."
    fi
fi

# 3. Pi-only: systemd user service
if [ -f /etc/rpi-issue ] && [ -f service/service.sh ]; then
    echo "Installing / refreshing systemd user service..."
    bash service/service.sh
fi

echo
echo "Install complete."
if [ "$needs_reboot" = "1" ]; then
    echo "labwc configuration was updated. Reboot to apply: sudo reboot"
fi
