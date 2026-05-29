# milanka

A Python project for controlling Raspberry Pi GPIO pins.

## Connecting to the Raspberry Pi

The Pi was flashed with Raspberry Pi Imager and configured with hostname `milanka`, user `milanka`, Wi-Fi credentials,
and SSH enabled.

Connect over SSH from your machine:

```bash
ssh milanka@milanka.local
```

The `.local` suffix uses mDNS — no need to know the IP. If `milanka.local` does not resolve (e.g. on a network that
blocks mDNS), find the Pi's IP from your router and connect with `ssh milanka@<ip-address>` instead.

## Installation location on the Pi

The project lives at **`/opt/Milanka`** on the Raspberry Pi. It was cloned there with:

```bash
sudo git clone https://github.com/Alejandralopezpuebla/Milanka.git /opt/Milanka
sudo chown -R milanka:milanka /opt/Milanka
```

The `chown` hands ownership to the `milanka` user, so day-to-day `git pull` / edits don't need `sudo`.

To work on the project after SSH-ing in:

```bash
cd /opt/Milanka
```

## Install

One script does everything. On the Pi, from the repo root:

```bash
cd /opt/Milanka
./init.sh
sudo reboot
```

That's it. `init.sh` is idempotent — re-run it any time you bump dependencies, change the service unit, or want to
re-apply the labwc config.

### What `init.sh` does

1. **Creates `./venv` and installs `requirements.txt` into it.**
2. **(Pi only) Configures the cursor to be invisible** by appending `XCURSOR_SIZE=1` to `~/.config/labwc/environment`.
   Skipped on macOS / non-Pi machines.
3. **(Pi only) Installs the systemd user service** by running `service/service.sh`, which copies the unit to
   `~/.config/systemd/user/milanka.service`, calls `loginctl enable-linger`, and `enable`+`restart`s it.

After the reboot:

- The desktop auto-logs in.
- The systemd user service starts the app within a few seconds.
- Both displays go black; PIRs control them edge-to-edge.

### Video on motion

Place a `video.mp4` in the repo root. When a PIR fires, the matching display switches from black to playing the video on
a loop. When motion stops for `HOLD_SECONDS`, the screen returns to black; the next motion event restarts the video from
frame 0.

If `video.mp4` is missing (or unreadable), the app falls back to the original red-screen behavior — same triggering,
just a flat red fullscreen instead of video.

To swap the video, drop a new file at `/opt/Milanka/video.mp4` and restart the service:

```bash
systemctl --user restart milanka
```

### Power saving

After `IDLE_TIMEOUT_SECONDS` of no motion (default 60 minutes) each display is powered off via
`wlr-randr --output … --off`. The next motion event powers it back on, shows black for `POWER_ON_DELAY_MS` (default 1500
ms) so the monitor can finish its handshake, and then starts the video.

The display-index → output-name mapping is `DISPLAY_OUTPUT_NAMES` in `src/main.py`. Default is `HDMI-A-1` / `HDMI-A-2` (
Pi 4 with KMS). Run `wlr-randr` on the Pi to confirm the names if power-off isn't working.

If `wlr-randr` isn't installed, the app skips power management and logs a notice — the rest still works.

### Developing on macOS / non-Pi

`init.sh` still works — steps 2 and 3 are skipped automatically (`/etc/rpi-issue` doesn't exist), so you just get a
working `venv/` for editing code. To run the script locally for tests, activate the venv yourself:

```bash
./init.sh
source venv/bin/activate
python src/main.py    # will fail on import RPi.GPIO unless you mock it
```

## Run on boot (systemd user service)

`init.sh` already installs this; this section is reference for what the service does and how to manage it after install.

### Managing it afterwards

```bash
systemctl --user status milanka          # current state
journalctl --user -u milanka -f          # follow logs (PIR readings, etc.)
systemctl --user restart milanka         # restart, e.g. after editing main.py
systemctl --user stop milanka            # stop without disabling
systemctl --user disable milanka         # disable autostart
```

To pick up changes to `milanka.service` itself, re-run `bash service/service.sh`.

### Why a user service (and not a system one)

A system-level service runs as `root` before any desktop session exists, so it has no `DISPLAY`, no `XAUTHORITY`, no
path to the screen. Working around that means writing `xhost` permissions, hardcoding paths to `.Xauthority`, and racing
the desktop's startup. A **user** service runs inside the logged-in graphical session, so all of that is set up
correctly out of the box.

A simpler alternative would be an XDG autostart entry (`~/.config/autostart/milanka.desktop`), but it gives no
auto-restart on crash and no proper logging.

## Project structure

```
milanka/
├── src/
│   └── main.py          # Entry point
├── service/
│   ├── milanka.service  # systemd user unit
│   └── service.sh       # one-shot installer for the service
├── init.sh              # Install / configure (venv, labwc, service)
├── requirements.txt     # Python dependencies
├── video.mp4            # Optional — played on motion (falls back to red if absent)
├── .gitignore
└── README.md
```
