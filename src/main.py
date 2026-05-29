import multiprocessing as mp
import os
import signal
import time
from datetime import datetime

# Render on the Pi's physical displays even when launched via SSH.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402
import RPi.GPIO as GPIO  # noqa: E402

POLL_INTERVAL = 0.5      # seconds between readings
HOLD_SECONDS = 3.0       # keep red this long after the last detected motion

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


def wait_for_displays() -> int:
    """Block until at least one display is connected; return how many are present."""
    while True:
        n = detect_display_count()
        if n > 0:
            return n
        print("No displays detected, waiting... (re-checking in 5s)", flush=True)
        time.sleep(5)


def main() -> None:
    n_displays = wait_for_displays()
    n_to_control = min(n_displays, len(DISPLAY_PIN_MAP))
    print(
        f"Found {n_displays} display(s); controlling {n_to_control}.",
        flush=True,
    )

    procs: list[mp.Process] = []
    for i in range(n_to_control):
        pin = DISPLAY_PIN_MAP[i]
        p = mp.Process(target=control_display, args=(i, pin), name=f"display-{i}")
        p.start()
        procs.append(p)
        print(f"Started {p.name} (pid={p.pid}) for GPIO {pin}", flush=True)

    def shutdown(signum, frame):
        print(f"\nReceived signal {signum}, stopping children...", flush=True)
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(timeout=5)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    for p in procs:
        p.join()


if __name__ == "__main__":
    main()
