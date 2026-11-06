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
        return;
    }
    const parsed = new URL(url);
    // Never transfer query parameters or fragments that may contain secrets.
    byId('url').value = parsed.origin + parsed.pathname.replace(/\/$/, '');
    const title = String(active.title || '').replace(/\s*[|–—-]\s*Libby\s*$/i, '').trim();
    byId('title').value = title === 'Libby' ? '' : title.slice(0, 256);
}

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
