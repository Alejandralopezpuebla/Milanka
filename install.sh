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
#   3. On a Raspberry Pi only: cleans up cursor-hiding artefacts left by older
#      installer versions (XCURSOR_SIZE=1 in labwc/environment, and the
#      unclutter line in labwc/autostart). Cursor hiding is now done entirely
#      from the app — see SDL_VIDEODRIVER=x11 in service/milanka.service.
#   4. On a Raspberry Pi only: caps systemd-journald to 100 MB / 10 rotated
#      files via /etc/systemd/journald.conf.d/milanka.conf, so a multi-year
#      run can't slowly fill the SD card.
#   5. Ensures the videos/ folder exists, and (Pi only) creates two Desktop
#      shortcuts: a 'milanka-videos' symlink to the videos folder, and a
#      'Milanka Terminal' launcher that opens lxterminal in /opt/Milanka.
#   6. On a Raspberry Pi only: installs / refreshes the systemd user service
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

# 3. Pi-only: clean up cursor-hiding artefacts from older installer versions.
# Cursor hiding is now done by the app itself, via SDL_VIDEODRIVER=x11 in the
# systemd unit (forces Xwayland so labwc honors pygame's mouse-hide request).
# Note: `grep -v` returns 1 when every line matched and was filtered out;
# combined with set -e that would abort the whole installer, so each filtered
# write is guarded with `|| true`.
if [ -f /etc/rpi-issue ]; then
    LABWC_ENV="$HOME/.config/labwc/environment"
    if [ -f "$LABWC_ENV" ] && grep -qxF 'XCURSOR_SIZE=1' "$LABWC_ENV"; then
        echo "Removing stale XCURSOR_SIZE=1 from $LABWC_ENV..."
        grep -vxF 'XCURSOR_SIZE=1' "$LABWC_ENV" > "$LABWC_ENV.tmp" || true
        mv "$LABWC_ENV.tmp" "$LABWC_ENV"
    fi

    AUTOSTART="$HOME/.config/labwc/autostart"
    if [ -f "$AUTOSTART" ] && grep -q '^unclutter' "$AUTOSTART"; then
        echo "Removing stale unclutter line from $AUTOSTART..."
        grep -v '^unclutter' "$AUTOSTART" > "$AUTOSTART.tmp" || true
        mv "$AUTOSTART.tmp" "$AUTOSTART"
    fi
fi

# 4. Pi-only: cap systemd-journald disk usage to 100 MB / 10 rotated files so
# the SD card doesn't slowly fill up over a multi-year deployment, and we get
# fewer rotation events (less SD-card wear). Idempotent: only writes the
# drop-in and reloads journald if the file isn't already as we want it.
if [ -f /etc/rpi-issue ]; then
    JOURNALD_DROPIN=/etc/systemd/journald.conf.d/milanka.conf
    desired_journal_conf=$(cat <<'EOF'
[Journal]
SystemMaxUse=100M
SystemMaxFiles=10
EOF
)
    if [ ! -f "$JOURNALD_DROPIN" ] || ! diff -q <(printf '%s\n' "$desired_journal_conf") "$JOURNALD_DROPIN" >/dev/null 2>&1; then
        echo "Capping journald to 100 MB at $JOURNALD_DROPIN..."
        sudo mkdir -p "$(dirname "$JOURNALD_DROPIN")"
        printf '%s\n' "$desired_journal_conf" | sudo tee "$JOURNALD_DROPIN" >/dev/null
        sudo systemctl kill --kill-who=main --signal=SIGUSR2 systemd-journald 2>/dev/null || true
        sudo systemctl restart systemd-journald 2>/dev/null || true
    else
        echo "journald cap already in place."
    fi
fi

# 5. Videos folder + Desktop shortcuts (videos symlink + terminal launcher).
mkdir -p "$REPO_DIR/videos"
if [ -f /etc/rpi-issue ]; then
    DESKTOP_DIR="$HOME/Desktop"
    mkdir -p "$DESKTOP_DIR"

    # 5a. Videos folder symlink.
    LINK="$DESKTOP_DIR/milanka-videos"
    # ln -sfn: -s symlink, -f force replace, -n don't dereference if it's already a symlink to a dir.
    if [ ! -L "$LINK" ] || [ "$(readlink "$LINK")" != "$REPO_DIR/videos" ]; then
        echo "Creating Desktop shortcut: $LINK → $REPO_DIR/videos"
        ln -sfn "$REPO_DIR/videos" "$LINK"
    else
        echo "Desktop videos shortcut already in place."
    fi

    # 5b. Terminal launcher (opens lxterminal cd'd into the repo).
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

# 6. Pi-only: systemd user service
if [ -f /etc/rpi-issue ] && [ -f service/service.sh ]; then
    echo "Installing / refreshing systemd user service..."
    bash service/service.sh
fi

echo
echo "Install complete."
