# ============================================================
# WINDOWS VERSION
# Gemini / Veo Watermark Removal
#
# Original engine:
# GeminiWatermarkTool-Windows-x64-Video.zip
#
# This version is for NORMAL WINDOWS EXECUTION.
#
# Run:
#     python watermark.py
#
# Project structure:
#
# Video_Generation/
#     watermark.py
#     videos/
#         1.mp4
#         2.mp4
#         3.mp4
#     output/
#     tools/
#
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

# Automatically use the folder where watermark.py is located.
BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "videos"
OUTPUT_DIR = BASE_DIR / "output"
TOOLS_DIR = BASE_DIR / "tools"

TOOLS_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PROCESS RANGE
#
# None = process all videos
#
# Example:
#
# START = 1
# END   = 10
#
# ============================================================

START = None
END = None


# ============================================================
# EXISTING OUTPUT FILES
#
# False = skip existing output
# True  = process again
# ============================================================

OVERWRITE = False


# ============================================================
# ENGINE MODE
#
# False = normal GPU/engine mode
# True  = CPU mode
#
# ============================================================

USE_CPU = False


# ============================================================
# ORIGINAL DOWNLOAD URL
# ============================================================

TOOL_DOWNLOAD_URL = (
    "https://github.com/allenk/VeoWatermarkRemover/releases/download/"
    "v0.6.5-demo/GeminiWatermarkTool-Windows-x64-Video.zip"
)


# ============================================================
# ENGINE PATH
# ============================================================

ENGINE_EXE = (
    TOOLS_DIR /
    "GeminiWatermarkTool-Video.exe"
)

ZIP_FILE = (
    TOOLS_DIR /
    "gwt_video.zip"
)


# ============================================================
# CHECK WINDOWS
# ============================================================

if os.name != "nt":

    raise RuntimeError(
        "\nThis version is designed for Windows.\n"
        "Do not run it inside Google Colab/Linux."
    )


# ============================================================
# CHECK INPUT DIRECTORY
# ============================================================

if not INPUT_DIR.is_dir():

    raise FileNotFoundError(
        "\nVideos folder not found:\n"
        f"{INPUT_DIR}\n\n"
        "Create a 'videos' folder next to watermark.py "
        "and put your MP4 files inside it."
    )


# ============================================================
# CHECK FFMPEG
# ============================================================

