"""Auto-update: periodically check upstream, reset hard to it on new commits,
then re-run install.sh so dependency / unit changes are applied before the
caller exits and systemd restarts the service."""

import os
import subprocess

from config import REPO_DIR


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


def check_for_updates() -> bool:
    """Fetch and (if upstream has new commits) force-reset the working tree to upstream.

    Any local edits to tracked files are discarded — we always converge on
    whatever upstream says. Gitignored files (e.g. videos/) are not touched.

    Returns True if HEAD was moved. Returns False if there's no internet, no
    new commits, or the operation failed — the parent loop just keeps going.
    """
    fetch = _git(["fetch", "--quiet"], timeout=20)
    if fetch is None or fetch.returncode != 0:
        return False  # most likely no internet; stay quiet

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
