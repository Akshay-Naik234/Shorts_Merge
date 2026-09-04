"""
Remove leading zeros from numeric MP4 filenames.

Examples:
    001.mp4  -> 1.mp4
    002.mp4  -> 2.mp4
    010.mp4  -> 10.mp4
    100.mp4  -> 100.mp4

Usage:
    python remove_leading_zeros_videos.py
    python remove_leading_zeros_videos.py videos
"""

import os
import sys


def remove_leading_zeros(folder_path="videos"):
    """Rename numeric MP4 filenames by removing leading zeros."""

    if not os.path.isdir(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    files = [
        f for f in os.listdir(folder_path)
        if os.path.isfile(os.path.join(folder_path, f))
    ]

    if not files:
        print("No files found.")
        return

    print(f"Found {len(files)} file(s).\n")

    rename_list = []

    for filename in files:
        name, ext = os.path.splitext(filename)

        # Only process MP4 files
        if ext.lower() != ".mp4":
            print(f"Skipping: {filename}")
            continue

        # Skip non-numeric filenames
        if not name.isdigit():
            print(f"Skipping: {filename}")
            continue

        # Convert to int to remove leading zeros
        new_name = f"{int(name)}{ext}"

        if filename != new_name:
            rename_list.append((filename, new_name))

    # Rename files
    for old_name, new_name in rename_list:
        old_path = os.path.join(folder_path, old_name)
        new_path = os.path.join(folder_path, new_name)

        if os.path.exists(new_path):
            print(
                f"Skipping '{old_name}' -> '{new_name}' "
                f"(already exists)"
            )
            continue

        os.rename(old_path, new_path)
        print(f"Renamed: {old_name} -> {new_name}")

    print("\nDone!")


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "videos"
    remove_leading_zeros(folder)