def check_ffmpeg():

    try:

        result = subprocess.run(
            [
                "ffmpeg",
                "-version"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )

        if result.returncode == 0:

            first_line = (
                result.stdout
                .splitlines()[0]
                if result.stdout
                else "FFmpeg detected"
            )

            print(
                f"[FFmpeg] {first_line}"
            )

            return True

    except FileNotFoundError:

        pass


    print()
    print("=" * 72)
    print("ERROR: FFmpeg was not found.")
    print("=" * 72)

    print(
        "\nPlease install FFmpeg and make sure "
        "it is available in Windows PATH."
    )

    print(
        "\nTest with:"
    )

    print(
        "    ffmpeg -version"
    )

    print(
        "\nThen run this script again."
    )

    print("=" * 72)

    return False


if not check_ffmpeg():

    sys.exit(1)


# ============================================================
# NATURAL SORT
# ============================================================

def natural_sort_key(filename):

    parts = re.split(
        r"(\d+)",
        filename
    )

    return [
        int(p)
        if p.isdigit()
        else p.lower()
        for p in parts
    ]


# ============================================================
# GET VIDEO NUMBER
# ============================================================

def get_video_number(filename):

    match = re.search(
        r"\d+",
        Path(filename).stem
    )

    return (
        int(match.group())
        if match
        else None
    )


# ============================================================
# FIND ENGINE
# ============================================================

def find_engine():

    # --------------------------------------------------------
    # Expected location
    # --------------------------------------------------------

    if ENGINE_EXE.exists():

        print(
            f"[Engine] Existing engine found:\n"
            f"          {ENGINE_EXE}"
        )

        return ENGINE_EXE


    # --------------------------------------------------------
    # Search tools folder
    # --------------------------------------------------------

    candidates = list(
        TOOLS_DIR.rglob(
            "GeminiWatermarkTool-Video.exe"
        )
    )

    if candidates:

        source = candidates[0]

        if source != ENGINE_EXE:

            shutil.copy2(
                source,
                ENGINE_EXE
            )

        print(
            f"[Engine] Found existing engine:\n"
            f"          {ENGINE_EXE}"
        )

        return ENGINE_EXE


    return None


# ============================================================
# DOWNLOAD ORIGINAL WINDOWS ENGINE
# ============================================================

def ensure_engine():

    existing = find_engine()

    if existing:

        return existing


    print()
    print("=" * 72)
    print("Downloading ORIGINAL Gemini/Veo Windows engine...")
    print("=" * 72)

    print(
        TOOL_DOWNLOAD_URL
    )

    try:

        urllib.request.urlretrieve(
            TOOL_DOWNLOAD_URL,
            ZIP_FILE
        )

    except Exception as e:

        raise RuntimeError(
            "\nCould not download the "
            "GeminiWatermarkTool package.\n\n"
            f"Error: {e}"
        )


    if not ZIP_FILE.exists():

        raise RuntimeError(
            "Download completed but ZIP file was not created."
        )


    print(
        f"Downloaded: "
        f"{ZIP_FILE.stat().st_size / 1024 / 1024:.2f} MB"
    )


    print(
        "Extracting engine..."
    )


    try:

        with zipfile.ZipFile(
            ZIP_FILE,
            "r"
        ) as zf:

            zf.extractall(
                TOOLS_DIR
            )

    except Exception as e:

        raise RuntimeError(
            f"Could not extract ZIP:\n{e}"
        )


    # --------------------------------------------------------
    # Delete ZIP
    # --------------------------------------------------------

    try:

        ZIP_FILE.unlink()

    except Exception:

        pass


    # --------------------------------------------------------
    # Search recursively
    # --------------------------------------------------------

    candidates = list(
        TOOLS_DIR.rglob(
            "GeminiWatermarkTool-Video.exe"
        )
    )


    if candidates:

        source = candidates[0]

        if source != ENGINE_EXE:

            shutil.copy2(
                source,
                ENGINE_EXE
            )


    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    if not ENGINE_EXE.exists():

        print()
        print(
            "Files extracted from package:"
        )

        for p in TOOLS_DIR.rglob("*"):

            if p.is_file():

                print(
                    " ",
                    p
                )


        raise FileNotFoundError(
            "\nGeminiWatermarkTool-Video.exe "
            "was not found after extraction."
        )


    print(
        f"[Engine] Ready:\n"
        f"          {ENGINE_EXE}"
    )

    return ENGINE_EXE


# ============================================================
# INITIALIZE ENGINE
# ============================================================

ENGINE = ensure_engine()


# ============================================================
# WINDOWS ENGINE COMMAND
#
# IMPORTANT:
# No Wine.
# No apt-get.
# No Linux.
#
# We directly execute:
#
# GeminiWatermarkTool-Video.exe
#
# ============================================================

def engine_command(*args):

    return [
        str(ENGINE),
        *[
            str(x)
            for x in args
        ]
    ]


# ============================================================
# TEST ENGINE
# ============================================================

print()
print("=" * 72)
print("Testing watermark engine...")
print("=" * 72)


test_result = subprocess.run(
    engine_command("--help"),
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    check=False
)


print(
    test_result.stdout[-3000:]
)


if test_result.returncode not in (0, 1):

    print(
        "\nWARNING: Engine returned "
        f"code {test_result.returncode}."
    )


print(
    "Engine test completed."
)


# ============================================================
# PATCH SKIPPED FRAMES
# ============================================================

def check_and_patch_skipped_frames(
    input_video,
    output_video
):

    """
    Detect frames where the watermark-removal engine
    appears to have skipped processing and repair them.

    This uses OpenCV + the original Windows engine.
    """

    try:

        import cv2
        import numpy as np

    except ImportError:

        print(
            "\n[Warning] OpenCV/NumPy not installed."
        )

        print(
            "Installing them..."
        )

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "opencv-python",
                "numpy"
            ],
            check=True
        )

        import cv2
        import numpy as np


    # ========================================================
    # OPEN INPUT / OUTPUT
    # ========================================================

    cap_in = cv2.VideoCapture(
        str(input_video)
    )

    cap_out = cv2.VideoCapture(
        str(output_video)
    )


    if not cap_in.isOpened():

        print(
            "\n[Patch] Could not open input video."
        )

        return True


    if not cap_out.isOpened():

        print(
            "\n[Patch] Could not open output video."
        )

        cap_in.release()

        return True


    # ========================================================
    # VIDEO INFORMATION
    # ========================================================

    w = int(
        cap_in.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    h = int(
        cap_in.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    fps = (
        cap_in.get(
            cv2.CAP_PROP_FPS
        )
        or 24.0
    )


    # ========================================================
    # WATERMARK REGION
    # ========================================================

    if (w, h) == (1280, 720):

        rx = 1136
        ry = 576
        rw = 48
        rh = 48

        alpha_val = 0.60


    elif (w, h) == (1920, 1080):

        rx = 1716
        ry = 884
        rw = 60
        rh = 60

        alpha_val = 0.95


    else:

        rx = int(
            w * 0.89
        )

        ry = int(
            h * 0.80
        )

        rw = int(
            w * 0.04
        )

        rh = int(
            h * 0.06
        )

        alpha_val = 0.60


    # ========================================================
    # COMPARE ORIGINAL / PROCESSED
    # ========================================================

    diffs = []


    while True:

        ri, fi = cap_in.read()

        ro, fo = cap_out.read()


        if not ri or not ro:

            break


        # Safety for unusual resolutions
        if (
            ry + rh > fi.shape[0]
            or
            rx + rw > fi.shape[1]
        ):

            continue


        if (
            ry + rh > fo.shape[0]
            or
            rx + rw > fo.shape[1]
        ):

            continue


        region_in = fi[
            ry:ry + rh,
            rx:rx + rw
        ].astype(float)


        region_out = fo[
            ry:ry + rh,
            rx:rx + rw
        ].astype(float)


        diff = float(
            np.mean(
                np.abs(
                    region_in -
                    region_out
                )
            )
        )


        diffs.append(
            diff
        )


    cap_in.release()
    cap_out.release()


    if not diffs:

        return True


    # ========================================================
    # DYNAMIC THRESHOLD
    # ========================================================

    median_d = float(
        np.median(diffs)
    )


    threshold = max(
        7.0,
        median_d * 0.4
    )


    skipped_indices = [

        i

        for i, d in enumerate(diffs)

        if d < threshold

    ]


    if not skipped_indices:

        return True


    print(
        f"\n[Auto-fixing "
        f"{len(skipped_indices)} "
        f"skipped frame(s)]...",
        end="",
        flush=True
    )


    # ========================================================
    # TEMP DIRECTORY
    # ========================================================

    temp_dir = (
        output_video.parent /
        ".temp_patch"
    )


    temp_dir.mkdir(
        exist_ok=True
    )


    clean_frames = {}


    # ========================================================
    # EXTRACT + REPROCESS SKIPPED FRAMES
    # ========================================================

    cap_in = cv2.VideoCapture(
        str(input_video)
    )


    for f_idx in skipped_indices:

        cap_in.set(
            cv2.CAP_PROP_POS_FRAMES,
            f_idx
        )


        ret, frame = cap_in.read()


        if not ret:

            continue


        raw_path = (
            temp_dir /
            f"frame_{f_idx}_raw.png"
        )


        clean_path = (
            temp_dir /
            f"frame_{f_idx}_clean.png"
        )


        cv2.imwrite(
            str(raw_path),
            frame
        )


        # ====================================================
        # ORIGINAL ENGINE ARGUMENTS
        # ====================================================

        cmd = engine_command(

            "-i",
            raw_path,

            "-o",
            clean_path,

            "--region",
            f"{rx},{ry},{rw},{rh}",

            "--veo-alpha",
            str(alpha_val),

            "--denoise",
            "ai",

            "-f"

        )


        if USE_CPU:

            cmd.append(
                "--cpu"
            )


        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False
        )


        if clean_path.exists():

            clean_frame = cv2.imread(
                str(clean_path)
            )


            if clean_frame is not None:

                clean_frames[
                    f_idx
                ] = clean_frame


            try:

                clean_path.unlink()

            except Exception:

                pass


        try:

            raw_path.unlink()

        except Exception:

            pass


    cap_in.release()


    # ========================================================
    # NOTHING TO PATCH
    # ========================================================

    if not clean_frames:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        return True


    # ========================================================
    # REBUILD VIDEO
    # ========================================================

    temp_out = (
        output_video.parent /
        f".temp_{output_video.name}"
    )


    ffmpeg_cmd = [

        "ffmpeg",

        "-y",

        "-hide_banner",

        "-loglevel",
        "error",

        "-f",
        "rawvideo",

        "-pix_fmt",
        "bgr24",

        "-s",
        f"{w}x{h}",

        "-r",
        str(fps),

        "-i",
        "-",

        "-i",
        str(input_video),

        "-map",
        "0:v:0",

        "-map",
        "1:a?",

        "-c:v",
        "libx264",

        "-preset",
        "fast",

        "-crf",
        "18",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "copy",

        "-shortest",

        str(temp_out)
    ]


    try:

        p = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE
        )


        cap_out = cv2.VideoCapture(
            str(output_video)
        )


        f_idx = 0


        while True:

            ret, frame = cap_out.read()


            if not ret:

                break


            if f_idx in clean_frames:

                frame = clean_frames[
                    f_idx
                ]


            p.stdin.write(
                frame.tobytes()
            )


            f_idx += 1


        cap_out.release()

        p.stdin.close()

        p.wait()


    except Exception as e:

        print(
            f"\n[Patch Error] {e}"
        )

        try:

            p.kill()

        except Exception:

            pass

        shutil.rmtree(
            temp_dir,
            ignore_errors=True
        )

        return False


    shutil.rmtree(
        temp_dir,
        ignore_errors=True
    )


    # ========================================================
    # VERIFY REBUILT VIDEO
    # ========================================================

    if (

        temp_out.exists()

        and

        temp_out.stat().st_size > 1000

    ):

        try:

            if output_video.exists():

                output_video.unlink()

            temp_out.replace(
                output_video
            )

        except Exception as e:

            print(
                f"\n[Patch Replace Error] {e}"
            )

            return False


        return True


    return False


