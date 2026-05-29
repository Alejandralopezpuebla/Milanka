"""Single-display controller: runs in its own subprocess, drives one fullscreen
window from one PIR sensor, manages video playback and display power."""

import os
import shutil
import subprocess
import time
from datetime import datetime

# Render on the Pi's physical displays even when launched via SSH.
os.environ.setdefault("DISPLAY", ":0")

import pygame  # noqa: E402
import RPi.GPIO as GPIO  # noqa: E402

from config import (  # noqa: E402
    BLACK,
    DISPLAY_OUTPUT_NAMES,
    HOLD_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    POLL_INTERVAL,
    POWER_ON_DELAY_MS,
    RED,
    VIDEO_PATH,
)


def _try_load_video():
    """Return (cv2_module, sample_fps) if video.mp4 exists and opens, else (None, None)."""
    if not VIDEO_PATH.exists():
        return None, None
    try:
        import cv2  # local import: only needed in video mode
    except ImportError:
        return None, None
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        cap.release()
        return None, None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return cv2, fps


def _set_display_power(output_name: str, on: bool) -> bool:
    """Turn a Wayland output on or off via wlr-randr. Returns True on success."""
    try:
        result = subprocess.run(
            ["wlr-randr", "--output", output_name, "--on" if on else "--off"],
            timeout=5,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def control_display(display_index: int, pir_pin: int) -> None:
    """Drive a fullscreen window on `display_index` from the PIR on `pir_pin`."""
    prefix = f"[d{display_index}/gpio{pir_pin}]"
    output_name = DISPLAY_OUTPUT_NAMES.get(display_index)
    power_mgmt_ok = (
        output_name is not None and shutil.which("wlr-randr") is not None
    )

    cv2, video_fps = _try_load_video()
    mode = "video" if cv2 is not None else "red"
    frame_interval = (1.0 / video_fps) if video_fps else 1.0 / 30
    cap = None

    showing_motion = False
    power_state = "on"        # "on" or "off"
    waking_until = None       # monotonic ts when the wake delay ends, or None
    last_motion_time = None
    last_pir_poll = 0.0
    next_frame_time = 0.0
    boot_time = time.monotonic()  # treat boot as the last "activity" for idle timing

    # ESC toggles to a 640x480 windowed mode with an overlay note. Quit (Q) is
    # how you actually exit the subprocess (and systemd restarts it fullscreen).
    windowed_mode = False
    overlay_surface = None
    overlay_pos = (0, 0)

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
        screen_size = screen.get_size()
        pygame.mouse.set_pos((screen_size[0] - 1, screen_size[1] - 1))

        def present():
            """Flip the back buffer, blitting the overlay on top if we're in windowed mode."""
            if windowed_mode and overlay_surface is not None:
                screen.blit(overlay_surface, overlay_pos)
            pygame.display.flip()

        def build_overlay(size):
            """Pre-render the windowed-mode overlay: white text on a semi-transparent black box."""
            pygame.font.init()
            font = pygame.font.Font(None, 26)
            lines = [
                "Exit the application (Ctrl+Q) to restart",
                "and enter fullscreen mode",
            ]
            text_surfaces = [font.render(line, True, (255, 255, 255)) for line in lines]
            pad = 12
            line_gap = 4
            width = max(s.get_width() for s in text_surfaces) + 2 * pad
            height = sum(s.get_height() for s in text_surfaces) + 2 * pad + line_gap * (len(lines) - 1)
            # SRCALPHA so the background can be partially transparent — the
            # underlying frame shows through, but text stays solid white.
            surf = pygame.Surface((width, height), pygame.SRCALPHA)
            surf.fill((0, 0, 0, 170))  # ~67% opaque black box
            y = pad
            for s in text_surfaces:
                surf.blit(s, ((width - s.get_width()) // 2, y))
                y += s.get_height() + line_gap
            pos = ((size[0] - width) // 2, (size[1] - height) // 2)
            return surf, pos

        screen.fill(BLACK)
        present()

        print(
            f"{prefix} ready (mode={mode}, "
            f"power_mgmt={'on' if power_mgmt_ok else 'unavailable'})",
            flush=True,
        )
        if not power_mgmt_ok:
            print(
                f"{prefix} wlr-randr missing or no output mapping; "
                f"display will stay powered on",
                flush=True,
            )

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    # Q or Ctrl+Q exits the subprocess (systemd restarts it
                    # fullscreen). event.mod isn't checked: matching K_q alone
                    # accepts plain Q, Ctrl+Q, Shift+Q, etc.
                    if event.key == pygame.K_q:
                        return
                    if event.key == pygame.K_ESCAPE and not windowed_mode:
                        # Switch to windowed mode (640x480) with overlay.
                        print(f"{prefix} ESC → windowed mode 640x480", flush=True)
                        windowed_mode = True
                        if cap is not None:
                            cap.release()
                            cap = None
                        showing_motion = False  # force redraw on next loop iteration
                        screen = pygame.display.set_mode(
                            (640, 480), display=display_index,
                        )
                        screen_size = screen.get_size()
                        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)
                        pygame.mouse.set_visible(True)
                        overlay_surface, overlay_pos = build_overlay(screen_size)
                        screen.fill(BLACK)
                        present()

            now = time.monotonic()

            # 1. Poll the PIR at POLL_INTERVAL cadence.
            if now - last_pir_poll >= POLL_INTERVAL:
                motion = GPIO.input(pir_pin)
                if motion:
                    last_motion_time = now
                last_pir_poll = now

                hold = "-"
                if last_motion_time is not None:
                    remaining = HOLD_SECONDS - (now - last_motion_time)
                    if remaining > 0:
                        hold = f"{remaining:4.1f}s"

                if power_state == "off":
                    state_label = "OFF"
                elif waking_until is not None:
                    state_label = "WAKE"
                elif showing_motion:
                    state_label = mode.upper()
                else:
                    state_label = "BLACK"

                stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(
                    f"{stamp} {prefix} raw={motion} {state_label:<5} hold={hold}",
                    flush=True,
                )

            # 2. Determine target power state (on / off).
            if power_mgmt_ok:
                last_activity = last_motion_time if last_motion_time is not None else boot_time
                target_power = (
                    "off" if (now - last_activity) >= IDLE_TIMEOUT_SECONDS else "on"
                )
            else:
                target_power = "on"

            # 3. Apply power-state transitions.
            if power_state == "on" and target_power == "off":
                print(
                    f"{prefix} idle for {IDLE_TIMEOUT_SECONDS}s → powering display off",
                    flush=True,
                )
                if cap is not None:
                    cap.release()
                    cap = None
                showing_motion = False
                _set_display_power(output_name, False)
                power_state = "off"
                waking_until = None
            elif power_state == "off" and target_power == "on":
                print(f"{prefix} motion → powering display on", flush=True)
                _set_display_power(output_name, True)
                power_state = "on"
                waking_until = now + (POWER_ON_DELAY_MS / 1000.0)
                screen.fill(BLACK)
                present()

            # 4. If display is off, idle — no rendering, no motion handling.
            if power_state == "off":
                time.sleep(0.2)
                continue

            # 5. If waking, keep showing black until the wake delay completes.
            #    last_motion_time keeps updating from the PIR poll above, so by
            #    the time we exit this phase the hold timer will still be valid
            #    if motion is ongoing.
            if waking_until is not None:
                if now < waking_until:
                    screen.fill(BLACK)
                    present()
                    time.sleep(0.05)
                    continue
                waking_until = None
                print(f"{prefix} wake delay complete", flush=True)

            # 6. Normal motion → video/red transitions.
            should_show = (
                last_motion_time is not None
                and (now - last_motion_time) < HOLD_SECONDS
            )
            if should_show and not showing_motion:
                if mode == "video":
                    cap = cv2.VideoCapture(str(VIDEO_PATH))
                    next_frame_time = now
                else:
                    screen.fill(RED)
                    present()
                showing_motion = True
            elif not should_show and showing_motion:
                if cap is not None:
                    cap.release()
                    cap = None
                screen.fill(BLACK)
                present()
                showing_motion = False

            # 7. Render the next video frame, if it's time.
            if showing_motion and cap is not None and now >= next_frame_time:
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w = frame.shape[:2]
                    surf = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
                    if (w, h) != screen_size:
                        surf = pygame.transform.scale(surf, screen_size)
                    screen.blit(surf, (0, 0))
                    present()
                next_frame_time = max(next_frame_time + frame_interval, now)

            # 8. Sleep. Tight while playing video, lazy otherwise.
            if showing_motion and cap is not None:
                time.sleep(max(0.0, min(next_frame_time - time.monotonic(), 0.05)))
            else:
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        # Make sure we leave the display powered on so the user doesn't see a
        # dark screen after the service stops.
        if power_state == "off" and power_mgmt_ok:
            try:
                _set_display_power(output_name, True)
            except Exception:
                pass
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        try:
            pygame.quit()
        except Exception:
            pass
        try:
            GPIO.cleanup(pir_pin)
        except Exception:
            pass
