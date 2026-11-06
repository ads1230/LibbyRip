'use strict';

const byId = id => document.getElementById(id);
const status = message => { byId('status').textContent = message; };
const LOAN_PATTERN = /^https:\/\/libbyapp\.com\/open\/loan\/\d+\/\d+\/?(?:[?#].*)?$/;

async function init() {
    const stored = await chrome.storage.local.get(['pairingKey']);
    if (stored.pairingKey) byId('key').value = stored.pairingKey;
    const tabs = await chrome.tabs.query({active: true, currentWindow: true});
    const active = tabs && tabs[0];
    const url = active && active.url || '';
    if (!LOAN_PATTERN.test(url)) {
        status('Open a book loan page at libbyapp.com/open/loan/... first.');
        byId('send').disabled = true;
        byId('detect').disabled = true;
        return;
    }
    const parsed = new URL(url);
    // Never transfer query parameters or fragments that may contain secrets.
    byId('url').value = parsed.origin + parsed.pathname.replace(/\/$/, '');
    const title = String(active.title || '').replace(/\s*[|–—-]\s*Libby\s*$/i, '').trim();
    byId('title').value = title === 'Libby' ? '' : title.slice(0, 256);
}

// Optional, user-triggered read of visible loan metadata. No reader hooks.
byId('detect').addEventListener('click', async () => {
    byId('detect').disabled = true;
    status('Checking visible loan details…');
    try {
        const tabs = await chrome.tabs.query({active: true, currentWindow: true});
        const tab = tabs && tabs[0];
        if (!tab || !tab.id || !LOAN_PATTERN.test(tab.url || '')) {
            throw new Error('Open an ordinary Libby loan page first.');
        }
        const results = await chrome.scripting.executeScript({
            target: {tabId: tab.id},
            world: 'ISOLATED',
            func: () => {
                const tidy = value => String(value || '').replace(/\s+/g, ' ').trim().slice(0, 256);
                const meta = selector => tidy(document.querySelector(selector)?.getAttribute('content'));
                const text = selector => tidy(document.querySelector(selector)?.textContent);
                // Only standard visible DOM metadata, never the embedded reader.
                const title = meta('meta[property="og:title"]') ||
                    meta('meta[name="twitter:title"]') ||
                    text('main h1') || text('h1') || tidy(document.title);
                const author = meta('meta[name="author"]') ||
                    meta('meta[property="book:author"]') ||
                    text('[itemprop="author"]') ||
                    text('main [data-testid*="author"]');
                return {title, author};
            }
        });
        const extracted = results?.[0]?.result;
        if (!extracted) throw new Error('No readable metadata found on this page.');
        if (extracted.title && extracted.title !== 'Libby') {
            byId('title').value = extracted.title.replace(/\s*[|–—-]\s*Libby\s*$/i, '').slice(0, 256);
        }
        if (extracted.author && !/^https?:\/\//i.test(extracted.author)) {
            byId('author').value = extracted.author.slice(0, 256);
        }
        status('Review the detected details before sending. Any field can be edited.');
    } catch (error) {
        status('Could not detect details automatically: ' + (error?.message || error) +
            '\nYou can enter the title and author manually.');
    } finally {
        byId('detect').disabled = false;
    }
});

byId('sendForm').addEventListener('submit', async event => {
    event.preventDefault();
    byId('send').disabled = true;
    status('Sending to 127.0.0.1…');
    const pairingKey = byId('key').value.trim();
    const data = {
        url: byId('url').value,
        title: byId('title').value.trim().slice(0, 256),
        author: byId('author').value.trim().slice(0, 256),
    };
    try {
        if (!LOAN_PATTERN.test(data.url)) throw new Error('No valid Libby loan selected.');
        if (!pairingKey) throw new Error('Enter the pairing key displayed by Python.');
        const response = await fetch('http://127.0.0.1:8765/api/loan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Libby-Handoff-Key': pairingKey },
            body: JSON.stringify(data),
            cache: 'no-store',
            credentials: 'omit',
            redirect: 'error',
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Local server rejected request.');
        await chrome.storage.local.set({pairingKey});
        status('Saved to Python locally. No protected content was requested.');
    } catch (error) {
        status('Could not transfer: ' + (error && error.message ? error.message : String(error)) +
            '\nCheck that the Python server is running.');
    } finally {
        byId('send').disabled = false;
    }
});

init().catch(error => status('Could not inspect the active tab: ' + error.message));