# ============================================================
# PROCESS ONE VIDEO
# ============================================================

def process_video(
    input_video,
    output_video
):

    """
    Main watermark removal.

    Windows:
        GeminiWatermarkTool-Video.exe
            -i input
            -o output
            --veo
            -v
    """

    cmd = engine_command(

        "-i",
        input_video,

        "-o",
        output_video,

        "--veo",

        "-v"

    )


    if USE_CPU:

        cmd.append(
            "--cpu"
        )


    try:

        proc = subprocess.run(

            cmd,

            stdout=subprocess.PIPE,

            stderr=subprocess.STDOUT,

            text=True,

            encoding="utf-8",

            errors="replace",

            check=False

        )


        # ====================================================
        # VERIFY OUTPUT
        # ====================================================

        if (

            proc.returncode == 0

            and

            output_video.exists()

            and

            output_video.stat().st_size > 1000

        ):

            # -----------------------------------------------
            # Always check skipped frames
            # -----------------------------------------------

            check_and_patch_skipped_frames(

                input_video,

                output_video

            )


            return True


        # ====================================================
        # ERROR
        # ====================================================

        print()

        print(
            f"[Warning] Process returned "
            f"code {proc.returncode} "
            f"for {input_video.name}"
        )


        lines = (
            proc.stdout
            .strip()
            .splitlines()
        )


        if lines:

            print(
                "\nLast engine messages:"
            )


            for line in lines[-20:]:

                print(
                    " ",
                    line
                )


        return False


    except Exception as exc:

        print(
            f"\n[Error] Exception during "
            f"processing "
            f"{input_video.name}: "
            f"{exc}"
        )

        return False


