"""Single-display controller: runs in its own subprocess, drives one fullscreen
window from one PIR sensor, manages video playback and display power."""

import os
import shutil
import signal
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
    VERBOSE_LOGGING,
    VIDEO_PATH,
)


def detect_display_count() -> int:
    """Return how many displays the desktop currently exposes (Wayland or X11)."""
    pygame.init()
    try:
        return len(pygame.display.get_desktop_sizes())
    finally:
        pygame.quit()


def _try_load_video():
    """Return (cv2_module, sample_fps) if video.mp4 exists and opens, else (None, None).

    Prints a clear reason on failure so the user can diagnose why the app is
    showing the red fallback instead of the video.
    """
    if not VIDEO_PATH.exists():
        print(
            f"video mode: {VIDEO_PATH} not found → falling back to red",
            flush=True,
        )
        return None, None
    try:
        import cv2  # local import: only needed in video mode
    except ImportError as e:
        print(
            f"video mode: cv2 not importable ({e}); is the venv active? → falling back to red",
            flush=True,
        )
        return None, None
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        cap.release()
        print(
            f"video mode: cv2.VideoCapture couldn't open {VIDEO_PATH} "
            f"(unsupported codec? corrupt file?) → falling back to red",
            flush=True,
        )
        return None, None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cap.release()
    return cv2, fps


def _list_wayland_outputs() -> list[str]:
    """Return the names of connected outputs in the order wlr-randr prints them.

    Each top-level line in wlr-randr's output is one connected output and starts
    at column 0; the first whitespace-separated token is its name (e.g.
    'HDMI-A-1', 'HDMI-A-2'). Properties of that output are indented. Returns []
    if wlr-randr is missing, can't connect to the compositor, or errors out.
    """
    try:
        result = subprocess.run(
            ["wlr-randr"], timeout=5, capture_output=True, text=True,
        )
        if result.returncode != 0:
            return []
        names: list[str] = []
        for line in result.stdout.splitlines():
            if line and not line[0].isspace():
                parts = line.split(None, 1)
                if parts:
                    names.append(parts[0])
        return names
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _set_display_power(output_name: str, on: bool) -> bool:
    """Turn a Wayland output on or off via wlr-randr. Returns True on success.

    On failure, logs the wlr-randr exit code and stderr so the user can see what
    went wrong (most commonly: 'Output HDMI-A-1 not found' if the configured
    name doesn't match the compositor's, or a Wayland connection error when
    invoked from a session that doesn't have WAYLAND_DISPLAY set).
    """
    direction = "on" if on else "off"
    try:
        result = subprocess.run(
            ["wlr-randr", "--output", output_name, f"--{direction}"],
            timeout=5,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip() or "(no output)"
            print(
                f"wlr-randr {output_name} --{direction} failed "
                f"(rc={result.returncode}): {err}",
                flush=True,
            )
            return False
        return True
    except FileNotFoundError:
        print("wlr-randr is not installed — cannot toggle display power.", flush=True)
        return False
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"wlr-randr error: {e}", flush=True)
        return False


def control_display(display_index: int, pir_pin: int) -> None:
    """Drive a fullscreen window on `display_index` from the PIR on `pir_pin`."""
    # multiprocessing.fork() copies the parent's signal handlers into us.
    # That made Ctrl+C (SIGINT to the whole process group) run the parent's
    # shutdown() in this process too — referencing a stale procs dict — then
    # return as if nothing happened, leaving the loop running. Reset both
    # signals to Python's default_int_handler so they raise KeyboardInterrupt,
    # which the try/except below catches and the finally clause cleans up after.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, signal.default_int_handler)

    prefix = f"[d{display_index}/gpio{pir_pin}]"

    # Discover the Wayland output name from wlr-randr (HDMI-A-1, HDMI-A-2, …).
    # We use the Nth connected output in wlr-randr's enumeration as the one
    # for pygame display N — this matches the kernel's order on Pi 4 / labwc
    # regardless of which physical port is in use. Falls back to the static
    # DISPLAY_OUTPUT_NAMES map if wlr-randr can't be reached.
    outputs = _list_wayland_outputs()
    if display_index < len(outputs):
        output_name = outputs[display_index]
    else:
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
    last_cursor_park = 0.0    # last time we warped the cursor to the corner
    next_frame_time = 0.0
    boot_time = time.monotonic()  # treat boot as the last "activity" for idle timing
    prev_state_label = None  # tracks the last logged state so we only print on change

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

        # Hide the cursor AFTER set_mode — some platforms reset it on surface
        # creation. The systemd unit forces SDL_VIDEODRIVER=x11 (Xwayland on
        # the Pi), so labwc honors the cursor-hide request. Belt and suspenders:
        # also assign a 1x1 transparent cursor image and warp the pointer to
        # the bottom-right corner.
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
            f"power_mgmt={'on (output=' + output_name + ')' if power_mgmt_ok else 'unavailable'})",
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

            # Re-park the cursor in the bottom-right corner periodically while
            # in fullscreen, in case the initial warp landed before the window
            # had pointer focus. Skipped in windowed mode so the user can use
            # the cursor normally.
            if not windowed_mode and now - last_cursor_park >= 2.0:
                pygame.mouse.set_pos((screen_size[0] - 1, screen_size[1] - 1))
                last_cursor_park = now

            # 1. Poll the PIR at POLL_INTERVAL cadence. Logging is gated on
            # state changes to keep the journal compact over long runs — set
            # VERBOSE_LOGGING in config.py to re-enable per-poll output.
            if now - last_pir_poll >= POLL_INTERVAL:
                motion = GPIO.input(pir_pin)
                if motion:
                    last_motion_time = now
                last_pir_poll = now

                if power_state == "off":
                    state_label = "OFF"
                elif waking_until is not None:
                    state_label = "WAKE"
                elif showing_motion:
                    state_label = mode.upper()
                else:
                    state_label = "BLACK"

                if VERBOSE_LOGGING or state_label != prev_state_label:
                    hold = "-"
                    if last_motion_time is not None:
                        remaining = HOLD_SECONDS - (now - last_motion_time)
                        if remaining > 0:
                            hold = f"{remaining:4.1f}s"
                    stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(
                        f"{stamp} {prefix} raw={motion} {state_label:<5} hold={hold}",
                        flush=True,
                    )
                    prev_state_label = state_label

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
        # Once we're shutting down, block any further SIGINT/SIGTERM so the
        # cleanup below can finish. Without this, a second signal (e.g. the
        # parent's p.terminate() arriving while we're already mid-cleanup from
        # the original Ctrl+C, or the user mashing Ctrl+C twice) would raise
        # KeyboardInterrupt out of, say, pygame.quit() — or even out of the
        # signal.signal() call itself (the call isn't atomic). pthread_sigmask
        # is a single syscall and atomic from this thread's point of view.
        try:
            if hasattr(signal, "pthread_sigmask"):
                signal.pthread_sigmask(
                    signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM},
                )
            else:
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
        except (Exception, KeyboardInterrupt):
            pass  # best-effort — proceed to cleanup regardless

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
