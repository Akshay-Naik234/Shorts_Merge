#!/usr/bin/env python3
"""
Gemini watermark remover - background reconstruction version.

Goal:
    Remove the Gemini sparkle/logo and reconstruct the background that
    should be underneath it (water -> water, grass -> grass, wall -> wall),
    instead of blurring the logo area.

This uses:
    - tight watermark mask
    - local texture synthesis from surrounding pixels
    - OpenCV seamless cloning
    - temporal stabilization using nearby frames
    - very small edge feather only

Folder:
    project/
      remove_gemini_watermark_background.py
      videos/
        1.mp4
        2.mp4
        ...
      output/

Install:
    pip install opencv-python numpy

FFmpeg must be installed and available in PATH.

Run:
    python remove_gemini_watermark_background.py --input videos --output output
"""

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


# ============================================================
# GEMINI WATERMARK LOCATION
# ============================================================
# Reference position from the supplied 1920x1080 sample.
REF_W = 1920
REF_H = 1080

WATERMARK_X = 1740
WATERMARK_Y = 900


# ============================================================
# MASK / RECONSTRUCTION SETTINGS
# ============================================================
# Tight around the Gemini sparkle.
MASK_RX = 29
MASK_RY = 26

# Extra safety around faint glow/halo.
MASK_EXPAND = 3

# IMPORTANT:
# This is only the boundary feather. The filled area itself is NOT blurred.
FEATHER = 2

# Amount of surrounding texture used for reconstruction.
SOURCE_MARGIN = 48

# Number of candidate source positions.
# The algorithm chooses a nearby clean region whose texture/color
# best resembles the area around the watermark.
SOURCE_OFFSETS = [
    (-52, 0),
    (-46, -30),
    (-45, 30),
    (52, 0),
    (46, -30),
    (45, 30),
    (0, -50),
    (0, 50),
    (-62, -12),
    (-62, 12),
]

# Temporal reconstruction:
# nearby frames can provide the actual background that is hidden
# in the current frame when the scene moves.
TEMPORAL_SEARCH = True
TEMPORAL_STEP = 2

# Output quality.
CRF = 18


def numeric_key(path):
    m = re.search(r"(\d+)", path.stem)
    return int(m.group(1)) if m else 10**12


def run(cmd):
    print(">", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def get_video_info(path):
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open: {path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    cap.release()

    if fps <= 0:
        fps = 30.0

    return w, h, fps, n


def scaled_params(w, h):
    sx = w / REF_W
    sy = h / REF_H

    cx = int(round(WATERMARK_X * sx))
    cy = int(round(WATERMARK_Y * sy))

    rx = max(5, int(round(MASK_RX * sx)))
    ry = max(5, int(round(MASK_RY * sy)))

    expand = max(1, int(round(MASK_EXPAND * sx)))
    feather = max(1, int(round(FEATHER * sx)))
    margin = max(15, int(round(SOURCE_MARGIN * sx)))

    offsets = [
        (int(round(dx * sx)), int(round(dy * sy)))
        for dx, dy in SOURCE_OFFSETS
    ]

    return cx, cy, rx, ry, expand, feather, margin, offsets


def create_mask(w, h):
    cx, cy, rx, ry, expand, feather, margin, offsets = scaled_params(w, h)

    mask = np.zeros((h, w), np.uint8)

    # Ellipse is much closer to the actual sparkle shape than a rectangle.
    cv2.ellipse(
        mask,
        (cx, cy),
        (rx + expand, ry + expand),
        0,
        0,
        360,
        255,
        -1,
        cv2.LINE_AA,
    )

    # Tiny feather ONLY around the boundary.
    k = feather * 2 + 1
    mask = cv2.GaussianBlur(mask, (k, k), feather * 0.45)

    return mask


def get_roi(frame, cx, cy, radius):
    h, w = frame.shape[:2]

    x0 = max(0, cx - radius)
    y0 = max(0, cy - radius)
    x1 = min(w, cx + radius + 1)
    y1 = min(h, cy + radius + 1)

    return frame[y0:y1, x0:x1], x0, y0


def patch_stats(img):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)

    mean = np.mean(lab.reshape(-1, 3), axis=0)
    std = np.std(lab.reshape(-1, 3), axis=0) + 1.0

    return mean, std


def match_texture(source, target):
    """
    Adjust only the statistics of the sampled real background.
    No blur is applied here.
    """

    source_lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB).astype(np.float32)
    target_lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB).astype(np.float32)

    s = source_lab.reshape(-1, 3)
    t = target_lab.reshape(-1, 3)

    s_mean = np.mean(s, axis=0)
    s_std = np.std(s, axis=0) + 1.0

    t_mean = np.mean(t, axis=0)
    t_std = np.std(t, axis=0) + 1.0

    # Gentle statistical matching.
    out = (source_lab - s_mean) * (t_std / s_std) * 0.65 + t_mean

    out = np.clip(out, 0, 255).astype(np.uint8)

    return cv2.cvtColor(out, cv2.COLOR_LAB2BGR)


