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
```

That's it. The service starts right at the end of the script — no reboot needed. `install.sh` is idempotent — re-run
it any time you bump dependencies, change the service unit, or just want to confirm the Pi is in the expected state.

### What `install.sh` does

1. **Creates `./venv` and installs `requirements.txt` into it.** Runs everywhere.
2. **(Pi only) Installs `wlr-randr`** via apt, used by the app to power displays off after idle.
3. **(Pi only) Cleans up cursor-hiding leftovers** from older installer versions (`XCURSOR_SIZE=1` in
   `~/.config/labwc/environment`, and any `unclutter` line in `~/.config/labwc/autostart`). The cursor is now
   hidden entirely from the app: the systemd unit sets `SDL_VIDEODRIVER=x11` to force pygame through Xwayland,
   which labwc honors when the app calls `pygame.mouse.set_visible(False)`.
4. **(Pi only) Caps `systemd-journald`** to 100 MB / 10 rotated files via a drop-in at
   `/etc/systemd/journald.conf.d/milanka.conf`. Prevents the SD card from slowly filling over multi-year runs.
5. **Ensures `videos/` exists**, and **(Pi only) writes two Desktop shortcuts**:
   - `milanka-videos` — a symlink to the videos folder, so clips can be dropped in via the file manager.
   - `Milanka Terminal` — a launcher that opens `lxterminal` already `cd`'d into `/opt/Milanka`, handy for running
     `git pull`, `sudo journalctl _SYSTEMD_USER_UNIT=milanka.service`, etc. without typing the path.
6. **(Pi only) Installs / refreshes the systemd user service** by running `service/service.sh`, which copies the unit
   to `~/.config/systemd/user/milanka.service`, calls `loginctl enable-linger`, runs `daemon-reload`+`enable`, and
   restarts the service (unless `MILANKA_SKIP_SERVICE_RESTART=1` is set — used by the auto-updater).

After install (and on every boot from then on):

- The desktop auto-logs in.
- The systemd user service starts the app within a few seconds.
- Both displays go black; PIRs control them edge-to-edge.

### Video on motion

The app expects `videos/milanka.mp4` in the repo (so `/opt/Milanka/videos/milanka.mp4` on the Pi). When a PIR fires,
the matching display switches from black to playing the video. What happens next depends on `PLAY_FULL_VIDEO` in
`src/config.py`:

- `PLAY_FULL_VIDEO = True` (default, "full-clip" mode): the clip always plays through to the end, even if motion
  stops mid-clip. When it finishes, the screen returns to black; the next motion detected *after* that starts the
  clip again from frame 0.
- `PLAY_FULL_VIDEO = False` ("hold" mode): the video plays on a loop while motion continues and stops `HOLD_SECONDS`
  after the last detection; the next motion event restarts it from frame 0.

If the clip has an audio track and `ffmpeg` is installed, the **primary display (index 0)** also plays the sound along
with the video — once per run in full-clip mode, looping in hold mode (extracted from the clip with `ffmpeg`, and re-extracted automatically if you swap the clip at
runtime — see below). Only display 0 plays audio so two displays don't fight over the single output or drift out of
sync; without `ffmpeg`, or for a silent clip, playback is silent.

If `videos/milanka.mp4` is missing or unreadable, the app falls back to red-screen behavior — same triggering, just a
flat red fullscreen instead of video. The red screen has no natural end, so it always uses the hold behavior
(`HOLD_SECONDS`) regardless of `PLAY_FULL_VIDEO`.

#### Swapping the video on the Pi

`install.sh` creates a Desktop shortcut named **`milanka-videos`** pointing to the videos folder. Double-click it from
the Pi's desktop to open the folder in the file manager, then drag your new clip in, renaming it to `milanka.mp4`
(replacing the existing one if any).

The new clip is picked up automatically on the **next motion event** — the app re-opens the file every time it starts
playing, so the picture, its soundtrack, and its frame rate all update without a restart. (The audio is re-extracted
with `ffmpeg` the first time the swapped clip plays, so that one play starts a moment later than usual.)

The one case that still needs a restart is a clip with **different pixel dimensions**: the GPU-scaled window is sized
to the previous clip's resolution at startup, so resize it cleanly with:

```bash
systemctl --user restart milanka
```

#### Why `videos/` is git-ignored

The folder itself is tracked (via an empty `.gitkeep` placeholder), but everything inside it is excluded by
`.gitignore` — large `.mp4` files shouldn't bloat the repository. That means `git pull` won't overwrite or remove the
clip you've dropped in.

#### Generating a sample video

If you don't have a clip handy, the repo ships a generator that produces a 2-minute "DVD logo"-style bouncing
animation, scored with a synthesised loop of the opening of Beethoven's Symphony No. 5:

```bash
venv/bin/python src/scripts/generate_sample_video.py
```

Output is written to `videos/milanka.mp4` — exactly where the app expects it. 1280×720 @ 30 fps, ~120 s long. The
soundtrack is muxed in with `ffmpeg`; if `ffmpeg` isn't installed the script still runs and writes a silent clip
(with a warning).

### Power saving

After `IDLE_TIMEOUT_SECONDS` of no motion (default 60 minutes) each display is powered off via
`wlr-randr --output … --off`. The next motion event powers it back on, shows black for `POWER_ON_DELAY_MS` (default 1500
ms) so the monitor can finish its handshake, and then starts the video.

Output names are discovered at runtime by running `wlr-randr` and reading the connected outputs in order — pygame
display N is mapped to the Nth output wlr-randr reports. That means it works whether the HDMI cable is in the port
nearer the USB-C (`HDMI-A-1`) or the one further from it (`HDMI-A-2`). The static `DISPLAY_OUTPUT_NAMES` map in
`src/config.py` is only used as a fallback when wlr-randr can't be reached.

If `wlr-randr` isn't installed, the app skips power management and logs a notice — the rest still works.

### Keyboard

- **ESC** — switch the display from fullscreen to a 640×480 window with an overlay reading
  `Exit the application (Ctrl+Q) to restart and enter fullscreen mode`. The motion → video/red logic keeps running
  inside the small window. There's no way back to fullscreen except by exiting the subprocess (which systemd restarts
  in fullscreen).
- **Q** / **Ctrl+Q** — exit the subprocess. With `Restart=always` on the unit, systemd will restart the service within
  a few seconds, re-entering fullscreen.

### Logging

The app keeps the journal small for long-running deployments:

- **State-change-only logging**: per-poll PIR readings (`raw=0 BLACK hold=-`) are only printed when the screen state
  changes (BLACK → VIDEO, hold expires → BLACK, power-off, wake-complete, etc.). Set `VERBOSE_LOGGING = True` in
  `src/config.py` to re-enable the per-poll line when you need to debug the sensor.
- **Journald cap**: `install.sh` writes `/etc/systemd/journald.conf.d/milanka.conf` which caps the system journal at
  100 MB across at most 10 rotated files. The Pi will never run out of disk space because of logs, regardless of
  how long the service runs.

### Auto-update

Every `UPDATE_CHECK_INTERVAL` seconds (default 3600 = 1 hour) the parent process runs `git fetch`. If the upstream
branch has new commits, it does `git reset --hard @{u}` — **any local edits to tracked files are discarded** so the
Pi always converges on whatever upstream looks like — then re-runs `install.sh` to pick up any new dependencies or
unit-file changes, and finally exits. systemd restarts the service with the new code (thanks to `Restart=always`
in the unit).

Gitignored paths (notably `videos/` — including the `milanka.mp4` clip the user dropped in) are **not** touched by the
reset, so your custom video survives every auto-update.

To avoid SIGTERM-ing the running service while `install.sh` is still working, the auto-updater sets
`MILANKA_SKIP_SERVICE_RESTART=1` in `install.sh`'s env. The downstream `service/service.sh` notices the flag and skips
its own `systemctl --user restart`, leaving the restart to happen via the auto-updater's clean `sys.exit(0)`.

If there's no internet, the fetch fails silently and the loop keeps running; the next check happens an hour later. To
disable auto-update entirely, set `UPDATE_CHECK_INTERVAL = 0` in `src/config.py`.

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
sudo journalctl _SYSTEMD_USER_UNIT=milanka.service -f  # follow logs (PIR readings, etc.)
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
│   ├── updater.py       # Auto-update: git fetch + reset --hard, post-update install.sh
│   ├── main.py          # Orchestrator: hot-plug watcher, signal handling
│   └── scripts/
│       └── generate_sample_video.py  # Builds a 2-min "DVD-logo" bouncing milanka.mp4 (with Beethoven audio)
├── service/
│   ├── milanka.service  # systemd user unit
│   └── service.sh       # one-shot installer for the service
├── videos/              # milanka.mp4 lives here (git-ignored, except .gitkeep)
│   └── .gitkeep
├── install.sh           # Install / configure (venv, wlr-randr, videos symlink, service)
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```
