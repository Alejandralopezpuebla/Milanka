"""Generate a 30-second sample video for the milanka app.

A 'DVD-logo'-style coloured box containing the word 'milanka' bounces around a
1280x720 black frame, switching colour on every wall bounce. Output is written
to videos/milanka.mp4 at the repo root — the same path the app expects.

Run from the repo root:

    venv/bin/python src/scripts/generate_sample_video.py

Or, with the venv activated:

    python src/scripts/generate_sample_video.py

Requires opencv-python-headless and numpy (both already in requirements.txt).
"""

from pathlib import Path

import cv2
import numpy as np

# Two levels up from this file is the repo root; the app reads videos/milanka.mp4 there.
REPO_DIR = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_DIR / "videos" / "milanka.mp4"

WIDTH, HEIGHT = 1280, 720
FPS = 30
DURATION_SECONDS = 30
TOTAL_FRAMES = FPS * DURATION_SECONDS

LOGO_W, LOGO_H = 240, 100
SPEED_X, SPEED_Y = 6, 5  # pixels per frame — different so the path isn't a single diagonal

# Bright BGR colours cycled on each wall bounce (cv2 uses BGR, not RGB).
COLORS = [
    (66, 245, 245),   # yellow
    (200, 66, 245),   # purple
    (66, 245, 66),    # green
    (245, 66, 66),    # blue
    (245, 105, 66),   # cyan-ish
    (66, 145, 245),   # orange
    (245, 66, 200),   # magenta
    (66, 66, 245),    # red
]


def main() -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(OUT_PATH), fourcc, FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise SystemExit(
            f"cv2.VideoWriter could not open {OUT_PATH}. "
            f"Check that opencv-python-headless was installed correctly."
        )

    x, y = 100, 100
    dx, dy = SPEED_X, SPEED_Y
    color_idx = 0
    font = cv2.FONT_HERSHEY_SIMPLEX
    text = "milanka"
    font_scale = 1.4
    thickness = 3
    (text_w, text_h), _ = cv2.getTextSize(text, font, font_scale, thickness)

    for _ in range(TOTAL_FRAMES):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        x += dx
        y += dy

        bounced = False
        if x <= 0:
            x = 0
            dx = -dx
            bounced = True
        elif x + LOGO_W >= WIDTH:
            x = WIDTH - LOGO_W
            dx = -dx
            bounced = True
        if y <= 0:
            y = 0
            dy = -dy
            bounced = True
        elif y + LOGO_H >= HEIGHT:
            y = HEIGHT - LOGO_H
            dy = -dy
            bounced = True
        if bounced:
            color_idx = (color_idx + 1) % len(COLORS)

        color = COLORS[color_idx]
        cv2.rectangle(frame, (x, y), (x + LOGO_W, y + LOGO_H), color, thickness=-1)

        text_x = x + (LOGO_W - text_w) // 2
        text_y = y + (LOGO_H + text_h) // 2
        cv2.putText(
            frame,
            text,
            (text_x, text_y),
            font,
            font_scale,
            (0, 0, 0),
            thickness,
            cv2.LINE_AA,
        )

        writer.write(frame)

    writer.release()
    print(
        f"Wrote {OUT_PATH} "
        f"({TOTAL_FRAMES} frames @ {FPS}fps, {WIDTH}x{HEIGHT}, ~{DURATION_SECONDS}s)"
    )


if __name__ == "__main__":
    main()