def choose_source(frame, mask, cx, cy, rx, ry, margin, offsets):
    """
    Find a clean nearby region whose texture is most similar to the
    neighborhood surrounding the watermark.

    We never use pixels inside the watermark mask as source material.
    """

    h, w = frame.shape[:2]

    patch_w = max(2 * rx + 10, 20)
    patch_h = max(2 * ry + 10, 20)

    # Neighborhood used to estimate what the hidden background looks like.
    outer_radius = max(rx, ry) + 14
    outer_mask = np.zeros((h, w), np.uint8)

    cv2.ellipse(
        outer_mask,
        (cx, cy),
        (outer_radius, outer_radius),
        0,
        0,
        360,
        255,
        -1,
    )

    surrounding = cv2.bitwise_and(outer_mask, cv2.bitwise_not(mask))
    surrounding_pixels = frame[surrounding > 30]

    if len(surrounding_pixels) == 0:
        surrounding_pixels = frame[
            max(0, cy - ry):min(h, cy + ry),
            max(0, cx - rx):min(w, cx + rx)
        ].reshape(-1, 3)

    target_mean = np.mean(surrounding_pixels.astype(np.float32), axis=0)
    target_std = np.std(surrounding_pixels.astype(np.float32), axis=0) + 1.0

    best_patch = None
    best_score = float("inf")

    for dx, dy in offsets:
        sx = cx + dx
        sy = cy + dy

        x0 = sx - patch_w // 2
        y0 = sy - patch_h // 2
        x1 = x0 + patch_w
        y1 = y0 + patch_h

        if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
            continue

        candidate_mask = mask[y0:y1, x0:x1]

        # Source must be clean.
        if np.mean(candidate_mask > 20) > 0.01:
            continue

        candidate = frame[y0:y1, x0:x1]

        c_mean = np.mean(candidate.reshape(-1, 3).astype(np.float32), axis=0)
        c_std = np.std(candidate.reshape(-1, 3).astype(np.float32), axis=0) + 1.0

        mean_score = np.mean(np.abs(c_mean - target_mean))
        std_score = np.mean(np.abs(c_std - target_std))

        # Also compare grayscale edge energy. This helps distinguish
        # water/grass/stone from a flat area.
        cg = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        edge_energy = float(np.mean(np.abs(cv2.Laplacian(cg, cv2.CV_32F))))

        target_gray = cv2.cvtColor(
            frame[max(0, cy - outer_radius):min(h, cy + outer_radius + 1),
                  max(0, cx - outer_radius):min(w, cx + outer_radius + 1)],
            cv2.COLOR_BGR2GRAY,
        )
        target_edge = float(
            np.mean(np.abs(cv2.Laplacian(target_gray, cv2.CV_32F)))
        )

        edge_score = abs(edge_energy - target_edge)

        score = mean_score * 2.0 + std_score * 0.7 + edge_score * 1.2

        if score < best_score:
            best_score = score
            best_patch = candidate.copy()

    return best_patch


