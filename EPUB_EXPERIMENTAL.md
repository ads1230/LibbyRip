# Experimental EPUB reader branch

This branch adds **libregrab-epub.user.js**, a separate EPUB-only Tampermonkey userscript. The existing **userscript.js** and **main** branch are unchanged.

## Install in Chrome

1. Disable the existing LibreGRAB script in Tampermonkey before installing this variant (avoid competing modifications).
2. Open the **raw** file on the `fix/epub-reader` branch at:
   https://raw.githubusercontent.com/ads1230/LibbyRip/fix/epub-reader/libregrab-epub.user.js
3. Tampermonkey may offer an install dialog for the `.user.js` URL. If not, select **Dashboard → Utilities → Install from URL** and paste the raw URL.
4. Verify the installed title is **LibreGRAB EPUB (ads1230 experimental)**.
5. The new variant matches only eBook reader frames (not audiobooks). Do not enable it simultaneously with the original script.

## Changes and provenance

- Based on the in-review EPUB overhaul at [upstream PR #79](https://github.com/PsychedelicPalimpsest/LibbyRip/pull/79), including chapter shell handling, EPUB metadata and asset improvements.
- EPUB-only matching avoids the original audiobook-specific JSON.parse override.
- Loads one missing chapter at a time, with a 20-second per-chapter/120-second overall bound rather than launching all missing chapters concurrently.
- Stops on a detected Terms/restriction page or unexpected chapter API and reports failures.
- Requests the client-zip library only when archive generation begins.
- Uses a unique Tampermonkey name/namespace and removes the Greasy Fork auto-update links.

## Limits and risks

**Experimental and not validated with an actual Libby loan.** Static JavaScript syntax was checked; live runtime, EPUBCheck and cross-browser tests have not been performed. A Terms redirect may indicate platform restrictions; this script does not attempt to bypass those restrictions. Do not repeatedly export when redirected, warned, or restricted. Your library's terms and applicable copyright rules remain in force.

This file contains changes from third-party contributors under the repository's MIT licence. Review the open pull request before merging into main.
