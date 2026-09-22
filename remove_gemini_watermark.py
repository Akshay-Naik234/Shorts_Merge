#!/usr/bin/env python3
"""
Gemini watermark remover - NATURAL TEXTURE version

The previous Telea/delogo versions can look like a blurred or smeared patch.
This version uses exemplar/patch matching:

1. Detects the small Gemini sparkle.
2. Looks around the watermark for a visually similar clean patch.
3. Copies only the texture needed to replace the sparkle.
4. Feather-blends the replacement into the original frame.
5. Keeps audio from the original MP4.

Designed for:
    videos/1.mp4
    videos/2.mp4
    ...
    videos/n.mp4

Output:
    output/1.mp4
    output/2.mp4
    ...
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


# Gemini watermark center measured from the supplied sample (1920x1080).
CX_PCT = 1740.0 / 1920.0
CY_PCT = 895.0 / 1080.0

# Approximate half-size of the sparkle.
RX_PCT = 48.0 / 1920.0
RY_PCT = 48.0 / 1080.0

# Extra mask around the anti-aliased white edges.
MASK_EXPAND = 3

# Patch/search settings.
PATCH_MARGIN = 18
SEARCH_RADIUS = 150
RING_WIDTH = 10

# Only search candidates that are sufficiently far from the logo.
MIN_SOURCE_DISTANCE = 75

# Feather the copied texture so the boundary is not visible.
FEATHER = 7


def check_program(name):
    if shutil.which(name) is None:
        raise RuntimeError(
            f"'{name}' was not found in PATH. "
            "Install FFmpeg and make sure it is available from Command Prompt."
        )


def get_video_info(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = r.stdout.strip().splitlines()

    width = int(lines[0])
    height = int(lines[1])

    n, d = lines[2].split("/")
    fps = float(n) / float(d)

    return width, height, fps


def make_mask(width, height):
    """
    Small 4-point sparkle mask.
    This is intentionally NOT a rectangle.
    """
    cx = int(round(width * CX_PCT))
    cy = int(round(height * CY_PCT))

    rx = max(7, int(round(width * RX_PCT)))
    ry = max(7, int(round(height * RY_PCT)))

    ix = max(3, int(round(rx * 0.27)))
    iy = max(3, int(round(ry * 0.27)))

    pts = np.array([
        [cx, cy - ry],
        [cx + ix, cy - iy],
        [cx + rx, cy],
        [cx + ix, cy + iy],
        [cx, cy + ry],
        [cx - ix, cy + iy],
        [cx - rx, cy],
        [cx - ix, cy - iy],
    ], dtype=np.int32)

    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [pts], 255)

    # Catch the anti-aliased white edge, but keep it small.
    if MASK_EXPAND > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * MASK_EXPAND + 1, 2 * MASK_EXPAND + 1)
        )
        mask = cv2.dilate(mask, kernel, iterations=1)

    return mask, cx, cy, rx, ry


def candidate_score(lab, ring_mask, src_x, src_y, target_x, target_y, pw, ph):
    """
    Compare a candidate patch against the known pixels surrounding the logo.
    Lower score = more similar texture/color.
    """
    h, w = lab.shape[:2]

    x0 = target_x - pw // 2
    y0 = target_y - ph // 2

    sx0 = src_x - pw // 2
    sy0 = src_y - ph // 2

    if x0 < 0 or y0 < 0 or x0 + pw >= w or y0 + ph >= h:
        return None

    if sx0 < 0 or sy0 < 0 or sx0 + pw >= w or sy0 + ph >= h:
        return None

    target = lab[y0:y0 + ph, x0:x0 + pw]
    source = lab[sy0:sy0 + ph, sx0:sx0 + pw]

    # Compare only the known ring around the watermark.
    ys, xs = np.where(ring_mask > 0)

    if len(xs) < 20:
        return None

    a = target[ys, xs].astype(np.float32)
    b = source[ys, xs].astype(np.float32)

    # L*a*b*: color + brightness.
    diff = np.abs(a - b)

    # Robust score prevents a few strong edges from dominating.
    score = float(np.mean(diff))

    return score


def build_ring(mask, cx, cy, rx, ry):
    """
    Known pixels immediately surrounding the watermark.
    """
    h, w = mask.shape

    # Work on the target patch only.
    pw = 2 * (rx + PATCH_MARGIN)
    ph = 2 * (ry + PATCH_MARGIN)

    x0 = cx - pw // 2
    y0 = cy - ph // 2

    local_mask = np.zeros((ph, pw), dtype=np.uint8)

    src_y1 = max(0, y0)
    src_y2 = min(h, y0 + ph)
    src_x1 = max(0, x0)
    src_x2 = min(w, x0 + pw)

    local_mask[
        src_y1 - y0:src_y2 - y0,
        src_x1 - x0:src_x2 - x0
    ] = mask[src_y1:src_y2, src_x1:src_x2]

    # Dilate the logo mask to define the immediate comparison ring.
    dil = cv2.dilate(
        local_mask,
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * RING_WIDTH + 1, 2 * RING_WIDTH + 1)
        )
    )

    ring = dil.copy()
    ring[local_mask > 0] = 0

    return ring, pw, ph


def patch_replace(frame, mask, cx, cy, rx, ry):
    """
    Find a clean nearby texture patch and use it to replace only the logo.

    This preserves natural local texture much better than blur/inpainting.
    """
    h, w = frame.shape[:2]

    ring, pw, ph = build_ring(mask, cx, cy, rx, ry)

    # Make sure patch fits.
    pw = min(pw, w - 4)
    ph = min(ph, h - 4)

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)

    best = None
    best_score = float("inf")

    # Search a grid around the logo.
    step = 8

    y_min = max(ph // 2 + 2, cy - SEARCH_RADIUS)
    y_max = min(h - ph // 2 - 2, cy + SEARCH_RADIUS)
    x_min = max(pw // 2 + 2, cx - SEARCH_RADIUS)
    x_max = min(w - pw // 2 - 2, cx + SEARCH_RADIUS)

    for sy in range(y_min, y_max + 1, step):
        for sx in range(x_min, x_max + 1, step):

            distance = ((sx - cx) ** 2 + (sy - cy) ** 2) ** 0.5
            if distance < MIN_SOURCE_DISTANCE:
                continue

            score = candidate_score(
                lab, ring,
                sx, sy,
                cx, cy,
                pw, ph
            )

            if score is not None and score < best_score:
                best_score = score
                best = (sx, sy)

    if best is None:
        # Extremely unlikely; use a very small Telea fallback.
        return cv2.inpaint(frame, mask, 2, cv2.INPAINT_TELEA)

    sx, sy = best

    tx0 = cx - pw // 2
    ty0 = cy - ph // 2
    sx0 = sx - pw // 2
    sy0 = sy - ph // 2

    source_patch = frame[sy0:sy0 + ph, sx0:sx0 + pw].copy()

    # Local mask.
    local_mask = mask[
        ty0:ty0 + ph,
        tx0:tx0 + pw
    ].copy()

    # Feather only the replacement edge.
    alpha = cv2.GaussianBlur(
        local_mask,
        (2 * FEATHER + 1, 2 * FEATHER + 1),
        0
    ).astype(np.float32) / 255.0

    alpha = alpha[..., None]

    target = frame[
        ty0:ty0 + ph,
        tx0:tx0 + pw
    ].copy()

    blended = (
        source_patch.astype(np.float32) * alpha +
        target.astype(np.float32) * (1.0 - alpha)
    ).astype(np.uint8)

    result = frame.copy()
    result[
        ty0:ty0 + ph,
        tx0:tx0 + pw
    ] = blended

    return result


def process_video(input_path, output_path):
    width, height, fps = get_video_info(input_path)

    print(f"  Resolution: {width}x{height}")
    print(f"  FPS: {fps:.3f}")

    mask, cx, cy, rx, ry = make_mask(width, height)

    print(
        f"  Gemini center: ({cx}, {cy})"
    )
    print(
        "  Method: local texture patch matching + feather blending"
    )

    temp = output_path.with_name(
        output_path.stem + ".texture_tmp.mp4"
    )

    if temp.exists():
        temp.unlink()

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {input_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(
        str(temp),
        fourcc,
        fps,
        (width, height)
    )

    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not create temporary video.")

    count = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            cleaned = patch_replace(
                frame, mask, cx, cy, rx, ry
            )

            writer.write(cleaned)

            count += 1

            if count % 10 == 0 or count == total:
                pct = (count / total * 100) if total else 0
                print(
                    f"    {count}/{total} ({pct:.1f}%)",
                    end="\r"
                )

    finally:
        cap.release()
        writer.release()

    print()

    if count == 0:
        if temp.exists():
            temp.unlink()
        raise RuntimeError("No frames processed.")

    # Replace temporary video while retaining original audio.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-y",

        "-i", str(temp),
        "-i", str(input_path),

        "-map", "0:v:0",
        "-map", "1:a?",

        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",

        "-c:a", "copy",
        "-movflags", "+faststart",

        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True)
    finally:
        if temp.exists():
            temp.unlink()

    print(f"  DONE -> {output_path.name}")


def numeric_mp4_files(folder):
    pattern = re.compile(r"^(\d+)\.mp4$", re.IGNORECASE)

    files = [
        p for p in folder.iterdir()
        if p.is_file() and pattern.match(p.name)
    ]

    return sorted(files, key=lambda p: int(p.stem))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        default="videos"
    )

    parser.add_argument(
        "--output",
        default="output"
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true"
    )

    args = parser.parse_args()

    check_program("ffmpeg")
    check_program("ffprobe")

    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        print(f"ERROR: {input_dir} does not exist.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    videos = numeric_mp4_files(input_dir)

    if not videos:
        print("No numeric MP4 files found.")
        sys.exit(0)

    print("=" * 72)
    print("GEMINI WATERMARK REMOVER - NATURAL TEXTURE VERSION")
    print("=" * 72)
    print(f"Found {len(videos)} video(s)")
    print("=" * 72)

    success = 0
    skipped = 0
    failed = 0

    for i, input_path in enumerate(videos, 1):
        output_path = output_dir / input_path.name

        print(f"\n[{i}/{len(videos)}] Processing {input_path.name}")

        if args.skip_existing and output_path.exists():
            print("  SKIPPED - output already exists")
            skipped += 1
            continue

        try:
            process_video(input_path, output_path)
            success += 1

        except Exception as e:
            failed += 1
            print(f"  FAILED: {e}")

            if output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass

    print("\n" + "=" * 72)
    print("FINISHED")
    print(f"Successful: {success}")
    print(f"Skipped   : {skipped}")
    print(f"Failed    : {failed}")
    print("=" * 72)


if __name__ == "__main__":
    main()
