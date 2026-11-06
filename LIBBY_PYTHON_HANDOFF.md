# Libby → Python handoff (experimental)

This branch adds a **separate, intentionally limited** Chrome-to-Python bridge:

- `chrome-extension/` provides a small Chrome extension popup that reads **only the active tab's URL and browser title** by default. An optional **Read visible title / author** button extracts standard metadata and visible headings when clicked. You can review/edit both fields before **Send**.
- `tools/libby_handoff_server.py` receives that metadata on **127.0.0.1:8765**, validates the loan URL, and stores it in `~/.local/share/libby-handoff/loans.json`.
- `tools/official_epub_handoff.py` (inherited from the previous branch) optionally watches for **official** ACSM loan downloads and opens them in Adobe Digital Editions.

This is **not yet a fully automatic ebook downloader**. It does not scrape reader pages, retrieve ebooks directly, transfer authentication, decrypt content, or bypass access restrictions. The Chrome extension does not inject any script into Libby.

## macOS installation

A small local setup is unavoidable because GitHub cannot install a Chrome extension or start a Python server on your Mac.

1. Save this GitHub branch via **Code → Download ZIP**, unzip it, and open Terminal in the unzipped folder. Alternatively clone the `feature/libby-python-handoff` branch.
2. Start the server using Python 3:

   ```bash
   python3 tools/libby_handoff_server.py
   ```

   It prints a local **pairing key**. Keep it private. The server binds only to `127.0.0.1`, and never calls the Libby website.
3. In Chrome open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked**, and select the downloaded `chrome-extension` folder.
4. Turn off original and experimental LibreGRAB userscripts in Tampermonkey.
5. Open your borrowed title's normal Libby loan page at `https://libbyapp.com/open/loan/...`.
6. Click the **Libby → Python Handoff** Chrome extension icon. Optionally click **Read visible title / author** to populate the fields (read-only extraction from the visible page, no reader iframe access). Review/edit the URL/title/author, paste the pairing key and click **Send to local Python**.
7. Return to Terminal to see the receipt; no chapter content will be fetched.

### Commands

```bash
python3 tools/libby_handoff_server.py --list
python3 tools/libby_handoff_server.py --show-pairing-key
python3 tools/libby_handoff_server.py --watch-official
python3 tools/official_epub_handoff.py --latest
python3 tools/loan_catalog.py --list
python3 tools/loan_catalog.py --scan ~/Downloads
python3 tools/loan_catalog.py --link ~/Downloads/your-loan.acsm --loan https://libbyapp.com/open/loan/123/456
python3 tools/loan_catalog.py --open --dry-run --loan https://libbyapp.com/open/loan/123/456
python3 -m unittest discover -s tests -p 'test*.py' -v
```

### Explicit loan-to-file association

Python can now track which official ACSM belongs to a particular loan, **but only after you explicitly link the file** using `tools/loan_catalog.py --link FILE --loan URL`. It will never guess based on filenames, automatically bind an unverified file, or download content itself. `--list` shows `awaiting_official_acsm`, `official_acsm_linked`, or `linked_file_missing_or_changed`. `--scan DIRECTORY` lists candidate ACSM files without changing your records. `--open --loan URL` verifies the file hash before opening it in Adobe Digital Editions; add `--dry-run` for a safe check. Use `--replace` to change an existing association, or `--unlink --loan URL` to forget it without deleting files. Metadata and associations are stored privately on this Mac. This is a conservative identity check, not a claim that the ACSM file genuinely belongs to the loan—only the user can verify that from the official download flow.

For `--watch-official`, select Libby's supported EPUB download option manually when eligible. Your browser downloads an ACSM licence file, and Adobe Digital Editions fulfils it. ADE requires appropriate authorisation and loans retain their access restrictions.

### Security notes

- Chrome sends a URL **without query string or fragment**, plus manually reviewed title and author.
- The server rejects non-Libby loan URLs, requires a per-install pairing key, only accepts `chrome-extension://` origins and limits request size.
- The pairing key is stored in Chrome's **local** extension storage, not Chrome sync. Keep it private.
- The optional metadata reader is initiated only by clicking a button, uses Chrome's temporary `activeTab` permission, and does not inspect cookies, account storage, or embedded chapter iframes.
- GitHub Actions validates Python syntax, JavaScript syntax, and localhost-only HTTP tests. The workflow must run and pass before this can be described as CI-verified.
- The receiver stores loan metadata only, with restricted local file permissions on macOS/POSIX.
- This is a local development tool and not a hardened, audited security service. Do not expose the port to your network or internet.
- To clear loan records, stop the service and delete `~/.local/share/libby-handoff/loans.json`.
- To re-pair, stop the service, delete `~/.config/libby-handoff/pairing-key` and clear/reinstall the Chrome extension.

### Limitations

The publisher may restrict a library account regardless of how an export is attempted. Merely using Python instead of JavaScript does not create a guaranteed safe route for automated content retrieval. This extension does not attempt to circumvent those controls.

**Current state:** Static code, offline unit/HTTP integration tests, and a GitHub Actions workflow are provided; end-to-end Chrome/ADE testing has not been performed. The main LibreGRAB script is unchanged.
