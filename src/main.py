"""Entry point: detects displays, spawns one controller subprocess per display,
reconciles hot-plug events, periodically pulls upstream code, and shuts
everything down on signal."""

import multiprocessing as mp
import os
import signal
import subprocess
import sys
import time

# Render on the Pi's physical displays even when launched via SSH. Set here too
# (display.py also sets it) so the parent process can talk to Wayland to
# enumerate displays before any subprocess is spawned.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402

from config import (  # noqa: E402
    DISPLAY_PIN_MAP,
    HOTPLUG_CHECK_INTERVAL,
    REPO_DIR,
    UPDATE_CHECK_INTERVAL,
)
from display import control_display  # noqa: E402


def detect_display_count() -> int:
    pygame.init()
    try:
        return len(pygame.display.get_desktop_sizes())
    finally:
        pygame.quit()


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
    """Fetch and (if upstream has new commits) fast-forward pull.

    Returns True if any new commits were pulled. Returns False if there's no
    internet, no new commits, the working tree has conflicts, or anything else
    went wrong — the parent loop should just keep going in that case.
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
        f"upstream={upstream.stdout.strip()[:8]}); pulling...",
        flush=True,
    )
    pull = _git(["pull", "--ff-only", "--quiet"], timeout=60)
    if pull is None or pull.returncode != 0:
        msg = pull.stderr.strip() if pull is not None else "timeout"
        print(f"git pull failed: {msg}", flush=True)
        return False
    return True


def spawn_controller(display_index: int) -> mp.Process:
    pin = DISPLAY_PIN_MAP[display_index]
    p = mp.Process(
        target=control_display,
        args=(display_index, pin),
        name=f"display-{display_index}",
    )
    p.start()
    print(
        f"+ Display {display_index} present → started subprocess (pid={p.pid}, gpio={pin})",
        flush=True,
    )
    return p


def main() -> None:
    procs: dict[int, mp.Process] = {}
    shutting_down = False

    def shutdown(signum, _frame):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        print(
            f"\nReceived signal {signum}, stopping all controllers...",
            flush=True,
        )
        for p in procs.values():
            if p.is_alive():
                p.terminate()
        for p in procs.values():
            p.join(timeout=5)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print(
        f"Display watcher started (polling every {HOTPLUG_CHECK_INTERVAL}s).",
        flush=True,
    )
    if UPDATE_CHECK_INTERVAL > 0:
        print(
            f"Auto-update enabled: checking every {UPDATE_CHECK_INTERVAL}s.",
            flush=True,
        )

    previously_logged_count = -1
    last_update_check = time.monotonic()  # first check happens UPDATE_CHECK_INTERVAL from now

    while not shutting_down:
        # 0. Auto-update: if upstream advanced, pull and exit so systemd restarts us.
        if (
            UPDATE_CHECK_INTERVAL > 0
            and time.monotonic() - last_update_check >= UPDATE_CHECK_INTERVAL
        ):
            last_update_check = time.monotonic()
            if check_for_updates():
                print(
                    "Updates pulled; exiting so systemd restarts with the new code.",
                    flush=True,
                )
                for p in procs.values():
                    if p.is_alive():
                        p.terminate()
                for p in procs.values():
                    p.join(timeout=5)
                sys.exit(0)

        # 1. Detect what's currently plugged in.
        try:
            n_displays = detect_display_count()
        except Exception as e:
            print(f"! display detection failed: {e}", flush=True)
            n_displays = 0

        target_indices = set(range(min(n_displays, len(DISPLAY_PIN_MAP))))

        # 2. Reap dead subprocesses (could have crashed, or display disappeared).
        for i in list(procs.keys()):
            if not procs[i].is_alive():
                exit_code = procs[i].exitcode
                procs[i].join()
                del procs[i]
                if i in target_indices:
                    print(
                        f"! display-{i} exited unexpectedly (code={exit_code}); will respawn",
                        flush=True,
                    )

        running_indices = set(procs.keys())

        # 3. Stop controllers whose display vanished.
        for i in sorted(running_indices - target_indices):
            p = procs[i]
            print(
                f"- Display {i} gone → stopping subprocess (pid={p.pid})",
                flush=True,
            )
            p.terminate()
            p.join(timeout=5)
            del procs[i]

        # 4. Start controllers for any newly-present display.
        for i in sorted(target_indices - set(procs.keys())):
            procs[i] = spawn_controller(i)

        # 5. Periodic status, but only when the visible count changes.
        if n_displays != previously_logged_count:
            if n_displays == 0:
                print("No displays detected, waiting...", flush=True)
            else:
                print(
                    f"Now controlling {len(procs)} of {n_displays} display(s).",
                    flush=True,
                )
            previously_logged_count = n_displays

        # 6. Sleep until next reconciliation, in small slices so shutdown is responsive.
        elapsed = 0.0
        while elapsed < HOTPLUG_CHECK_INTERVAL and not shutting_down:
            time.sleep(0.1)
            elapsed += 0.1


if __name__ == "__main__":
    main()