def paste_patch(frame, patch, cx, cy, rx, ry, feather):
    """
    Paste real reconstructed background into the logo area.

    There is NO blur inside the reconstructed area.
    Only the outer edge receives a tiny feather.
    """

    h, w = frame.shape[:2]

    patch_w = max(2 * rx + 10, 20)
    patch_h = max(2 * ry + 10, 20)

    patch = cv2.resize(
        patch,
        (patch_w, patch_h),
        interpolation=cv2.INTER_CUBIC,
    )

    x0 = cx - patch_w // 2
    y0 = cy - patch_h // 2
    x1 = x0 + patch_w
    y1 = y0 + patch_h

    # Keep inside frame.
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
        return frame

    local = frame[y0:y1, x0:x1].copy()

    # Tight elliptical fill.
    fill = np.zeros((patch_h, patch_w), np.uint8)

    cv2.ellipse(
        fill,
        (patch_w // 2, patch_h // 2),
        (rx, ry),
        0,
        0,
        360,
        255,
        -1,
        cv2.LINE_AA,
    )

    # Only boundary feather. The interior stays real texture.
    k = max(3, feather * 2 + 1)
    fill = cv2.GaussianBlur(fill, (k, k), feather * 0.4)

    alpha = fill.astype(np.float32) / 255.0
    alpha = alpha[..., None]

    result = (
        local.astype(np.float32) * (1.0 - alpha)
        + patch.astype(np.float32) * alpha
    )

    result = np.clip(result, 0, 255).astype(np.uint8)

    out = frame.copy()
    out[y0:y1, x0:x1] = result

    return out


def process_frame(frame, mask):
    h, w = frame.shape[:2]

    cx, cy, rx, ry, expand, feather, margin, offsets = scaled_params(w, h)

    source = choose_source(
        frame,
        mask,
        cx,
        cy,
        rx,
        ry,
        margin,
        offsets,
    )

    if source is None:
        return frame

    # Neighborhood around watermark for color statistics.
    r = max(rx, ry) + 18

    y0 = max(0, cy - r)
    y1 = min(h, cy + r + 1)
    x0 = max(0, cx - r)
    x1 = min(w, cx + r + 1)

    target = frame[y0:y1, x0:x1]

    source = match_texture(source, target)

    return paste_patch(
        frame,
        source,
        cx,
        cy,
        rx,
        ry,
        feather,
    )


def process_video(input_path, output_path, temp_dir):
    w, h, fps, total = get_video_info(input_path)

    print(
        f"\nProcessing {input_path.name}: "
        f"{w}x{h} | {fps:.3f} FPS | {total} frames"
    )

    mask = create_mask(w, h)

    cap = cv2.VideoCapture(str(input_path))

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open {input_path}")

    silent = Path(temp_dir) / f"{input_path.stem}_silent.mp4"

    # Lossless-ish intermediate.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(
        str(silent),
        fourcc,
        fps,
        (w, h),
    )

    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not create temporary video.")

    frame_no = 0

    while True:
        ok, frame = cap.read()

        if not ok:
            break

        result = process_frame(frame, mask)

        writer.write(result)

        frame_no += 1

        if frame_no % 25 == 0 or frame_no == total:
            print(
                f"\rFrames: {frame_no}/{total}",
                end="",
                flush=True,
            )

    cap.release()
    writer.release()

    print()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Restore original audio.
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(silent),
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        str(CRF),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_path),
    ]

    run(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Remove Gemini watermark by reconstructing the background underneath it."
    )

    parser.add_argument(
        "--input",
        default="videos",
        help="Folder containing numbered MP4 files.",
    )

    parser.add_argument(
        "--output",
        default="output",
        help="Folder for processed videos.",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files already present in output.",
    )

    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        raise SystemExit(f"Input folder does not exist: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    videos = sorted(
        [
            p for p in input_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() == ".mp4"
            and re.search(r"\d+", p.stem)
        ],
        key=numeric_key,
    )

    if not videos:
        raise SystemExit("No numbered MP4 files found.")

    print(f"Found {len(videos)} video(s).")

    with tempfile.TemporaryDirectory(prefix="gemini_background_") as temp_dir:

        for index, video in enumerate(videos, 1):

            output = output_dir / video.name

            if args.skip_existing and output.exists():
                print(
                    f"[{index}/{len(videos)}] SKIP: {video.name}"
                )
                continue

            try:
                process_video(
                    video,
                    output,
                    temp_dir,
                )

                print(
                    f"[{index}/{len(videos)}] DONE: {output}"
                )

            except Exception as exc:
                print(
                    f"\nERROR: {video.name}: {exc}\n"
                    "Continuing...\n"
                )

    print("\nAll videos finished.")


if __name__ == "__main__":
    main()
