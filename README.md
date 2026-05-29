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
./install.sh
sudo reboot
```

That's it. `install.sh` is idempotent — re-run it any time you bump dependencies, change the service unit, or just
want to confirm the Pi is in the expected state.

### What `install.sh` does

1. **Creates `./venv` and installs `requirements.txt` into it.** Runs everywhere.
2. **(Pi only) Installs `wlr-randr`** via apt, used by the app to power displays off after idle.
3. **(Pi only) Removes a stale `XCURSOR_SIZE=1` line** from `~/.config/labwc/environment` if a previous version of
   this installer left one there. The app now lets the cursor stay visible (needed for the windowed-mode introduced
   with ESC), so this earlier hack is no longer wanted.
4. **Ensures `videos/` exists**, and **(Pi only) creates a Desktop shortcut** named `milanka-videos` pointing at the
   folder so clips can be dropped in via the file manager.
5. **(Pi only) Installs / refreshes the systemd user service** by running `service/service.sh`, which copies the unit
   to `~/.config/systemd/user/milanka.service`, calls `loginctl enable-linger`, runs `daemon-reload`+`enable`, and
   restarts the service (unless `MILANKA_SKIP_SERVICE_RESTART=1` is set — used by the auto-updater).

After the reboot:

- The desktop auto-logs in.
- The systemd user service starts the app within a few seconds.
- Both displays go black; PIRs control them edge-to-edge.

### Video on motion

The app expects `videos/milanka.mp4` in the repo (so `/opt/Milanka/videos/milanka.mp4` on the Pi). When a PIR fires,
the matching display switches from black to playing the video on a loop. When motion stops for `HOLD_SECONDS`, the
screen returns to black; the next motion event restarts the video from frame 0.

If `videos/milanka.mp4` is missing or unreadable, the app falls back to red-screen behavior — same triggering, just a
flat red fullscreen instead of video.

#### Swapping the video on the Pi

`install.sh` creates a Desktop shortcut named **`milanka-videos`** pointing to the videos folder. Double-click it from
the Pi's desktop to open the folder in the file manager, then drag your new clip in, renaming it to `milanka.mp4`
(replacing the existing one if any). Restart the service for the new video to be picked up:

```bash
systemctl --user restart milanka
```

#### Why `videos/` is git-ignored

The folder itself is tracked (via an empty `.gitkeep` placeholder), but everything inside it is excluded by
`.gitignore` — large `.mp4` files shouldn't bloat the repository. That means `git pull` won't overwrite or remove the
clip you've dropped in.

### Power saving

After `IDLE_TIMEOUT_SECONDS` of no motion (default 60 minutes) each display is powered off via
`wlr-randr --output … --off`. The next motion event powers it back on, shows black for `POWER_ON_DELAY_MS` (default 1500
ms) so the monitor can finish its handshake, and then starts the video.

The display-index → output-name mapping is `DISPLAY_OUTPUT_NAMES` in `src/config.py`. Default is `HDMI-A-1` / `HDMI-A-2`
(Pi 4 with KMS). Run `wlr-randr` on the Pi to confirm the names if power-off isn't working.

If `wlr-randr` isn't installed, the app skips power management and logs a notice — the rest still works.

### Keyboard

- **ESC** — switch the display from fullscreen to a 640×480 window with an overlay reading
  `Exit the application (Ctrl+Q) to restart and enter fullscreen mode`. The motion → video/red logic keeps running
  inside the small window. There's no way back to fullscreen except by exiting the subprocess (which systemd restarts
  in fullscreen).
- **Q** / **Ctrl+Q** — exit the subprocess. With `Restart=always` on the unit, systemd will restart the service within
  a few seconds, re-entering fullscreen.

### Auto-update

Every `UPDATE_CHECK_INTERVAL` seconds (default 3600 = 1 hour) the parent process runs `git fetch`. If the upstream
branch has new commits, it does `git pull --ff-only`, then re-runs `install.sh` to pick up any new dependencies or
unit-file changes, and finally exits — systemd then restarts the service with the new code (thanks to `Restart=always`
in the unit).

To avoid SIGTERM-ing the running service while `install.sh` is still working, the auto-updater sets
`MILANKA_SKIP_SERVICE_RESTART=1` in `install.sh`'s env. The downstream `service/service.sh` notices the flag and skips
its own `systemctl --user restart`, leaving the restart to happen via the auto-updater's clean `sys.exit(0)`.

If there's no internet, the fetch fails silently and the loop keeps running; the next check happens an hour later.
Local edits that block a fast-forward (uncommitted changes or diverged history) cause the pull to fail loudly in the
journal; the service keeps running on the old code until the conflict is resolved. To disable auto-update entirely,
set `UPDATE_CHECK_INTERVAL = 0` in `src/config.py`.

### Developing on macOS / non-Pi

`install.sh` still works — all the Pi-only steps are skipped automatically (the script checks for `/etc/rpi-issue`),
so you just get a working `venv/` and an empty `videos/` folder. To run the script locally for tests, activate the
venv yourself:

```bash
./install.sh
source venv/bin/activate
python src/main.py    # will fail on import RPi.GPIO unless you mock it
```

## Run on boot (systemd user service)

`install.sh` already installs this; this section is reference for what the service does and how to manage it after
install.

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
│   ├── config.py        # Tunable constants (pins, timing, paths, colors)
│   ├── display.py       # Per-display subprocess: motion → video/red, power off/on
│   └── main.py          # Orchestrator: hot-plug watcher, signal handling
├── service/
│   ├── milanka.service  # systemd user unit
│   └── service.sh       # one-shot installer for the service
├── videos/              # Drop milanka.mp4 here (git-ignored, except for .gitkeep)
│   └── .gitkeep
├── install.sh           # Install / configure (venv, wlr-randr, videos symlink, service)
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```
