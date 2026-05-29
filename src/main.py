import multiprocessing as mp
import os
import signal
import time
from datetime import datetime

# Render on the Pi's physical displays even when launched via SSH.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402
import RPi.GPIO as GPIO  # noqa: E402

POLL_INTERVAL = 0.5            # seconds between PIR readings (in each subprocess)
HOLD_SECONDS = 3.0             # keep red this long after the last detected motion
HOTPLUG_CHECK_INTERVAL = 3.0   # how often the parent re-checks the display list

# Display index → PIR pin (BCM numbering).
#   Display 0 ← PIR on GPIO 4  (physical pin 7)
#   Display 1 ← PIR on GPIO 17 (physical pin 11)
DISPLAY_PIN_MAP = {
    0: 4,
    1: 17,
}

BLACK = (0, 0, 0)
RED = (255, 0, 0)


def control_display(display_index: int, pir_pin: int) -> None:
    """Drive a fullscreen window on `display_index` from the PIR on `pir_pin`."""
    prefix = f"[d{display_index}/gpio{pir_pin}]"
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pir_pin, GPIO.IN)

        pygame.init()
        screen = pygame.display.set_mode(
            (0, 0),
            pygame.FULLSCREEN | pygame.NOFRAME,
            display=display_index,
        )
        pygame.display.set_caption(f"milanka display {display_index}")

        # Hide the cursor AFTER set_mode (some platforms reset it on surface
        # creation). Belt and suspenders: also use a blank cursor image and
        # park the pointer in the bottom-right corner.
        pygame.mouse.set_visible(False)
        blank = pygame.Surface((1, 1), pygame.SRCALPHA)
        pygame.mouse.set_cursor(pygame.cursors.Cursor((0, 0), blank))
        w, h = screen.get_size()
        pygame.mouse.set_pos((w - 1, h - 1))

        current_color = None
        last_motion_time = None

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE,
                    pygame.K_q,
                ):
                    return

            now = time.monotonic()
            motion = GPIO.input(pir_pin)

            if motion:
                last_motion_time = now

            if last_motion_time is not None and (now - last_motion_time) < HOLD_SECONDS:
                target = RED
                hold = f"{HOLD_SECONDS - (now - last_motion_time):4.1f}s"
            else:
                target = BLACK
                hold = "-"

            if target != current_color:
                screen.fill(target)
                pygame.display.flip()
                current_color = target

            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            label = "RED" if target == RED else "BLACK"
            print(f"{stamp} {prefix} raw={motion} {label:<5} hold={hold}", flush=True)

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            pygame.quit()
        except Exception:
            pass
        try:
            GPIO.cleanup(pir_pin)
        except Exception:
            pass


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
                # We'll respawn below if the display is still target; otherwise
                # the display went away and this is expected.
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
