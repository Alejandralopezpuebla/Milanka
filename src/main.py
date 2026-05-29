import time

import RPi.GPIO as GPIO

PIR_PIN = 4  # BCM pin number — change to match your wiring


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)

    print(f"PIR sensor reading on GPIO {PIR_PIN}. Press Ctrl+C to stop.")
    print("Warming up sensor...")
    time.sleep(2)
    print("Ready.")

    last_state = None
    try:
        while True:
            state = GPIO.input(PIR_PIN)
            if state != last_state:
                if state:
                    print("Motion detected")
                else:
                    print("No motion")
                last_state = state
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