# ============================================================
# FIND VIDEOS
# ============================================================

all_files = [

    f

    for f in os.listdir(
        INPUT_DIR
    )

    if f.lower().endswith(".mp4")

]


all_files.sort(
    key=natural_sort_key
)


if not all_files:

    print(
        f"\nNo .mp4 files found in:\n"
        f"{INPUT_DIR}"
    )

    raise SystemExit(0)


# ============================================================
# FILTER RANGE
# ============================================================

filtered_files = []


for f in all_files:

    number = get_video_number(
        f
    )


    if number is not None:

        if (

            START is not None

            and

            number < START

        ):

            continue


        if (

            END is not None

            and

            number > END

        ):

            continue


    filtered_files.append(
        f
    )


# ============================================================
# DISPLAY CONFIG
# ============================================================

print()
print("=" * 72)
print("   WINDOWS GEMINI / VEO WATERMARK REMOVAL")
print("=" * 72)

print(
    "Engine      : "
    "GeminiWatermarkTool-Video.exe"
)

print(
    "Execution   : "
    "Native Windows"
)

print(
    f"Videos Path : "
    f"{INPUT_DIR}"
)

print(
    f"Output Path : "
    f"{OUTPUT_DIR}"
)

print(
    f"Videos      : "
    f"{len(filtered_files)}"
)

