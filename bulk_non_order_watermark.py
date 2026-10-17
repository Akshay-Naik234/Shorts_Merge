# ============================================================
# WINDOWS VERSION
# Gemini / Veo Watermark Removal - Numeric Batch Processing
#
# Run:
#     python watermark.py
#
# Project structure:
#     Video_Generation/
#         watermark.py
#         videos/
#             3.mp4
#             4.mp4
#             6.mp4
#             7.mp4
#         output/
#         tools/
#
# All MP4 files are automatically sorted by the first number in
# their filename and processed in ascending numerical order.
# No video-number input is required.
# ============================================================

import os
import sys
import re
import time
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "videos"
OUTPUT_DIR = BASE_DIR / "output"
TOOLS_DIR = BASE_DIR / "tools"

TOOLS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# False = skip existing output files
# True  = process them again
OVERWRITE = False

# False = normal engine mode
# True  = CPU mode
USE_CPU = False

TOOL_DOWNLOAD_URL = (
    "https://github.com/allenk/VeoWatermarkRemover/releases/download/"
    "v0.6.5-demo/GeminiWatermarkTool-Windows-x64-Video.zip"
)

ENGINE_EXE = TOOLS_DIR / "GeminiWatermarkTool-Video.exe"
ZIP_FILE = TOOLS_DIR / "gwt_video.zip"

# ============================================================
# PLATFORM / INPUT / FFMPEG CHECKS
# ============================================================

if os.name != "nt":
    raise RuntimeError(
        "\nThis version is designed for Windows.\n"
        "Do not run it inside Google Colab/Linux."
    )

if not INPUT_DIR.is_dir():
    raise FileNotFoundError(
        f"\nVideos folder not found:\n{INPUT_DIR}\n\n"
        "Create a 'videos' folder next to watermark.py "
        "and put your MP4 files inside it."
    )


def check_ffmpeg():
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            first_line = (
                result.stdout.splitlines()[0]
                if result.stdout else "FFmpeg detected"
            )
            print(f"[FFmpeg] {first_line}")
            return True
    except FileNotFoundError:
        pass

    print("\n" + "=" * 72)
    print("ERROR: FFmpeg was not found.")
    print("=" * 72)
    print("Install FFmpeg and make sure it is available in Windows PATH.")
    print("Test with: ffmpeg -version")
    print("=" * 72)
    return False


if not check_ffmpeg():
    sys.exit(1)

# ============================================================
# NATURAL SORT / VIDEO NUMBER
# ============================================================

def natural_sort_key(filename):
    parts = re.split(r"(\d+)", filename)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def get_video_number(filename):
    match = re.search(r"\d+", Path(filename).stem)
    return int(match.group()) if match else None


# ============================================================
# FIND ENGINE
# ============================================================

def find_engine():
    if ENGINE_EXE.exists():
        print(f"[Engine] Existing engine found:\n          {ENGINE_EXE}")
        return ENGINE_EXE

    candidates = list(TOOLS_DIR.rglob("GeminiWatermarkTool-Video.exe"))
    if candidates:
        source = candidates[0]
        if source != ENGINE_EXE:
            shutil.copy2(source, ENGINE_EXE)
        print(f"[Engine] Found existing engine:\n          {ENGINE_EXE}")
        return ENGINE_EXE

    return None


def ensure_engine():
    existing = find_engine()
    if existing:
        return existing

    print("\n" + "=" * 72)
    print("Downloading Gemini/Veo Windows engine...")
    print("=" * 72)
    print(TOOL_DOWNLOAD_URL)

    try:
        urllib.request.urlretrieve(TOOL_DOWNLOAD_URL, ZIP_FILE)
    except Exception as exc:
        raise RuntimeError(
            "Could not download the GeminiWatermarkTool package.\n"
            f"Error: {exc}"
        ) from exc

    if not ZIP_FILE.exists():
        raise RuntimeError("Download completed but ZIP file was not created.")

    print(f"Downloaded: {ZIP_FILE.stat().st_size / 1024 / 1024:.2f} MB")
    print("Extracting engine...")

    try:
        with zipfile.ZipFile(ZIP_FILE, "r") as zf:
            zf.extractall(TOOLS_DIR)
    except Exception as exc:
        raise RuntimeError(f"Could not extract ZIP:\n{exc}") from exc
    finally:
        try:
            ZIP_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    candidates = list(TOOLS_DIR.rglob("GeminiWatermarkTool-Video.exe"))
    if candidates:
        source = candidates[0]
        if source != ENGINE_EXE:
            shutil.copy2(source, ENGINE_EXE)

    if not ENGINE_EXE.exists():
        print("\nFiles extracted from package:")
        for path in TOOLS_DIR.rglob("*"):
            if path.is_file():
                print(" ", path)
        raise FileNotFoundError(
            "GeminiWatermarkTool-Video.exe was not found after extraction."
        )

    print(f"[Engine] Ready:\n          {ENGINE_EXE}")
    return ENGINE_EXE


