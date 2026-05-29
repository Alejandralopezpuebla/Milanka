#!/usr/bin/env bash
# milanka installer.
# Run once on a fresh Raspberry Pi after cloning the repo:
#     ./install.sh
#   or
#     bash install.sh
#
# What it does:
#   1. Creates ./venv and installs requirements.txt into it.
#   2. On a Raspberry Pi only: installs wlr-randr (used to power displays off
#      after an idle period).
#   3. On a Raspberry Pi only: undoes the previously-added XCURSOR_SIZE=1 line
#      in ~/.config/labwc/environment, if present.
#   4. Ensures the videos/ folder exists, and (Pi only) creates a Desktop
#      symlink so users can drop clips via the file manager.
#   5. On a Raspberry Pi only: installs / refreshes the systemd user service
#      that runs the app on every boot (delegates to service/service.sh).
#
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

# 2. Pi-only: ensure wlr-randr is installed (used for display power management).
if [ -f /etc/rpi-issue ]; then
    if ! command -v wlr-randr >/dev/null 2>&1; then
        echo "Installing wlr-randr (sudo required, used for screen power-off)..."
        sudo apt-get update -qq
        sudo apt-get install -y wlr-randr
    else
        echo "wlr-randr already installed."
    fi
fi

# 3. Pi-only: undo the previously-added XCURSOR_SIZE=1 line if it's still
# present from an older install. The app now lets the cursor stay visible.
if [ -f /etc/rpi-issue ]; then
    LABWC_ENV="$HOME/.config/labwc/environment"
    if [ -f "$LABWC_ENV" ] && grep -qxF 'XCURSOR_SIZE=1' "$LABWC_ENV"; then
        echo "Removing previously-added XCURSOR_SIZE=1 from $LABWC_ENV..."
        grep -vxF 'XCURSOR_SIZE=1' "$LABWC_ENV" > "$LABWC_ENV.tmp"
        mv "$LABWC_ENV.tmp" "$LABWC_ENV"
    fi
fi

# 4. Videos folder + Desktop shortcut.
mkdir -p "$REPO_DIR/videos"
if [ -f /etc/rpi-issue ]; then
    DESKTOP_DIR="$HOME/Desktop"
    mkdir -p "$DESKTOP_DIR"
    LINK="$DESKTOP_DIR/milanka-videos"
    # ln -sfn: -s symlink, -f force replace, -n don't dereference if it's already a symlink to a dir.
    if [ ! -L "$LINK" ] || [ "$(readlink "$LINK")" != "$REPO_DIR/videos" ]; then
        echo "Creating Desktop shortcut: $LINK → $REPO_DIR/videos"
        ln -sfn "$REPO_DIR/videos" "$LINK"
    else
        echo "Desktop shortcut already in place."
    fi
fi

# 5. Pi-only: systemd user service
if [ -f /etc/rpi-issue ] && [ -f service/service.sh ]; then
    echo "Installing / refreshing systemd user service..."
    bash service/service.sh
fi

echo
echo "Install complete."
