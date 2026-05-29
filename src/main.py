"""Entry point: detects displays, spawns one controller subprocess per display,
reconciles hot-plug events, and shuts everything down on signal."""

import multiprocessing as mp
import os
import signal
import time

# Render on the Pi's physical displays even when launched via SSH. Set here too
# (display.py also sets it) so the parent process can talk to Wayland to
# enumerate displays before any subprocess is spawned.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402

from config import DISPLAY_PIN_MAP, HOTPLUG_CHECK_INTERVAL  # noqa: E402
from display import control_display  # noqa: E402


def detect_display_count() -> int:
    pygame.init()
    try:
        return len(pygame.display.get_desktop_sizes())
    finally:
        pygame.quit()


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

    previously_logged_count = -1

    while not shutting_down:
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
