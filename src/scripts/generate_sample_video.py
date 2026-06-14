"""Generate a sample video (with sound) for the milanka app.

A 'DVD-logo'-style coloured box containing the word 'milanka' bounces around a
1280x720 black frame, switching colour on every wall bounce. Under it plays a
synthesised rendition of the opening of Beethoven's Symphony No. 5 ("da-da-da-
daaa"), looped for the length of the clip. Output is written to
videos/milanka.mp4 at the repo root — the same path the app expects.

Run from the repo root:

    venv/bin/python src/scripts/generate_sample_video.py

Or, with the venv activated:

    python src/scripts/generate_sample_video.py

Requires opencv-python-headless and numpy (both already in requirements.txt).
The soundtrack additionally requires the `ffmpeg` command-line tool to mux the
audio onto the video; if ffmpeg isn't found, a silent clip is written instead
(with a warning) so the script never hard-fails on that account.
"""

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import cv2
import numpy as np

# Two levels up from this file is the repo root; the app reads videos/milanka.mp4 there.
REPO_DIR = Path(__file__).resolve().parent.parent.parent
OUT_PATH = REPO_DIR / "videos" / "milanka.mp4"

WIDTH, HEIGHT = 1280, 720
FPS = 30
DURATION_SECONDS = 120
TOTAL_FRAMES = FPS * DURATION_SECONDS

LOGO_W, LOGO_H = 240, 100
SPEED_X, SPEED_Y = 6, 5  # pixels per frame — different so the path isn't a single diagonal

SAMPLE_RATE = 44100  # audio sample rate for the synthesised soundtrack

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

# Beethoven, Symphony No. 5, opening motif (C minor). Note frequencies in Hz;
# 0.0 means a rest. Durations in seconds at an Allegro-con-brio clip: the three
# repeated notes are quick eighths, the resolution notes are held (fermata).
# Two statements — "G G G Eb" then "F F F D" — make one ~4-second loop.
G4, EB4, F4, D4 = 392.00, 311.13, 349.23, 293.66
EIGHTH = 0.13
PHRASE = [
    (0.0, EIGHTH),          # the famous eighth-rest upbeat
    (G4, EIGHTH), (G4, EIGHTH), (G4, EIGHTH),
    (EB4, 1.10),            # fermata
    (0.0, 0.28),
    (0.0, EIGHTH),          # second upbeat rest
    (F4, EIGHTH), (F4, EIGHTH), (F4, EIGHTH),
    (D4, 1.30),             # fermata
    (0.0, 0.40),            # breath before the loop repeats
]


def _synth_note(freq: float, duration: float) -> np.ndarray:
    """Render one note (or a rest, if freq == 0) as a float32 mono waveform.

    A few harmonics plus a short attack/release envelope give it a warm,
    MIDI-ish tone and keep the loop free of clicks at note boundaries.
    """
    n = int(round(duration * SAMPLE_RATE))
    if freq <= 0.0:
        return np.zeros(n, dtype=np.float32)

    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    wave_ = (
        np.sin(2 * np.pi * freq * t)
        + 0.5 * np.sin(2 * np.pi * 2 * freq * t)
        + 0.25 * np.sin(2 * np.pi * 3 * freq * t)
    ).astype(np.float32)

    # Linear attack/release so onsets/offsets don't click. ~8 ms each, capped
    # at a quarter of the note so very short notes still get a full envelope.
    edge = min(int(0.008 * SAMPLE_RATE), n // 4)
    if edge > 0:
        env = np.ones(n, dtype=np.float32)
        env[:edge] = np.linspace(0.0, 1.0, edge, dtype=np.float32)
        env[-edge:] = np.linspace(1.0, 0.0, edge, dtype=np.float32)
        wave_ *= env
    return wave_


def _synthesize_soundtrack() -> np.ndarray:
    """Build the looped Symphony-No.5 phrase as int16 mono samples, just over
    DURATION_SECONDS long (ffmpeg trims it to the video with -shortest)."""
    phrase = np.concatenate([_synth_note(f, d) for f, d in PHRASE])
    reps = int(np.ceil(DURATION_SECONDS * SAMPLE_RATE / len(phrase)))
    track = np.tile(phrase, reps)

    peak = float(np.max(np.abs(track))) or 1.0
    track = (track / peak) * 0.85  # normalise with a little headroom
    return (track * 32767.0).astype(np.int16)


def _write_wav(samples: np.ndarray, path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(samples.tobytes())


def _render_silent_video(path: Path) -> None:
    """Render the bouncing-logo frames to `path` (no audio)."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise SystemExit(
            f"cv2.VideoWriter could not open {path}. "
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


def _mux(video_path: Path, audio_path: Path, out_path: Path) -> bool:
    """Combine the silent video and the wav into out_path via ffmpeg.

    Copies the video stream untouched and encodes the audio to AAC; -shortest
    trims the looped audio to the video length. Returns True on success.
    """
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            "ffmpeg muxing failed (writing silent video instead):\n"
            f"{(result.stderr or result.stdout).strip()}"
        )
        return False
    return True


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    have_ffmpeg = shutil.which("ffmpeg") is not None
    if not have_ffmpeg:
        print(
            "ffmpeg not found on PATH — writing a SILENT clip. Install ffmpeg "
            "(e.g. `sudo apt-get install ffmpeg` / `brew install ffmpeg`) and "
            "re-run to get the Beethoven soundtrack."
        )
        _render_silent_video(OUT_PATH)
        _report()
        return

    # Render video + audio to temp files, then mux into the final OUT_PATH so a
    # failure never leaves a half-written milanka.mp4 in place.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_video = Path(tmp) / "video.mp4"
        tmp_audio = Path(tmp) / "track.wav"

        _render_silent_video(tmp_video)
        _write_wav(_synthesize_soundtrack(), tmp_audio)

        if _mux(tmp_video, tmp_audio, OUT_PATH):
            _report(with_audio=True)
        else:
            shutil.copyfile(tmp_video, OUT_PATH)
            _report()


def _report(with_audio: bool = False) -> None:
    sound = "Symphony No. 5 soundtrack" if with_audio else "no audio"
    print(
        f"Wrote {OUT_PATH} "
        f"({TOTAL_FRAMES} frames @ {FPS}fps, {WIDTH}x{HEIGHT}, "
        f"~{DURATION_SECONDS}s, {sound})"
    )


if __name__ == "__main__":
    main()
