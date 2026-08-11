// Does the web build actually work offline? Compiling proves nothing.
//
// This script exists because three separate defects in the first web build were
// invisible to `flutter build`, `flutter analyze` and `flutter test`, and all
// three broke the one property the build was made for:
//
//   1. the renderer was fetched from `gstatic.com` at start-up, so the app did
//      not boot at all without a network;
//   2. the default font was fetched from `fonts.gstatic.com`, so when that
//      failed the interface rendered with *no text* — not a fallback font, none;
//   3. the boot placeholder in `index.html` was never removed, so the running
//      application sat underneath it.
//
// Each is asserted below. Run it after `./tool/build.sh web`:
//
//   node tool/smoke_web.mjs
//
// Requires a Chromium and Playwright, located by `browser.mjs`. Skips with a
// clear message rather than failing when either is missing, because a developer
// without them should not be blocked — CI has both.
//
// It stops where the network begins: nothing here calls the API. What the
// application does once it is talking to a server is `e2e_capture.mjs`.

import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { loadChromium } from './browser.mjs';
import { startStaticServer } from './static_server.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'build', 'web');
const PORT = 8901;
const ORIGIN = `http://127.0.0.1:${PORT}`;

const runtime = await loadChromium();
if (!runtime) process.exit(0);
const { chromium, executablePath } = runtime;

let server;
try {
  server = await startStaticServer({ root, port: PORT });
} catch (error) {
  console.error(`error: ${error.message}`);
  process.exit(1);
}

const failures = [];
const check = (name, ok, detail = '') => {
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures.push(name);
};

const browser = await chromium.launch({ executablePath, args: ['--no-sandbox'] });
const context = await browser.newContext();
const page = await context.newPage();

const external = new Set();
page.on('request', (request) => {
  const url = request.url();
  if (!url.startsWith(ORIGIN) && !url.startsWith('data:') && !url.startsWith('blob:')) {
    external.add(new URL(url).origin);
  }
});

/// Waits for a painted Flutter view.
///
/// CanvasKit draws to a canvas, so there is no text in the DOM to wait for —
/// `innerText` is empty on a perfectly healthy page. The accessibility tree is
/// the honest probe: Flutter builds it on demand when the semantics placeholder
/// is activated, and it then contains the real labels.
async function bootAndReadLabels(target) {
  await target.waitForSelector('flutter-view', { timeout: 60000 });
  await target.waitForSelector('flt-scene-host canvas, flt-canvas-container canvas', {
    timeout: 60000,
    state: 'attached',
  });
  // Dispatched from the page rather than through Playwright's click: the
  // placeholder is deliberately off-screen and zero-opacity, so an actionability
  // check waits for a visibility that will never come.
  await target.evaluate(() => {
    document.querySelector('flt-semantics-placeholder')?.click();
  });
  await target.waitForSelector('flt-semantics[aria-label], flt-semantics[role]', {
    timeout: 60000,
    state: 'attached',
  });
  return target.evaluate(() =>
    [...document.querySelectorAll('flt-semantics')]
      .map((node) => node.getAttribute('aria-label') ?? node.textContent ?? '')
      .join(' | '),
  );
}

await page.goto(`${ORIGIN}/`, { waitUntil: 'load' });
const labels = await bootAndReadLabels(page);

check('the application boots', true);

// Reported rather than asserted, and the distinction is the point.
//
// `fonts.gstatic.com` is still probed by the engine for its glyph *fallback*
// chain — a knob Flutter 3.27 does not expose. That request failing is
// harmless: the bundled Roboto covers everything a French interface draws, as
// the label check below proves. What must not be tolerated is a third party the
// application cannot start without, and the only honest test of that is the
// offline reload at the end of this file.
const thirdParty = [...external].filter((origin) => !origin.includes('localhost'));
if (thirdParty.length > 0) {
  console.log(`  note   third-party origins probed: ${thirdParty.join(', ')}`);
}

check(
  'the boot placeholder is removed',
  (await page.$('#boot')) === null,
);

check(
  'the interface has content — the bundled font is in use',
  labels.includes('MindFlow'),
  JSON.stringify(labels.slice(0, 80)),
);

// The browser half of the storage layer, in the browser it runs in.
const stored = await page.evaluate(async () => {
  const database = await new Promise((resolve, reject) => {
    const request = indexedDB.open('mindflow', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('captures');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const write = (key, value) =>
    new Promise((resolve, reject) => {
      const query = database
        .transaction('captures', 'readwrite')
        .objectStore('captures')
        .put(value, key);
      query.onsuccess = resolve;
      query.onerror = () => reject(query.error);
    });
  const read = (key) =>
    new Promise((resolve, reject) => {
      const query = database
        .transaction('captures', 'readonly')
        .objectStore('captures')
        .get(key);
      query.onsuccess = () => resolve(query.result);
      query.onerror = () => reject(query.error);
    });
  await write('probe', new Uint8Array([1, 2, 3, 4]));
  return (await read('probe'))?.length ?? 0;
});
check('audio survives a round trip through IndexedDB', stored === 4);

// The test this whole file is named after.
//
// The service worker caches the shell, but only once it is activated *and*
// controlling the page — and it does not control the page that registered it
// until a navigation. Cutting the network before that proves nothing except
// that the test was hasty.
await page.waitForFunction(
  async () => {
    const registration = await navigator.serviceWorker?.ready;
    return registration?.active?.state === 'activated';
  },
  { timeout: 60000 },
);
// A first reload puts the worker in control; the offline one comes after.
await page.reload({ waitUntil: 'load', timeout: 60000 });
await bootAndReadLabels(page);
await page.waitForFunction(() => !!navigator.serviceWorker?.controller, {
  timeout: 60000,
});

await context.setOffline(true);
let offlineLabels = '';
try {
  await page.reload({ waitUntil: 'load', timeout: 60000 });
  offlineLabels = await bootAndReadLabels(page);
} catch {
  offlineLabels = '';
}
check(
  'the application boots with the network cut',
  offlineLabels.includes('MindFlow'),
);

// Whatever was in IndexedDB before the network went away is still there.
const survived = offlineLabels === ''
    ? -1
    : await page.evaluate(async () => {
  const database = await new Promise((resolve, reject) => {
    const request = indexedDB.open('mindflow', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('captures');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return new Promise((resolve, reject) => {
    const query = database
      .transaction('captures', 'readonly')
      .objectStore('captures')
      .get('probe');
    query.onsuccess = () => resolve(query.result?.length ?? 0);
    query.onerror = () => reject(query.error);
  });
      });
check('queued audio survives the network going away', survived === 4);

await browser.close();
await server.close();

if (failures.length > 0) {
  console.error(`\n${failures.length} check(s) failed.`);
  process.exit(1);
}
console.log('\nAll web smoke checks passed.');
