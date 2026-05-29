# milanka

A Python project for controlling Raspberry Pi GPIO pins.

## Connecting to the Raspberry Pi

The Pi was flashed with Raspberry Pi Imager and configured with hostname `milanka`, user `milanka`, Wi-Fi credentials, and SSH enabled.

Connect over SSH from your machine:

```bash
ssh milanka@milanka.local
```

The `.local` suffix uses mDNS — no need to know the IP. If `milanka.local` does not resolve (e.g. on a network that blocks mDNS), find the Pi's IP from your router and connect with `ssh milanka@<ip-address>` instead.

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

> Must be **sourced**, not executed. Running `./init.sh` will activate the venv only inside the script's subshell, leaving your shell unchanged.

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

> Note: `RPi.GPIO` only installs on a Raspberry Pi. On other systems (macOS, Windows, x86 Linux) the install will fail — that's expected. Develop on those platforms without the dep, or use a mock library such as `Mock.GPIO`.

#### 4. Run the script

```bash
python src/main.py
```

#### 5. Deactivate the virtual environment

```bash
deactivate
```

## Project structure

```
milanka/
├── src/
│   └── main.py          # Entry point
├── init.sh              # Create + activate venv + install deps
├── requirements.txt     # Python dependencies
├── .gitignore
└── README.md
```
