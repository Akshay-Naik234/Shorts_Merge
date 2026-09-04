"""
Video Generation Assembler
==========================

Reads numbered MP4 clips from videos/ and narration.mp3.

Timing rules:
  - Videos 1 through N-1 are never trimmed.
  - The final video is the only video that is trimmed.
  - The final video is trimmed to exactly the remaining time needed for the
    output to end when narration.mp3 ends.
  - No image_display_duration.json or images directory is required.

Audio:
  - Original audio from all MP4 clips is preserved.
  - Narration is mixed with the original clip audio.
  - Original clip audio defaults to 35% volume.

Usage:
    python assembler_final.py
    python assembler_final.py --videos ./videos --audio narration.mp3
"""


import argparse
import json
import sys
from pathlib import Path

# MoviePy 1.0.3 / Pillow compatibility
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy.editor import (
    AudioFileClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
    CompositeAudioClip,
)


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
TARGET_RESOLUTION = (1920, 1080)
EPSILON = 0.05  # 50 ms duration tolerance.
DEFAULT_ORIGINAL_AUDIO_VOLUME = 0.35  # Keep source clip audio audible under narration.


def find_numbered_file(folder: Path, number: int, extensions: set[str]) -> Path | None:
    """Find a numbered file such as 12.mp4 or 12.png."""
    for ext in extensions:
        candidate = folder / f"{number}{ext}"
        if candidate.exists():
            return candidate
    return None


