import os
import time

# Make the script render on the Pi's physical HDMI display even when launched
# via SSH. Override on the command line if you need a different display.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402
import RPi.GPIO as GPIO  # noqa: E402

PIR_PIN = 4  # BCM pin number
POLL_INTERVAL = 0.05  # seconds

BLACK = (0, 0, 0)
RED = (255, 0, 0)


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)

    pygame.init()
    pygame.mouse.set_visible(False)
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.NOFRAME)
    pygame.display.set_caption("milanka")

    current_color = None  # force first paint
    running = True

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

            motion = GPIO.input(PIR_PIN)
            new_color = RED if motion else BLACK
            if new_color != current_color:
                screen.fill(new_color)
                pygame.display.flip()
                current_color = new_color
                print("MOTION" if motion else "idle")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
