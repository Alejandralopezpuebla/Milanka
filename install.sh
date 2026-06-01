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
#      after an idle period) and ydotool (used to warp the cursor to the
#      bottom-right corner — pygame.mouse.set_pos is a no-op on labwc/Wayland).
#   3. On a Raspberry Pi only: undoes the previously-added XCURSOR_SIZE=1 line
#      in ~/.config/labwc/environment, if present.
#   4. Ensures the videos/ folder exists, and (Pi only) creates two Desktop
#      shortcuts: a 'milanka-videos' symlink to the videos folder, and a
#      'Milanka Terminal' launcher that opens lxterminal in /opt/Milanka.
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

# 2. Pi-only: install wlr-randr (display power-off) and ydotool (cursor warping
# on Wayland — pygame's set_pos doesn't work on labwc because the compositor
# refuses client-side warp requests; ydotool injects at /dev/uinput instead).
if [ -f /etc/rpi-issue ]; then
    missing=()
    command -v wlr-randr >/dev/null 2>&1 || missing+=(wlr-randr)
    command -v ydotool   >/dev/null 2>&1 || missing+=(ydotool)
    if [ ${#missing[@]} -gt 0 ]; then
        echo "Installing: ${missing[*]} (sudo required)..."
        sudo apt-get update -qq
        sudo apt-get install -y "${missing[@]}"
    else
        echo "wlr-randr and ydotool already installed."
    fi

    # Run ydotoold as a system service so we can talk to it via the default
    # socket. Failure here is non-fatal — cursor will just stay where it is.
    if systemctl list-unit-files | grep -q '^ydotoold\.service'; then
        sudo systemctl enable --now ydotoold || true
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

# 4. Videos folder + Desktop shortcuts (videos symlink + terminal launcher).
mkdir -p "$REPO_DIR/videos"
if [ -f /etc/rpi-issue ]; then
    DESKTOP_DIR="$HOME/Desktop"
    mkdir -p "$DESKTOP_DIR"

    # 4a. Videos folder symlink.
    LINK="$DESKTOP_DIR/milanka-videos"
    # ln -sfn: -s symlink, -f force replace, -n don't dereference if it's already a symlink to a dir.
    if [ ! -L "$LINK" ] || [ "$(readlink "$LINK")" != "$REPO_DIR/videos" ]; then
        echo "Creating Desktop shortcut: $LINK → $REPO_DIR/videos"
        ln -sfn "$REPO_DIR/videos" "$LINK"
    else
        echo "Desktop videos shortcut already in place."
    fi

    # 4b. Terminal launcher (opens lxterminal cd'd into the repo).
    TERM_LAUNCHER="$DESKTOP_DIR/milanka-terminal.desktop"
    cat > "$TERM_LAUNCHER" <<EOF
[Desktop Entry]
Type=Application
Name=Milanka Terminal
Comment=Open a terminal in $REPO_DIR
Exec=lxterminal --working-directory=$REPO_DIR
Icon=utilities-terminal
Terminal=false
Categories=Utility;
EOF
    chmod +x "$TERM_LAUNCHER"
    echo "Wrote Desktop launcher: $TERM_LAUNCHER"
fi

# 5. Pi-only: systemd user service
if [ -f /etc/rpi-issue ] && [ -f service/service.sh ]; then
    echo "Installing / refreshing systemd user service..."
    bash service/service.sh
fi

echo
echo "Install complete."
