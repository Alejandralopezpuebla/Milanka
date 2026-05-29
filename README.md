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

## Setup

### Quick start (macOS / Linux)

Run the bootstrap script — it creates the venv, installs the requirements, and leaves the venv active in your shell:

```bash
source init.sh
```

> Must be **sourced**, not executed. Running `./init.sh` will activate the venv only inside the script's subshell,
> leaving your shell unchanged.

When you're done:

```bash
deactivate
```

### Manual setup

#### 1. Create the virtual environment

```bash
python3 -m venv venv
```

#### 2. Activate the virtual environment

On macOS / Linux:

```bash
source venv/bin/activate
```

On Windows (PowerShell):

```powershell
venv\Scripts\Activate.ps1
```

On Windows (cmd):

```cmd
venv\Scripts\activate.bat
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> Note: `RPi.GPIO` only installs on a Raspberry Pi. On other systems (macOS, Windows, x86 Linux) the install will fail —
> that's expected. Develop on those platforms without the dep, or use a mock library such as `Mock.GPIO`.

#### 4. Run the script

```bash
python src/main.py
```

#### 5. Deactivate the virtual environment

```bash
deactivate
```

## Run on boot (systemd user service)

To keep the screen under control across reboots and crashes, the app can run as a **systemd user service**. The service
starts with the desktop session (assumes desktop autologin is on — see step 3 in the SSH section), auto-restarts on
failure, and writes logs to the journal.

### One-time install

On the Pi, in the project directory:

```bash
cd /opt/Milanka
source init.sh              # ensures venv/ exists with deps installed
bash service/service.sh     # installs and starts milanka.service
```

The installer:

1. Copies `service/milanka.service` to `~/.config/systemd/user/`.
2. Calls `loginctl enable-linger` so the user systemd instance survives logout and starts on boot.
3. Runs `systemctl --user daemon-reload`, then `enable` + `restart` on the unit.

After this, the service starts automatically every time the desktop logs in (i.e. every boot, given autologin).

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
├── init.sh              # Create + activate venv + install deps
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```
