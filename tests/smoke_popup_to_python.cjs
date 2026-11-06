#!/usr/bin/env node
/**
 * Cross-language smoke test: ACTUAL Chrome popup.js -> ACTUAL Python server.
 * A simulated Chrome API and a static Libby DOM fixture stand in for Chrome.
 * No HTTP traffic goes to Libby or OverDrive; only 127.0.0.1 is contacted.
 *
 * This does not establish real Chrome-extension compatibility or download
 * capabilities; those require a separate, consensual Mac smoke test.
 */
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const { spawn, execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const serverScript = path.join(root, 'tools', 'libby_handoff_server.py');
const popupScript = fs.readFileSync(path.join(root, 'chrome-extension', 'popup.js'), 'utf8');
const origin = 'chrome-extension://' + 'a'.repeat(32);
const loanUrl = 'https://libbyapp.com/open/loan/123456/987654';
const localBase = 'http://127.0.0.1:8765';

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const nextTick = () => new Promise(resolve => setImmediate(resolve));

async function waitForServer(server) {
    for (let attempt = 0; attempt < 80; ++attempt) {
        if (server.exitCode !== null) throw new Error('Python server exited unexpectedly.');
        try {
            const response = await fetch(localBase + '/health', { signal: AbortSignal.timeout(500) });
            if (response.ok && (await response.json()).ok) return;
        } catch (_) { /* Server is still starting; no external requests */ }
        await delay(100);
    }
    throw new Error('Local Python server did not become healthy.');
}

function createPopup(fakeUrl, pairingKey, calls) {
    const ids = ['url', 'title', 'author', 'key', 'status', 'detect', 'send', 'sendForm'];
    const nodes = Object.fromEntries(ids.map(id => [id, {
        value: '', textContent: '', disabled: false, handlers: {},
        addEventListener(name, handler) { this.handlers[name] = handler; },
    }]));

    const document = {
        title: 'Book Details - Libby',
        getElementById(id) { return nodes[id] || null; },
        querySelector(selector) {
            const metadata = {
                'meta[property="og:title"]': 'Verified Fixture Title',
                'meta[name="author"]': 'Fixture Author',
            };
            if (!(selector in metadata)) return null;
            return {getAttribute() { return metadata[selector]; }, textContent: metadata[selector]};
        },
    };
    const stored = {};
    const chrome = {
        storage: {local: {
            async get() { return {pairingKey: stored.pairingKey}; },
            async set(data) { Object.assign(stored, data); },
        }},
        tabs: {async query() {
            return [{id: 37, url: fakeUrl, title: 'Browser Tab Title | Libby'}];
        }},
        scripting: {async executeScript({func, target, world}) {
            assert.equal(target.tabId, 37);
            assert.equal(world, 'ISOLATED');
            return [{result: func()}];
        }},
    };
    const localFetch = async (url, options) => {
        calls.push({url, options});
        assert.equal(url, localBase + '/api/loan', 'Popup must not call Libby or OverDrive');
        assert.equal(options.credentials, 'omit');
        return fetch(url, {...options, headers: {...options.headers, Origin: origin}});
    };
    const context = {document, chrome, URL, fetch: localFetch, console};
    vm.runInNewContext(popupScript, context, {timeout: 2000, filename: 'popup.js'});
    nodes.key.value = pairingKey;
    return {nodes, stored};
}

async function main() {
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'libby-handoff-smoke-'));
    const env = {...process.env, HOME: temp};
    let server;
    try {
        const key = execFileSync('python3', [serverScript, '--show-pairing-key'], {
            encoding: 'utf8', env, timeout: 5000,
        }).trim();
        assert.ok(key.length > 24, 'Python pairing key created');

        server = spawn('python3', ['-u', serverScript], {
            env, stdio: ['ignore', 'pipe', 'pipe'],
        });
        let errorLog = '';
        server.stderr.on('data', chunk => { errorLog += chunk.toString(); });
        await waitForServer(server);

        const calls = [];
        const popup = createPopup(loanUrl + '?session=DO_NOT_STORE#page', key, calls);
        await nextTick();
        assert.equal(calls.length, 0, 'Opening popup does not make network requests');
        assert.equal(popup.nodes.url.value, loanUrl, 'URL sanitised by popup');
        assert.equal(popup.nodes.send.disabled, false, 'Valid loan enables Send');

        await popup.nodes.detect.handlers.click();
        assert.equal(calls.length, 0, 'Reading visible metadata is local-only');
        assert.equal(popup.nodes.title.value, 'Verified Fixture Title');
        assert.equal(popup.nodes.author.value, 'Fixture Author');

        await popup.nodes.sendForm.handlers.submit({preventDefault() {}});
        assert.equal(calls.length, 1, 'One actual localhost POST on Send');
        assert.match(popup.nodes.status.textContent, /Saved to Python locally/);
        assert.equal(popup.stored.pairingKey, key, 'Pairing key persisted locally');

        const storageFile = path.join(temp, '.local/share/libby-handoff/loans.json');
        const saved = JSON.parse(fs.readFileSync(storageFile, 'utf8'));
        assert.equal(saved.length, 1);
        assert.equal(saved[0].url, loanUrl);
        assert.equal(saved[0].title, 'Verified Fixture Title');
        assert.equal(saved[0].author, 'Fixture Author');
        assert.equal(saved[0].loan_reference.join('/'), '123456/987654');
        assert.equal(fs.readFileSync(storageFile, 'utf8').includes('DO_NOT_STORE'), false);

        popup.nodes.key.value = 'wrong-key';
        popup.nodes.title.value = 'SHOULD_NOT_BE_SAVED';
        await popup.nodes.sendForm.handlers.submit({preventDefault() {}});
        assert.equal(calls.length, 2);
        assert.match(popup.nodes.status.textContent, /Could not transfer/);
        assert.equal(JSON.parse(fs.readFileSync(storageFile, 'utf8'))[0].title, 'Verified Fixture Title');

        const blockedCalls = [];
        const invalid = createPopup('https://example.invalid/', key, blockedCalls);
        await nextTick();
        assert.equal(invalid.nodes.send.disabled, true, 'Other domains blocked');
        assert.equal(invalid.nodes.detect.disabled, true);
        assert.equal(blockedCalls.length, 0);

        assert.equal(errorLog, '', 'Python server produced no traceback');
        console.log('PASS: popup → visible metadata → explicit localhost POST → Python → private JSON');
        console.log('PASS: no external web requests; query strings stripped; wrong key rejected; other sites blocked');
    } finally {
        if (server && server.exitCode === null) {
            server.kill('SIGTERM');
            await Promise.race([
                new Promise(resolve => server.once('exit', resolve)),
                delay(1000),
            ]);
        }
        fs.rmSync(temp, {recursive: true, force: true});
    }
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