ENGINE = ensure_engine()


def engine_command(*args):
    return [str(ENGINE), *[str(arg) for arg in args]]


# ============================================================
# TEST ENGINE
# ============================================================

print("\n" + "=" * 72)
print("Testing watermark engine...")
print("=" * 72)

try:
    test_result = subprocess.run(
        engine_command("--help"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    print((test_result.stdout or "")[-3000:])
    if test_result.returncode not in (0, 1):
        print(f"\nWARNING: Engine returned code {test_result.returncode}.")
    print("Engine test completed.")
except Exception as exc:
    print(f"[Warning] Could not run engine help test: {exc}")


# ============================================================
# PATCH SKIPPED FRAMES
# ============================================================

def check_and_patch_skipped_frames(input_video, output_video):
    """
    Compare the watermark region in the input and processed video.
    Frames that appear unchanged are individually reprocessed and
    inserted into a rebuilt output video.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("\n[Warning] Installing OpenCV and NumPy...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "opencv-python", "numpy"],
            check=True,
        )
        import cv2
        import numpy as np

    cap_in = cv2.VideoCapture(str(input_video))
    cap_out = cv2.VideoCapture(str(output_video))

    if not cap_in.isOpened():
        print("\n[Patch] Could not open input video.")
        cap_in.release()
        cap_out.release()
        return True

    if not cap_out.isOpened():
        print("\n[Patch] Could not open output video.")
        cap_in.release()
        cap_out.release()
        return True

    w = int(cap_in.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap_in.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap_in.get(cv2.CAP_PROP_FPS) or 24.0

    if (w, h) == (1280, 720):
        rx, ry, rw, rh, alpha_val = 1136, 576, 48, 48, 0.60
    elif (w, h) == (1920, 1080):
        rx, ry, rw, rh, alpha_val = 1716, 884, 60, 60, 0.95
    else:
        rx = int(w * 0.89)
        ry = int(h * 0.80)
        rw = int(w * 0.04)
        rh = int(h * 0.06)
        alpha_val = 0.60

    diffs = []
    while True:
        ret_in, frame_in = cap_in.read()
        ret_out, frame_out = cap_out.read()
        if not ret_in or not ret_out:
            break

        if (
            ry + rh > frame_in.shape[0]
            or rx + rw > frame_in.shape[1]
            or ry + rh > frame_out.shape[0]
            or rx + rw > frame_out.shape[1]
        ):
            diffs.append(float("inf"))
            continue

        region_in = frame_in[ry:ry + rh, rx:rx + rw].astype(np.float32)
        region_out = frame_out[ry:ry + rh, rx:rx + rw].astype(np.float32)
        diffs.append(float(np.mean(np.abs(region_in - region_out))))

    cap_in.release()
    cap_out.release()

    if not diffs:
        return True

    finite_diffs = [d for d in diffs if np.isfinite(d)]
    if not finite_diffs:
        return True

    median_d = float(np.median(finite_diffs))
    threshold = max(7.0, median_d * 0.4)
    skipped_indices = [
        i for i, diff in enumerate(diffs)
        if np.isfinite(diff) and diff < threshold
    ]

    if not skipped_indices:
        return True

    print(
        f"\n[Auto-fixing {len(skipped_indices)} potentially skipped frame(s)]...",
        end="",
        flush=True,
    )

    temp_dir = output_video.parent / ".temp_patch"
    temp_dir.mkdir(exist_ok=True)
    clean_frames = {}

    cap_in = cv2.VideoCapture(str(input_video))
    for frame_index in skipped_indices:
        cap_in.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap_in.read()
        if not ret:
            continue

        raw_path = temp_dir / f"frame_{frame_index}_raw.png"
        clean_path = temp_dir / f"frame_{frame_index}_clean.png"
        cv2.imwrite(str(raw_path), frame)

        cmd = engine_command(
            "-i", raw_path,
            "-o", clean_path,
            "--region", f"{rx},{ry},{rw},{rh}",
            "--veo-alpha", str(alpha_val),
            "--denoise", "ai",
            "-f",
        )
        if USE_CPU:
            cmd.append("--cpu")

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

        if clean_path.exists():
            clean_frame = cv2.imread(str(clean_path))
            if clean_frame is not None:
                clean_frames[frame_index] = clean_frame

        for path in (raw_path, clean_path):
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass

    cap_in.release()

    if not clean_frames:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return True

    temp_out = output_video.parent / f".temp_{output_video.name}"
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-i", str(input_video),
        "-map", "0:v:0", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
        str(temp_out),
    ]

    proc = None
    cap_out = None
    try:
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
        cap_out = cv2.VideoCapture(str(output_video))
        frame_index = 0

        while True:
            ret, frame = cap_out.read()
            if not ret:
                break
            if frame_index in clean_frames:
                frame = clean_frames[frame_index]
            proc.stdin.write(frame.tobytes())
            frame_index += 1

        cap_out.release()
        cap_out = None
        proc.stdin.close()
        proc.stdin = None
        return_code = proc.wait()

        if return_code != 0:
            print(f"\n[Patch Error] FFmpeg returned code {return_code}.")
            return False

    except Exception as exc:
        print(f"\n[Patch Error] {exc}")
        try:
            if proc and proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        return False
    finally:
        if cap_out is not None:
            cap_out.release()
        shutil.rmtree(temp_dir, ignore_errors=True)

    if temp_out.exists() and temp_out.stat().st_size > 1000:
        try:
            output_video.unlink(missing_ok=True)
            temp_out.replace(output_video)
            return True
        except Exception as exc:
            print(f"\n[Patch Replace Error] {exc}")
            return False

    return False


# ============================================================
# PROCESS ONE VIDEO
# ============================================================

def process_video(input_video, output_video):
    cmd = engine_command(
        "-i", input_video,
        "-o", output_video,
        "--veo",
        "-v",
    )
    if USE_CPU:
        cmd.append("--cpu")

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if (
            proc.returncode == 0
            and output_video.exists()
            and output_video.stat().st_size > 1000
        ):
            check_and_patch_skipped_frames(input_video, output_video)
            return True

        print(
            f"\n[Warning] Process returned code {proc.returncode} "
            f"for {input_video.name}"
        )
        lines = (proc.stdout or "").strip().splitlines()
        if lines:
            print("\nLast engine messages:")
            for line in lines[-20:]:
                print(" ", line)
        return False

    except Exception as exc:
        print(
            f"\n[Error] Exception during processing "
            f"{input_video.name}: {exc}"
        )
        return False


# ============================================================
# FIND AND SORT VIDEOS NUMERICALLY
# ============================================================

all_files = [
    filename
    for filename in os.listdir(INPUT_DIR)
    if filename.lower().endswith(".mp4")
]

# Sort by the first number in each filename. Files without a number
# are placed at the end and sorted naturally.
all_files.sort(
    key=lambda filename: (
        get_video_number(filename) is None,
        get_video_number(filename)
        if get_video_number(filename) is not None
        else float("inf"),
        natural_sort_key(filename),
    )
)

if not all_files:
    print(f"\nNo .mp4 files found in:\n{INPUT_DIR}")
    raise SystemExit(0)

# No selection array is needed: process every MP4 in numeric order.
filtered_files = all_files

print("\n" + "=" * 72)
print("NUMERICALLY SORTED PROCESSING QUEUE")
print("=" * 72)
for position, filename in enumerate(filtered_files, 1):
    print(f"{position:>3}. {filename}")
print("=" * 72)


# ============================================================
# DISPLAY CONFIGURATION
# ============================================================

print("\n" + "=" * 72)
print("   WINDOWS GEMINI / VEO WATERMARK REMOVAL")
print("=" * 72)
print("Engine      : GeminiWatermarkTool-Video.exe")
print("Execution   : Native Windows")
print(f"Videos Path : {INPUT_DIR}")
print(f"Output Path : {OUTPUT_DIR}")
print(f"Videos      : {len(filtered_files)}")
print("Processing  : Reverse Alpha / AI Denoise")
print(f"Mode        : {'CPU' if USE_CPU else 'Normal Engine Mode'}")
print(f"Overwrite   : {OVERWRITE}")
print("Order       : Ascending numerical filename order")
print("=" * 72)


# ============================================================
# BATCH PROCESS
# ============================================================

success_count = 0
skipped_count = 0
failed_count = 0
start_time = time.time()

for idx, fname in enumerate(filtered_files, 1):
    in_path = INPUT_DIR / fname
    out_path = OUTPUT_DIR / fname

    if (
        not OVERWRITE
        and out_path.is_file()
        and out_path.stat().st_size > 1000
    ):
        print(
            f"[{idx}/{len(filtered_files)}] {fname} -> "
            "ALREADY PROCESSED (Skipping)"
        )
        skipped_count += 1
        continue

    file_size_mb = in_path.stat().st_size / (1024 * 1024)
    print(
        f"\n[{idx}/{len(filtered_files)}] Processing {fname} "
        f"({file_size_mb:.1f} MB)...",
        flush=True,
    )

    file_start = time.time()
    ok = process_video(in_path, out_path)
    file_elapsed = time.time() - file_start

    if ok:
        print(
            f"SUCCESS in {file_elapsed:.1f}s -> saved to {out_path}"
        )
        success_count += 1
    else:
        print(f"FAILED: {fname}")
        failed_count += 1


# ============================================================
# FINAL SUMMARY
# ============================================================

total_elapsed = time.time() - start_time

print("\n" + "=" * 72)
print("   Batch Processing Complete")
print("=" * 72)
print(f"Total videos completed : {success_count}")
print(f"Already completed      : {skipped_count}")
print(f"Failed                 : {failed_count}")
print(
    f"Total time elapsed     : {total_elapsed:.1f}s "
    f"({total_elapsed / 60:.1f} minutes)"
)
print(f"Output folder          : {OUTPUT_DIR}")
print("=" * 72)
