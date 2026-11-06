#!/usr/bin/env python3
"""Open official Libby/OverDrive ACSM loan files in Adobe Digital Editions on macOS.

This tool does not log in, request book chapters, remove DRM, or contact Libby.
Only use ACSM files obtained via Libby's official EPUB/PDF download option.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def acsm_files(directory: Path) -> list[Path]:
    """Return newest-first ACSM files from a local directory."""
    return sorted(
        (
            p for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() == ".acsm"
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def open_in_ade(path: Path, dry_run: bool = False) -> None:
    """Hand a locally downloaded ACSM licence file to Adobe Digital Editions."""
    if not path.is_file() or path.suffix.lower() != ".acsm":
        raise ValueError("Choose an existing .acsm file downloaded from Libby.")
    if path.stat().st_size == 0:
        raise ValueError("The .acsm file is empty.")
    if sys.platform != "darwin" and not dry_run:
        raise RuntimeError("This helper currently supports macOS only.")
    if dry_run:
        print(f"[dry run] Would open in Adobe Digital Editions: {path}")
        return
    try:
        subprocess.run(
            ["open", "-a", "Adobe Digital Editions", str(path.resolve())],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "Could not open Adobe Digital Editions. Install and authorise it "
            "first, then retry."
        ) from exc
    print(f"Sent to Adobe Digital Editions: {path.name}")


def watch(directory: Path, interval: float, dry_run: bool) -> None:
    """Watch for NEW official ACSM downloads; ignore files already present."""
    known = {p.resolve() for p in acsm_files(directory)}
    pending: dict[Path, tuple[int, int]] = {}
    print(f"Watching {directory} for newly downloaded .acsm files.")
    print("Existing files are ignored. Use --file or --latest for those.")
    print("Press Ctrl+C to stop.")
    while True:
        current = acsm_files(directory)
        for path in current:
            key = path.resolve()
            if key in known:
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            snapshot = (stat.st_size, stat.st_mtime_ns)
            if snapshot[0] == 0 or pending.get(key) != snapshot:
                pending[key] = snapshot
                continue
            # File is unchanged across polls. No new web requests are made.
            known.add(key)
            pending.pop(key, None)
            try:
                open_in_ade(path, dry_run)
            except (ValueError, RuntimeError) as exc:
                print(f"Could not import {path.name}: {exc}", file=sys.stderr)
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--file", type=Path, help="Open a previously downloaded .acsm file")
    action.add_argument("--latest", action="store_true", help="Open newest .acsm in Downloads")
    action.add_argument("--watch", action="store_true", help="Watch for new .acsm files")
    parser.add_argument(
        "--directory", type=Path, default=Path.home() / "Downloads",
        help="Folder for --latest/--watch (default: ~/Downloads)"
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Watch poll interval in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without opening ADE")
    args = parser.parse_args()
    try:
        if args.file:
            open_in_ade(args.file.expanduser(), args.dry_run)
        else:
            directory = args.directory.expanduser()
            if not directory.is_dir():
                raise ValueError(f"Directory not found: {directory}")
            if args.latest:
                found = acsm_files(directory)
                if not found:
                    raise ValueError("No .acsm files found. Use Libby's official download option first.")
                open_in_ade(found[0], args.dry_run)
            else:
                if args.interval < 0.25:
                    raise ValueError("--interval must be at least 0.25 seconds.")
                watch(directory, args.interval, args.dry_run)
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
