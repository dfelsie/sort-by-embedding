#!/usr/bin/env python3
import os
import re
import sys

def strip_numeric_prefix(folder):
    """
    Rename all files in `folder` by removing a leading NN_ prefix if present.
    E.g. '03_myimage.png' → 'myimage.png'.
    """
    prefix_re = re.compile(r'^(\d+_)')
    for name in os.listdir(folder):
        old = os.path.join(folder, name)
        if not os.path.isfile(old):
            continue

        m = prefix_re.match(name)
        if not m:
            continue  # no numeric prefix

        new_name = name[m.end():]
        new = os.path.join(folder, new_name)

        # Avoid clobbering an existing file
        if os.path.exists(new):
            print(f"Skipping {name}: target {new_name} already exists")
            continue

        print(f"Renaming: {name} → {new_name}")
        os.rename(old, new)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/image/folder")
        sys.exit(1)
    strip_numeric_prefix(sys.argv[1])
