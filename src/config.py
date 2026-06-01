"""Tunable constants for milanka. Edit values here, no logic elsewhere depends on them being elsewhere."""

import pathlib

# Sensor polling and screen state.
POLL_INTERVAL = 1.0             # seconds between PIR readings
HOLD_SECONDS = 9.0              # keep playing this long after the last detected motion
HOTPLUG_CHECK_INTERVAL = 3.0    # how often the parent re-checks the display list

# Per-poll PIR readings are logged only on state changes by default (keeps the
# journal small for long-running deployments). Set True to log every poll —
# useful when debugging the sensor or the state machine.
VERBOSE_LOGGING = False

# Power management.
IDLE_TIMEOUT_SECONDS = 60 * 60  # turn the display off after this many seconds of no motion
POWER_ON_DELAY_MS = 1500        # show black for this long after waking, before video

# Auto-update. Set to 0 to disable.
UPDATE_CHECK_INTERVAL = 300     # seconds between `git fetch` checks (0 disables)

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

# Fallback display-index → Wayland output name map. At runtime the app first
# discovers names by running `wlr-randr` and uses the Nth connected output for
# display index N — that handles "which HDMI port is the cable in" correctly,
# regardless of whether it's HDMI-A-1 (port nearer USB-C) or HDMI-A-2.
# This map is only consulted when wlr-randr is unreachable.
DISPLAY_OUTPUT_NAMES = {
    0: "HDMI-A-1",
    1: "HDMI-A-2",
}

BLACK = (0, 0, 0)
RED = (255, 0, 0)
