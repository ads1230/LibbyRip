# Official Libby EPUB handoff (macOS)

This helper is deliberately separate from LibreGRAB. It does **not** download chapters, automate browsing, bypass lending limits, remove DRM, or authenticate to Libby. It only opens locally downloaded **ACSM** loan files in **Adobe Digital Editions (ADE)**, which fulfils eligible library EPUB/PDF loans through the supported process.

## Setup

1. Install Adobe Digital Editions from Adobe and authorise it as required by your library.
2. In Libby, open **Shelf → Loans → Manage Loan → Read With → Other Options** and use the official **EPUB** option where available. Your browser will typically download an `.acsm` file, not a complete EPUB.
3. On macOS, run one of the commands below from a local checkout of this repository. Only Python 3 is required.

```bash
python3 tools/official_epub_handoff.py --latest
python3 tools/official_epub_handoff.py --file ~/Downloads/book.acsm
python3 tools/official_epub_handoff.py --watch
python3 tools/official_epub_handoff.py --latest --dry-run
```

- `--latest` opens the newest ACSM in `~/Downloads`.
- `--file` opens a specific ACSM.
- `--watch` monitors `~/Downloads` and opens only *new* ACSM files once their size and modification timestamp are stable across two polls. Stop with Ctrl+C.
- `--directory` changes the folder for `--latest` or `--watch`. `--dry-run` shows intended actions without launching ADE.

**BOOX:** Transfer only files the library's lending terms and DRM permit. Many library loans are time-limited and protected. ADE authorisation is not a DRM-removal mechanism, and an ADE-protected EPUB is not guaranteed to work on every BOOX app.

## Why this does not trigger the userscript issue

The utility does not inject code into a Libby page or issue requests to OverDrive. It cannot guarantee that the library will not apply restrictions to an account, but its own actions do not resemble the LibreGRAB chapter-scraping flow.

For the experimental userscript work, see PR #1. Do not run the experimental script alongside this helper.
