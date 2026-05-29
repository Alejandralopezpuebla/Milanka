#!/usr/bin/env bash
# One-shot installer for the milanka systemd user service.
# Run on the Pi as the user that owns the desktop session (typically 'milanka'):
#     bash service/service.sh
# It installs the unit into ~/.config/systemd/user/, enables it, and starts it.
# Re-run any time you want to refresh the unit file from the repo.

set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as a regular user (not root). User services live in your home, not the system." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_SRC="$REPO_DIR/service/milanka.service"
USER_UNIT_DIR="$HOME/.config/systemd/user"
TARGET="$USER_UNIT_DIR/milanka.service"

if [ ! -f "$SERVICE_SRC" ]; then
    echo "Cannot find unit file at $SERVICE_SRC" >&2
    exit 1
fi

if [ ! -x "$REPO_DIR/venv/bin/python" ]; then
    echo "Virtualenv not found at $REPO_DIR/venv. Run './install.sh' first." >&2
    exit 1
fi

mkdir -p "$USER_UNIT_DIR"
cp "$SERVICE_SRC" "$TARGET"
echo "Installed unit to $TARGET"

# Let the user systemd instance start at boot (under autologin) and survive logout.
loginctl enable-linger "$USER" >/dev/null 2>&1 || true

systemctl --user daemon-reload
systemctl --user enable milanka.service

# When the auto-updater calls install.sh from inside the running service it
# sets MILANKA_SKIP_SERVICE_RESTART=1 — restarting from here would SIGTERM our
# own running process mid-install. The auto-updater calls sys.exit(0) itself,
# and systemd's Restart=always picks the new unit up.
if [ "${MILANKA_SKIP_SERVICE_RESTART:-}" = "1" ]; then
    echo "MILANKA_SKIP_SERVICE_RESTART=1 set; skipping 'systemctl restart' (caller will exit)."
else
    systemctl --user restart milanka.service
fi

echo
echo "milanka.service installed, enabled, and running."
echo
echo "Useful commands:"
echo "  systemctl --user status milanka          # current state"
echo "  journalctl --user -u milanka -f          # follow logs"
echo "  systemctl --user restart milanka         # restart after edits"
echo "  systemctl --user stop milanka            # stop"
echo "  systemctl --user disable milanka         # remove from autostart"
