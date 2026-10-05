import os
import re

FOLDER = "videos"

# ------------------------------------------------------------
# NATURAL SORT
# ------------------------------------------------------------

def natural_sort_key(filename):
    parts = re.split(r'(\d+)', filename)

    return [
        int(part) if part.isdigit() else part.lower()
        for part in parts
    ]


# ------------------------------------------------------------
# GET NUMBER FROM FILENAME
# ------------------------------------------------------------

def get_number(filename):
    match = re.search(r'\d+', filename)

    if match:
        return int(match.group())

    return None


# ------------------------------------------------------------
# GET MP4 FILES
# ------------------------------------------------------------

files = [
    f for f in os.listdir(FOLDER)
    if f.lower().endswith(".mp4")
]

# ------------------------------------------------------------
# SORT FIRST
# ------------------------------------------------------------

files.sort(key=natural_sort_key)

print("Sorted files:")
for f in files:
    print(" ", f)

print("\nRenaming...\n")


# ------------------------------------------------------------
# FIRST PASS:
# Rename to temporary names to avoid conflicts
# ------------------------------------------------------------

temp_files = []

for index, filename in enumerate(files):

    number = get_number(filename)

    if number is None:
        print(f"Skipped: {filename}")
        continue

    temp_name = f"__temp_{index:06d}.mp4"
    temp_path = os.path.join(FOLDER, temp_name)

    old_path = os.path.join(FOLDER, filename)

    os.rename(old_path, temp_path)

    temp_files.append(
        (temp_path, filename, number)
    )


# ------------------------------------------------------------
# SECOND PASS:
# Subtract 9 AFTER sorting
# ------------------------------------------------------------

for temp_path, original_name, number in temp_files:

    new_number = number - 4

    new_name = f"{new_number}.mp4"

    new_path = os.path.join(
        FOLDER,
        new_name
    )

    os.rename(
        temp_path,
        new_path
    )

    print(
        f"{original_name}  ->  {new_name}"
    )


print("\nDone.")