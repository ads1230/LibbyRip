#!/usr/bin/env python3
"""Manually match an official ACSM file to a Libby loan received from Chrome.

Does not download books, access Libby, remove DRM or infer filenames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import libby_handoff_server as bridge
from official_epub_handoff import open_in_ade

LINKS_FILE = bridge.APP / "acsm_links.json"


def read_links() -> dict:
    if not LINKS_FILE.exists():
        return {}
    data = json.loads(LINKS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid links file.")
    return data


def loan_url(url: str) -> str:
    canonical = bridge.validate_loan({"url": url})["url"]
    if not any(loan.get("url") == canonical for loan in bridge.load_loans()):
        raise ValueError("That loan has not been transferred from Chrome yet.")
    return canonical


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_file(path: Path) -> Path:
    path = path.expanduser()
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".acsm":
        raise ValueError("Select an existing, regular .acsm file.")
    if not path.stat().st_size:
        raise ValueError("The ACSM file is empty.")
    return path.resolve()


def link(url: str, path: Path, replace: bool = False) -> dict:
    url = loan_url(url)
    path = check_file(path)
    digest = file_hash(path)
    links = read_links()
    if any(key != url and value.get("sha256") == digest for key, value in links.items()):
        raise ValueError("This file is already assigned to another loan.")
    if url in links and links[url].get("sha256") != digest and not replace:
        raise ValueError("This loan already has a file. Supply --replace to change it.")
    record = {
        "filename": path.name,
        "path": str(path),
        "sha256": digest,
        "linked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    links[url] = record
    bridge.private_write(LINKS_FILE, json.dumps(links, indent=2) + "\n")
    return record


def verified_path(url: str) -> Path:
    url = loan_url(url)
    record = read_links().get(url)
    if not record:
        raise ValueError("No official file has been linked to this loan.")
    path = check_file(Path(record["path"]))
    if file_hash(path) != record["sha256"]:
        raise ValueError("The ACSM file changed after linking.")
    return path


def status() -> list[dict]:
    links = read_links()
    out = []
    for loan in bridge.load_loans():
        url = loan["url"]
        state = "awaiting_official_acsm"
        filename = ""
        if url in links:
            try:
                path = verified_path(url)
                filename = path.name
                state = "official_acsm_linked"
            except (ValueError, OSError, KeyError):
                state = "linked_file_missing_or_changed"
        out.append({
            "url": url, "title": loan.get("title", ""),
            "author": loan.get("author", ""), "status": state,
            "filename": filename
        })
    return out


def scan(directory: Path) -> list[str]:
    directory = directory.expanduser()
    if not directory.is_dir():
        raise ValueError("Directory does not exist.")
    return sorted(
        p.name for p in directory.iterdir()
        if p.suffix.lower() == ".acsm" and p.is_file() and not p.is_symlink()
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true")
    action.add_argument("--scan", type=Path, metavar="DIRECTORY")
    action.add_argument("--link", type=Path, metavar="FILE")
    action.add_argument("--open", action="store_true")
    action.add_argument("--unlink", action="store_true")
    ap.add_argument("--loan", help="Canonical Libby loan page URL")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        if args.list:
            print(json.dumps(status(), indent=2))
            return
        if args.scan is not None:
            print(json.dumps(scan(args.scan), indent=2))
            return
        if not args.loan:
            ap.error("--loan is required with --link, --open and --unlink")
        if args.link:
            print("Linked:", link(args.loan, args.link, args.replace)["filename"])
        elif args.open:
            open_in_ade(verified_path(args.loan), dry_run=args.dry_run)
        else:
            key = loan_url(args.loan)
            links = read_links()
            links.pop(key, None)
            bridge.private_write(LINKS_FILE, json.dumps(links, indent=2) + "\n")
            print("Link removed. The ACSM file is unchanged.")
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as e:
        ap.exit(1, f"Error: {e}\n")


if __name__ == "__main__":
    main()
