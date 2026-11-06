# Validation plan: what is tested vs what is still unknown

## Status at this commit

**Automated offline coverage:** Python unit tests, local HTTP integration tests, and a cross-language smoke test that executes the real `chrome-extension/popup.js` against the real Python receiver. The smoke test uses a simulated Chrome API and DOM fixture, not an installed Chrome browser. It makes **no requests to Libby/OverDrive**.

**Not yet validated:** an installed extension on macOS Chrome, integration with Adobe Digital Editions on a real book, or any direct/automatic download of book contents. A green CI build must never be represented as proof of those capabilities.

## Test 1 — deterministic CI

Run GitHub Actions workflow **Libby handoff offline tests** on PR #3, or locally:

```bash
python3 -m unittest discover -s tests -p 'test*.py' -v
node --check chrome-extension/popup.js
node tests/smoke_popup_to_python.cjs
```

The Node smoke test starts a **real Python server** at 127.0.0.1:8765, calls the actual popup code through an in-memory simulated Chrome API, and checks:
- Opening the popup makes **zero network requests**.
- Visible-metadata extraction makes **zero network requests**.
- Clicking Send makes **one localhost POST**.
- The URL's query/fragment are removed, and loan reference/title/author match the saved file.
- A wrong pairing key does not overwrite the local record.
- A non-Libby active tab cannot send.
- No network requests go to Libby/OverDrive.

If port 8765 is in use, the smoke test fails; use an isolated CI environment.

## Test 2 — one-time Mac acceptance test

1. Disable **both** LibreGRAB userscripts in Tampermonkey. Do not open the modified EPUB reader.
2. Install the branch's `chrome-extension` folder via Chrome → Extensions → Developer mode → Load unpacked.
3. Start `python3 tools/libby_handoff_server.py` and keep the printed pairing key private.
4. Open **a normal Libby loan page**, not the embedded reading view. It may be any legitimate existing loan; do not share sensitive account data in screenshots or logs.
5. Click the extension icon. **Expected:** canonical `libbyapp.com/open/loan/...` URL is displayed; no transfer has yet happened.
6. Click **Read visible title / author**. **Expected:** title/author may be populated if page metadata is available, and must be editable. A missing title is a **graceful failure**, not a reason to probe hidden reader data.
7. Paste the pairing key and click **Send to local Python** once. **Expected:** popup confirms save, Python prints receipt, and `python3 tools/libby_handoff_server.py --list` shows one matching loan.
8. **Stop here for the first session.** Do not repeatedly attempt EPUB export as part of this test.

Record only **pass/fail**, Chrome version, Python version and any error text stripped of private tokens. Do not copy library cookies, bearer tokens, entire HAR traces or sensitive URLs into GitHub issues.

## Test 3 — optional official loan-file association

Only if the library offers an official EPUB/PDF download, and you have an eligible loan:

1. Use Libby's ordinary **Read With / Other Options → EPUB/PDF** action.
2. Check that a real `.acsm` file appears in Downloads.
3. Run `python3 tools/loan_catalog.py --scan ~/Downloads`.
4. Manually associate the selected file with the **matching** previously transferred loan:
   ```bash
   python3 tools/loan_catalog.py --link ~/Downloads/your-loan.acsm --loan https://libbyapp.com/open/loan/123/456
   ```
   Replace placeholders with your own exact local values. This is **not** automatic identity verification.
5. Run `python3 tools/loan_catalog.py --list` and confirm **official_acsm_linked**.
6. Run `python3 tools/loan_catalog.py --open --dry-run --loan https://libbyapp.com/open/loan/123/456` to check the handoff without opening ADE.
7. If desired and permitted, repeat the `--open` command without `--dry-run` to launch ADE and confirm the loan is accepted. Mac/ADE authorisation and publisher DRM rules still apply.

## Stop criteria

- Any OverDrive Terms redirect, unusual-activity warning, or access restriction → **stop all export tests** and disable LibreGRAB. Do not automate evasion or increase request frequency.
- Any unexpected request to Libby/OverDrive during the popup-to-Python smoke test → **fail**.
- Any missing metadata, mismatched loan, incorrect file association or invalid token handling → **fail**, investigate locally.
- Green CI + successful Mac handoff means only **metadata transfer is validated**, not direct book downloading.

## Confidence matrix

| Claim | Evidence |
|---|---|
| Python validates and saves loan references | Python unit and localhost HTTP tests |
| The popup's actual JS can exchange metadata with the Python server | Node cross-language test, simulated Chrome API |
| The popup runs correctly in installed macOS Chrome | **Pending one-time Mac test** |
| Official ACSM file can be passed to ADE | Logic/unit tests; **live macOS ADE validation pending** |
| A standalone downloader avoids Libby's restrictions | **Not established** |
