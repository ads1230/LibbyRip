#!/usr/bin/env python3
"""Local, consent-based Libby loan metadata handoff for macOS Chrome.

Receives only non-secret loan references from an explicitly clicked Chrome
extension. Never authenticates to Libby, fetches chapters or removes DRM.
Optionally launches the official ACSM -> Adobe Digital Editions handoff watcher.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP = Path.home() / ".local" / "share" / "libby-handoff"
CONFIG = Path.home() / ".config" / "libby-handoff"
KEY_FILE = CONFIG / "pairing-key"
LOANS_FILE = APP / "loans.json"
ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}$")
LOAN_PATH_RE = re.compile(r"^/open/loan/[0-9]+/[0-9]+/?$")
MAX_REQUEST_BYTES = 8192


def private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def private_write(path: Path, value: str) -> None:
    private_dir(path.parent)
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(temp, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        temp.unlink(missing_ok=True)


def get_pairing_key() -> str:
    private_dir(CONFIG)
    if KEY_FILE.exists():
        token = KEY_FILE.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", token):
            raise ValueError("Stored pairing key is invalid; repair it locally.")
        return token
    token = secrets.token_urlsafe(32)
    # Exclusive creation avoids accidental overwrite.
    try:
        with os.fdopen(os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
    except FileExistsError:
        return get_pairing_key()
    return token


def validate_loan(payload: dict) -> dict:
    url = payload.get("url", "")
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Missing or invalid Libby loan URL.")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != "libbyapp.com"
        or parts.username or parts.password or parts.port is not None
        or not LOAN_PATH_RE.fullmatch(parts.path)
    ):
        raise ValueError("Open a Libby loan page (https://libbyapp.com/open/loan/...).")
    # Omit query strings/fragments: they could hold private data or session tokens.
    clean_url = "https://libbyapp.com" + parts.path.rstrip("/")
    result = {"url": clean_url, "loan_reference": parts.path.rstrip("/").split("/")[-2:]}
    for field in ("title", "author"):
        value = payload.get(field, "")
        if not isinstance(value, str):
            raise ValueError(field + " must be text.")
        result[field] = " ".join(value.split())[:256]
    result["received_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return result


def load_loans() -> list[dict]:
    if not LOANS_FILE.exists():
        return []
    data = json.loads(LOANS_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Loan metadata file is not a JSON list.")
    return data


class HandoffServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, pairing_key: str):
        super().__init__((host, port), HandoffHandler)
        self.pairing_key = pairing_key
        self.store_lock = threading.Lock()


class HandoffHandler(BaseHTTPRequestHandler):
    server: HandoffServer
    server_version = "LibbyHandoff/0.1"

    def _extension_origin(self) -> str | None:
        origin = self.headers.get("Origin", "")
        return origin if ORIGIN_RE.fullmatch(origin) else None

    def _headers(self, status: int, *, public: bool = False) -> None:
        self.send_response(status)
        origin = self._extension_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def _reply(self, status: int, payload: dict) -> None:
        self._headers(status)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _authorised(self) -> bool:
        origin = self._extension_origin()
        key = self.headers.get("X-Libby-Handoff-Key", "")
        return origin is not None and secrets.compare_digest(key, self.server.pairing_key)

    def do_OPTIONS(self) -> None:
        if self.path != "/api/loan" or not self._extension_origin():
            self._reply(403, {"error": "Extension origin required."})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._extension_origin())
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Libby-Handoff-Key")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self._reply(200, {"ok": True, "service": "libby-handoff", "version": "0.1"})
        else:
            self._reply(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if self.path != "/api/loan":
            self._reply(404, {"error": "Not found."})
            return
        if not self._authorised():
            self._reply(403, {"error": "Extension or pairing key not authorised."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].lower().strip() != "application/json":
            self._reply(415, {"error": "Expected application/json."})
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if not 0 <= size <= MAX_REQUEST_BYTES:
            self._reply(413, {"error": "Invalid request size."})
            return
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object.")
            record = validate_loan(payload)
            with self.server.store_lock:
                loans = load_loans()
                loans = [x for x in loans if x.get("url") != record["url"]]
                loans.append(record)
                private_write(LOANS_FILE, json.dumps(loans[-1000:], indent=2) + "\n")
        except (UnicodeError, json.JSONDecodeError, ValueError, OSError) as exc:
            self._reply(400, {"error": str(exc)})
            return
        print("Received loan metadata:", record["url"], record["title"], flush=True)
        self._reply(201, {"ok": True, "reference": record["loan_reference"], "saved": True})

    def log_message(self, format_string: str, *args) -> None:
        # Avoid logging loan URLs, keys or request data.
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--list", action="store_true", help="Show locally saved loan references")
    parser.add_argument("--show-pairing-key", action="store_true", help="Print the local pairing key")
    parser.add_argument("--watch-official", action="store_true", help="Also watch for official ACSM downloads")
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    try:
        if args.list:
            print(json.dumps(load_loans(), indent=2))
            return 0
        key = get_pairing_key()
        if args.show_pairing_key:
            print(key)
            return 0
        if not 1 <= args.port <= 65535:
            parser.error("--port must be in 1..65535")
        if args.watch_official:
            from official_epub_handoff import watch
            folder = args.downloads.expanduser().resolve()
            if not folder.is_dir():
                parser.error("Downloads directory does not exist.")
            threading.Thread(target=watch, args=(folder, 1.0, False), daemon=True).start()
        with HandoffServer("127.0.0.1", args.port, key) as httpd:
            print("Libby handoff: http://127.0.0.1:" + str(args.port) + "/health")
            print("Pairing key (keep private): " + key)
            print("Loan metadata saved locally to: " + str(LOANS_FILE))
            print("No connections to Libby or OverDrive are made by this server.")
            httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
