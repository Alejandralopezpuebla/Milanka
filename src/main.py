import time
from datetime import datetime

import RPi.GPIO as GPIO

PIR_PIN = 4  # BCM pin number — change to match your wiring
POLL_INTERVAL = 0.2  # seconds between readings


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)

    print(f"Reading GPIO {PIR_PIN} every {POLL_INTERVAL}s. Press Ctrl+C to stop.")
    print("Warming up sensor (give it ~30–60s on first boot)...")
    time.sleep(2)
    print("-" * 40)
    print(f"{'time':<12} {'raw':<5} {'state'}")
    print("-" * 40)

    try:
        while True:
            value = GPIO.input(PIR_PIN)
            label = "MOTION" if value else "idle"
            now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"{now:<12} {value:<5} {label}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
