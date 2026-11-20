"""Inspect zip contents and view specific files inside the archive."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Inspect zip archive contents")
    parser.add_argument("zip_path", type=Path, help="Path to zip file")
    parser.add_argument("--read", type=str, default=None, help="File path inside zip to display")
    parser.add_argument("--filter", type=str, default=None, help="Filter file names by substring")
    args = parser.parse_args()

    if not args.zip_path.is_file():
        print(f"Error: {args.zip_path} not found", file=sys.stderr)
        sys.exit(1)

    with zipfile.ZipFile(args.zip_path) as zf:
        if args.read:
            matched = [n for n in zf.namelist() if n == args.read or n.endswith(args.read)]
            if not matched:
                print(f"Error: File '{args.read}' not found in zip.", file=sys.stderr)
                sys.exit(1)
            target = matched[0]
            print(f"=== {target} ===")
            content = zf.read(target).decode("utf-8", errors="replace")
            print(content)
        else:
            names = zf.namelist()
            if args.filter:
                names = [n for n in names if args.filter in n]
            print(f"Entries in {args.zip_path.name} (total {len(names)}):")
            for name in names:
                info = zf.getinfo(name)
                print(f"  {info.file_size:8d}  {name}")


if __name__ == "__main__":
    main()
