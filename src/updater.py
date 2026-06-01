"""Auto-update: periodically check upstream, reset hard to it on new commits,
then re-run install.sh so dependency / unit changes are applied before the
caller exits and systemd restarts the service."""

import os
import socket
import subprocess
from urllib.parse import urlparse

from config import REPO_DIR

# Cached origin remote URL — never changes during a process's lifetime, so
# parse it once instead of running `git remote get-url` every hour.
_remote_url_cache: str | None = None


def _git(args: list[str], timeout: float) -> subprocess.CompletedProcess | None:
    """Run a git command in the repo dir. Returns the CompletedProcess, or None on timeout/OS error."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(REPO_DIR),
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _origin_host_port() -> tuple[str, int] | None:
    """Return (host, port) for the origin remote, or None if we can't parse it.

    Handles the common URL formats:
      https://github.com/user/repo.git           → ('github.com', 443)
      http://example.com/user/repo.git           → ('example.com', 80)
      ssh://git@github.com:2222/user/repo.git    → ('github.com', 2222)
      git@github.com:user/repo.git               → ('github.com', 22)
    """
    global _remote_url_cache
    if _remote_url_cache is None:
        result = _git(["remote", "get-url", "origin"], timeout=3)
        if result is None or result.returncode != 0:
            return None
        _remote_url_cache = result.stdout.strip()

    url = _remote_url_cache
    if url.startswith(("http://", "https://", "ssh://", "git://")):
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return None
        if parsed.port:
            return host, parsed.port
        default_ports = {"https": 443, "http": 80, "ssh": 22, "git": 9418}
        return host, default_ports.get(parsed.scheme, 443)
    if "@" in url and ":" in url:
        try:
            host = url.split("@", 1)[1].split(":", 1)[0]
            return host, 22
        except (IndexError, ValueError):
            return None
    return None


def _can_reach_remote(timeout: float = 3.0) -> bool:
    """Fast TCP probe to the origin remote — returns False within `timeout` seconds
    if we have no internet / DNS / route to the host. Avoids waiting up to 20 s
    for `git fetch` to give up on its own."""
    host_port = _origin_host_port()
    if host_port is None:
        return False
    try:
        with socket.create_connection(host_port, timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def check_for_updates() -> bool:
    """Fetch and (if upstream has new commits) force-reset the working tree to upstream.

    Any local edits to tracked files are discarded — we always converge on
    whatever upstream says. Gitignored files (e.g. videos/) are not touched.

    Returns True if HEAD was moved. Returns False if there's no internet, no
    new commits, or the operation failed — the parent loop just keeps going.

    Skips the git fetch entirely (and returns within ~3 seconds) if the remote
    host can't be reached, so we don't block the parent for 20 s every check
    when the Pi is offline.
    """
    if not _can_reach_remote():
        return False  # offline or DNS-failed — skip silently

    fetch = _git(["fetch", "--quiet"], timeout=10)
    if fetch is None or fetch.returncode != 0:
        return False

    local = _git(["rev-parse", "HEAD"], timeout=5)
    upstream = _git(["rev-parse", "@{u}"], timeout=5)
    if (
        local is None
        or upstream is None
        or local.returncode != 0
        or upstream.returncode != 0
        or local.stdout.strip() == upstream.stdout.strip()
    ):
        return False

    print(
        f"New commits upstream (local={local.stdout.strip()[:8]}, "
        f"upstream={upstream.stdout.strip()[:8]}); resetting to upstream "
        f"(local edits to tracked files will be discarded)...",
        flush=True,
    )
    reset = _git(["reset", "--hard", "@{u}"], timeout=60)
    if reset is None or reset.returncode != 0:
        msg = reset.stderr.strip() if reset is not None else "timeout"
        print(f"git reset failed: {msg}", flush=True)
        return False
    return True


def run_post_update_install() -> None:
    """Re-run install.sh so any new requirements / unit file changes are applied.

    MILANKA_SKIP_SERVICE_RESTART is set so service.sh skips its `systemctl restart`
    — the caller will exit shortly and systemd's Restart=always will pick up the
    new code (and the new unit, since daemon-reload was already done).
    """
    install_script = REPO_DIR / "install.sh"
    if not install_script.exists():
        print("install.sh not found; skipping post-update install.", flush=True)
        return
    env = os.environ.copy()
    env["MILANKA_SKIP_SERVICE_RESTART"] = "1"
    print("Running install.sh to apply post-update changes...", flush=True)
    try:
        result = subprocess.run(
            ["bash", str(install_script)],
            cwd=str(REPO_DIR),
            env=env,
            timeout=300,
        )
        if result.returncode != 0:
            print(
                f"install.sh exited with code {result.returncode}; "
                f"continuing anyway, the restart may pick up partial state",
                flush=True,
            )
    except subprocess.TimeoutExpired:
        print("install.sh timed out after 300s; continuing.", flush=True)
    except OSError as e:
        print(f"install.sh could not be launched: {e}", flush=True)
