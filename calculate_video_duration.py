"""
Video Duration Calculator
=========================

Calculates the total duration of all numbered videos in ./videos.

Expected structure:
    project/
    ├── calculate_video_duration.py
    └── videos/
        ├── 1.mp4
        ├── 2.mp4
        ├── 3.mp4
        └── ...

Usage:
    python calculate_video_duration.py

Optional:
    python calculate_video_duration.py --videos ./videos
"""

import argparse
from pathlib import Path

from moviepy.editor import VideoFileClip


SUPPORTED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
}


def format_duration(seconds: float) -> str:
    """Convert seconds into HH:MM:SS.mmm format."""
    total_ms = round(seconds * 1000)

    hours = total_ms // 3_600_000
    total_ms %= 3_600_000

    minutes = total_ms // 60_000
    total_ms %= 60_000

    secs = total_ms // 1_000
    milliseconds = total_ms % 1_000

    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def find_numbered_videos(folder: Path):
    """Find videos named 1.mp4, 2.mp4, 3.mp4, etc."""
    videos = []

    for file in folder.iterdir():
        if not file.is_file():
            continue

        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            number = int(file.stem)
        except ValueError:
            continue

        if number > 0:
            videos.append((number, file))

    videos.sort(key=lambda item: item[0])
    return videos


def calculate_total_duration(videos_dir: str):
    videos_path = Path(videos_dir)

    if not videos_path.is_dir():
        print(f"Error: Videos directory not found: {videos_dir}")
        return

    videos = find_numbered_videos(videos_path)

    if not videos:
        print(f"No numbered videos found in: {videos_dir}")
        return

    total_duration = 0.0

    print("\nVideo durations")
    print("=" * 60)

    for number, video_file in videos:
        clip = None

        try:
            clip = VideoFileClip(str(video_file), audio=False)
            duration = float(clip.duration)
            total_duration += duration

            print(
                f"{number}. {video_file.name:<25} "
                f"{duration:>10.3f} sec   "
                f"{format_duration(duration)}"
            )

        except Exception as exc:
            print(f"{number}. {video_file.name:<25} ERROR: {exc}")

        finally:
            if clip is not None:
                clip.close()

    print("=" * 60)
    print(f"Number of videos : {len(videos)}")
    print(f"Total seconds    : {total_duration:.3f}")
    print(f"Total duration   : {format_duration(total_duration)}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Calculate the total duration of numbered videos."
    )

    parser.add_argument(
        "--videos",
        "-v",
        default="./videos",
        help="Videos directory. Default: ./videos",
    )

    args = parser.parse_args()
    calculate_total_duration(args.videos)


if __name__ == "__main__":
    main()
