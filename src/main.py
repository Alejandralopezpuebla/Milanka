import os
import time
from datetime import datetime

# Render on the Pi's physical HDMI display even when launched via SSH.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402
import RPi.GPIO as GPIO  # noqa: E402

PIR_PIN = 4              # BCM pin number
POLL_INTERVAL = 0.1      # seconds between readings
HOLD_SECONDS = 5.0       # keep red this long after motion stops

BLACK = (0, 0, 0)
RED = (255, 0, 0)


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)

    pygame.init()
    pygame.mouse.set_visible(False)
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.NOFRAME)
    pygame.display.set_caption("milanka")

    current_color = None
    last_motion_time = None
    running = True

    print(f"Polling GPIO {PIR_PIN} every {POLL_INTERVAL}s. Hold = {HOLD_SECONDS}s.")
    print(f"{'time':<13} {'raw':<4} {'screen':<6} {'hold'}")
    print("-" * 40)

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE,
                    pygame.K_q,
                ):
                    running = False

            now = time.monotonic()
            motion = GPIO.input(PIR_PIN)

            if motion:
                last_motion_time = now

            if last_motion_time is not None and (now - last_motion_time) < HOLD_SECONDS:
                target_color = RED
                remaining = HOLD_SECONDS - (now - last_motion_time)
                hold_str = f"{remaining:4.1f}s"
            else:
                target_color = BLACK
                hold_str = "-"

            if target_color != current_color:
                screen.fill(target_color)
                pygame.display.flip()
                current_color = target_color

            stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            screen_label = "RED" if target_color == RED else "BLACK"
            print(f"{stamp:<13} {motion:<4} {screen_label:<6} {hold_str}")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