def resize_to_fit(clip, target_w: int, target_h: int):
    """Resize to cover target resolution and center-crop excess."""
    clip_w, clip_h = clip.size
    scale = max(target_w / clip_w, target_h / clip_h)
    new_w = max(1, int(round(clip_w * scale)))
    new_h = max(1, int(round(clip_h * scale)))

    resized = clip.resize((new_w, new_h))
    x_offset = max(0, (new_w - target_w) // 2)
    y_offset = max(0, (new_h - target_h) // 2)

    return resized.crop(
        x1=x_offset,
        y1=y_offset,
        x2=x_offset + target_w,
        y2=y_offset + target_h,
    )


def fit_video_to_duration(clip, target_duration: float, source_name: str = "video"):
    """Force a source clip to target_duration without fragile end-of-file reads.

    If the source is slightly shorter than the JSON duration, grab a safe frame
    from a freshly opened reader and hold that frame for the missing time.
    Reopening the reader avoids MoviePy's common EOF/reader-position failure
    when to_ImageClip() is called after duration probing.
    """
    source_duration = float(clip.duration)

    if source_duration >= target_duration - EPSILON:
        return clip.subclip(0, target_duration)

    missing = target_duration - source_duration
    print(
        f"       Source is {missing:.3f}s shorter than JSON; "
        "holding its last decodable frame."
    )

    # Use a conservative timestamp safely inside the readable portion.
    # Never request the exact final timestamp because MP4 duration metadata
    # can point a few milliseconds beyond the last decodable frame.
    safe_time = max(0.0, source_duration - max(0.05, 2.0 / 30.0))

    source_path = getattr(clip, "filename", None)
    if not source_path:
        raise RuntimeError(f"Could not determine source path for {source_name}")

    frame_reader = None
    try:
        frame_reader = VideoFileClip(str(source_path), audio=False)
        safe_time = min(safe_time, max(0.0, float(frame_reader.duration) - 0.05))
        frame = frame_reader.get_frame(safe_time)
        still = ImageClip(frame).set_duration(missing)
    except Exception as exc:
        raise RuntimeError(
            f"Could not decode a frame from {source_name} while extending it by "
            f"{missing:.3f}s. The MP4 may be damaged or unreadable by FFmpeg. "
            f"Try opening/re-encoding {source_name} with FFmpeg. Original error: {exc}"
        ) from exc
    finally:
        if frame_reader is not None:
            frame_reader.close()

    return concatenate_videoclips([clip, still], method="compose")


def assemble_video(
    audio_path: str,
    videos_dir: str,
    output_path: str,
    fps: int = 30,
    resolution: tuple[int, int] = TARGET_RESOLUTION,
    original_audio_volume: float = DEFAULT_ORIGINAL_AUDIO_VOLUME,
):
    """Concatenate all numbered videos.

    Rules:
      - Videos 1 through N-1 are used at their full source duration.
      - The final video is trimmed so the complete output ends exactly when
        narration.mp3 ends.
      - If videos 1..N-1 are already longer than the narration, the final
        video is not allowed to create extra duration; an error is raised
        because there is no safe way to preserve all earlier videos while
        also ending at the narration duration.
      - Original audio from every video is retained and mixed with narration.
    """
    videos_path = Path(videos_dir)

    if not videos_path.is_dir():
        print(f"Error: Videos directory not found: {videos_dir}")
        sys.exit(1)

    if not Path(audio_path).is_file():
        print(f"Error: Audio file not found: {audio_path}")
        sys.exit(1)

    # Discover numbered videos in numeric order: 1.mp4, 2.mp4, ... N.mp4.
    numbered_videos = []
    for number in range(1, 100000):
        video_file = find_numbered_file(
            videos_path, number, SUPPORTED_VIDEO_EXTENSIONS
        )
        if video_file is None:
            if number == 1:
                continue
            # Stop at the first missing number after discovering at least one.
            if numbered_videos:
                break
            continue
        numbered_videos.append((number, video_file))

    if not numbered_videos:
        print(f"Error: No numbered videos found in '{videos_dir}'.")
        sys.exit(1)

    print(f"\\nFound {len(numbered_videos)} numbered videos.")
    print(f"First video: {numbered_videos[0][1].name}")
    print(f"Final video: {numbered_videos[-1][1].name}")

    print(f"\\nLoading narration: {audio_path}")
    audio = AudioFileClip(audio_path)
    audio_duration = float(audio.duration)
    print(f"  Narration duration: {audio_duration:.3f}s")

    clips = []
    video = None

    try:
        target_w, target_h = resolution

        # Load videos 1..N-1 WITHOUT trimming. Their complete source duration
        # is preserved. Their original audio is also preserved.
        for index, (video_no, video_file) in enumerate(
            numbered_videos[:-1], start=1
        ):
            print(
                f"  [{index}/{len(numbered_videos)}] Loading {video_file.name} "
                f"(FULL duration)"
            )

            clip = VideoFileClip(str(video_file), audio=True)
            clip = resize_to_fit(clip, target_w, target_h)
            clips.append(clip)

            print(f"       Duration: {float(clip.duration):.3f}s")

        # The FINAL video is the only video whose duration is changed.
        final_no, final_video_file = numbered_videos[-1]

        duration_before_final = sum(float(c.duration) for c in clips)
        final_target_duration = audio_duration - duration_before_final

        print(f"\\nFinal video: {final_video_file.name}")
        print(f"  Duration before final video: {duration_before_final:.3f}s")
        print(f"  Narration duration: {audio_duration:.3f}s")
        print(f"  Required final-video duration: {final_target_duration:.3f}s")

        if final_target_duration <= EPSILON:
            raise RuntimeError(
                "The narration is not long enough to contain videos 1..N-1. "
                f"Those videos already total {duration_before_final:.3f}s, "
                f"while narration is only {audio_duration:.3f}s. "
                "The script only trims the final video and never trims earlier videos."
            )

        final_source = VideoFileClip(str(final_video_file), audio=True)
        final_source_duration = float(final_source.duration)

        if final_source_duration < final_target_duration - EPSILON:
            final_source.close()
            raise RuntimeError(
                f"Final video {final_video_file.name} is too short. "
                f"It is {final_source_duration:.3f}s, but "
                f"{final_target_duration:.3f}s is required to reach the end "
                "of narration without trimming earlier videos."
            )

        # ONLY the final video is trimmed.
        final_clip = final_source.subclip(0, final_target_duration)
        final_clip = resize_to_fit(final_clip, target_w, target_h)
        clips.append(final_clip)

        print(
            f"  Final source duration: {final_source_duration:.3f}s -> "
            f"trimmed to exactly {final_target_duration:.3f}s"
        )

        print(f"\\nConcatenating {len(clips)} clips...")
        video = concatenate_videoclips(clips, method="compose")

        # Make the final duration exactly the narration duration.
        # This is only a tiny floating-point correction and does not trim
        # videos 1..N-1.
        visual_duration = float(video.duration)
        if abs(visual_duration - audio_duration) > EPSILON:
            video = video.set_duration(audio_duration)
            visual_duration = float(video.duration)

        final_audio_duration = min(audio_duration, visual_duration)
        narration_track = audio.subclip(0, final_audio_duration)

        # Mix all original video audio with narration.
        if video.audio is not None:
            source_audio = video.audio.volumex(original_audio_volume)
            mixed_audio = CompositeAudioClip([
                source_audio,
                narration_track.volumex(1.0),
            ]).set_duration(final_audio_duration)

            video = video.set_audio(mixed_audio)

            print(
                f"  Original clip audio: ENABLED "
                f"(volume {original_audio_volume:.2f})"
            )
            print("  Narration: ENABLED (volume 1.00)")
        else:
            video = video.set_audio(narration_track)
            print("  Original clip audio: none detected; narration only.")

        print(f"\\nFINAL video duration: {float(video.duration):.3f}s")
        print(f"FINAL narration duration: {final_audio_duration:.3f}s")

        print(f"\\nWriting video to: {output_path}")
        print(f"  Resolution: {resolution[0]}x{resolution[1]}")
        print(f"  FPS: {fps}")

        video.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            logger="bar",
        )

        print(f"\\nDone! Video saved to: {output_path}")

    finally:
        if video is not None:
            video.close()

        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

        audio.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Video assembler — numbered MP4 clips + narration. "
            "Videos 1..N-1 keep their full duration; only the final video "
            "is trimmed to make the output end exactly with narration."
        )
    )
    parser.add_argument("--audio", "-a", default="narration.mp3")
    parser.add_argument("--videos", "-v", default="./videos")
    parser.add_argument("--output", "-o", default="output.mp4")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--resolution", "-r", default="1920x1080")
    parser.add_argument(
        "--original-audio-volume",
        type=float,
        default=DEFAULT_ORIGINAL_AUDIO_VOLUME,
        help=(
            "Volume of audio embedded in the video clips (0.0-1.0). "
            "Default: 0.35"
        ),
    )

    args = parser.parse_args()

    try:
        w, h = args.resolution.lower().split("x")
        resolution = (int(w), int(h))
    except ValueError:
        print(f"Error: Invalid resolution '{args.resolution}'. Use WIDTHxHEIGHT.")
        sys.exit(1)

    if not 0.0 <= args.original_audio_volume <= 1.0:
        print("Error: --original-audio-volume must be between 0.0 and 1.0.")
        sys.exit(1)

    for path, kind in [
        (args.audio, "Audio file"),
        (args.videos, "Videos directory"),
    ]:
        if not Path(path).exists():
            print(f"Error: {kind} not found: {path}")
            sys.exit(1)

    assemble_video(
        audio_path=args.audio,
        videos_dir=args.videos,
        output_path=args.output,
        fps=args.fps,
        resolution=resolution,
        original_audio_volume=args.original_audio_volume,
    )


if __name__ == "__main__":
    main()
