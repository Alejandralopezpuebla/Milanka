"""Tunable constants for milanka. Edit values here, no logic elsewhere depends on them being elsewhere."""

import pathlib

# Sensor polling and screen state.
POLL_INTERVAL = 0.5            # seconds between PIR readings
HOLD_SECONDS = 3.0             # keep playing this long after the last detected motion
HOTPLUG_CHECK_INTERVAL = 3.0   # how often the parent re-checks the display list

# Power management.
IDLE_TIMEOUT_SECONDS = 60 * 60  # turn the display off after this many seconds of no motion
POWER_ON_DELAY_MS = 1500        # show black for this long after waking, before video

# Auto-update. Set to 0 to disable.
UPDATE_CHECK_INTERVAL = 3600    # seconds between `git fetch` checks (0 disables)

# Repo root (used for git operations and to resolve video.mp4).
REPO_DIR = pathlib.Path(__file__).resolve().parent.parent

# Video file shown on motion. If missing or unreadable, the app falls back to a
# red fullscreen with identical triggering. The videos/ folder is git-ignored
# (except for .gitkeep) so users can drop their own clips in without polluting
# the repo. init.sh creates a Desktop symlink to this folder on the Pi.
VIDEO_PATH = REPO_DIR / "videos" / "milanka.mp4"

# Display index → PIR pin (BCM numbering).
#   Display 0 ← PIR on GPIO 4  (physical pin 7)
#   Display 1 ← PIR on GPIO 17 (physical pin 11)
DISPLAY_PIN_MAP = {
    0: 4,
    1: 17,
}

# Display index → Wayland output name (for wlr-randr power control).
# Pi 4 with KMS uses HDMI-A-1 / HDMI-A-2 by default. Check `wlr-randr` on the
# Pi if power-off isn't working and adjust here.
DISPLAY_OUTPUT_NAMES = {
    0: "HDMI-A-1",
    1: "HDMI-A-2",
}

BLACK = (0, 0, 0)
RED = (255, 0, 0)