print(
    "Processing   : "
    "Reverse Alpha / AI Denoise"
)

print(
    f"Mode        : "
    f"{'CPU' if USE_CPU else 'Normal Engine Mode'}"
)

print(
    f"Overwrite   : "
    f"{OVERWRITE}"
)

print("=" * 72)


# ============================================================
# BATCH PROCESS
# ============================================================

success_count = 0
skipped_count = 0
failed_count = 0

start_time = time.time()


for idx, fname in enumerate(
    filtered_files,
    1
):

    in_path = (
        INPUT_DIR /
        fname
    )


    out_path = (
        OUTPUT_DIR /
        fname
    )


    # ========================================================
    # SKIP EXISTING
    # ========================================================

    if (

        not OVERWRITE

        and

        out_path.is_file()

        and

        out_path.stat().st_size > 1000

    ):

        print(
            f"[{idx}/{len(filtered_files)}] "
            f"{fname} -> "
            f"ALREADY PROCESSED "
            f"(Skipping)"
        )

        skipped_count += 1

        continue


    file_size_mb = (

        in_path.stat().st_size

        /

        (1024 * 1024)

    )


    print(
        f"\n[{idx}/{len(filtered_files)}] "
        f"Processing {fname} "
        f"({file_size_mb:.1f} MB)...",
        flush=True
    )


    file_start = time.time()


    ok = process_video(

        in_path,

        out_path

    )


    file_elapsed = (

        time.time()

        -

        file_start

    )


    if ok:

        print(
            f"SUCCESS "
            f"in {file_elapsed:.1f}s "
            f"-> saved to "
            f"{out_path}"
        )

        success_count += 1


    else:

        print(
            "FAILED!"
        )

        failed_count += 1


# ============================================================
# FINAL SUMMARY
# ============================================================

total_elapsed = (

    time.time()

    -

    start_time

)


print()
print("=" * 72)
print("   Batch Processing Complete")
print("=" * 72)

print(
    f"Total videos completed : "
    f"{success_count}"
)

print(
    f"Already completed      : "
    f"{skipped_count}"
)

print(
    f"Failed                 : "
    f"{failed_count}"
)

print(
    f"Total time elapsed     : "
    f"{total_elapsed:.1f}s "
    f"({total_elapsed / 60:.1f} minutes)"
)

print(
    f"Output folder          : "
    f"{OUTPUT_DIR}"
)

print("=" * 72)