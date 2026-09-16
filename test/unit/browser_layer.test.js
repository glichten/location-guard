// test/unit/browser_layer.test.js
//
// The Browser abstraction layer must work inside a Manifest V3 service worker: no `window`,
// the `action` API instead of `browserAction`, and no per-wake-up work that touches every tab.

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { fakeBrowser, loadFresh, mv2FirefoxManifest, calls, tick } = require('./helpers/fake_browser');

// module paths given to loadFresh() are resolved from test/unit/helpers/, where it lives
const BROWSER = '../../../src/js/common/browser';

test('the Browser layer loads in a worker-like global with no window', () => {
	assert.equal(typeof globalThis.window, 'undefined');
	assert.doesNotThrow(() => loadFresh(fakeBrowser(), BROWSER));
});

test('permanentIcon() and injectsViaManifest() follow the manifest', () => {
	const v3 = loadFresh(fakeBrowser(), BROWSER);
	assert.equal(v3.capabilities.permanentIcon(), true);
	assert.equal(v3.capabilities.injectsViaManifest(), true);
	assert.equal(v3.capabilities.hasPersistentBackground(), false);

	const v2 = loadFresh(fakeBrowser({ manifest: mv2FirefoxManifest() }), BROWSER);
	assert.equal(v2.capabilities.permanentIcon(), false);
	assert.equal(v2.capabilities.injectsViaManifest(), false);
	assert.equal(v2.capabilities.hasPersistentBackground(), true);
});

test('the default icon is refreshed through browser.action when browserAction does not exist', async () => {
	const fake = fakeBrowser();
	const Browser = loadFresh(fake, BROWSER);
	Browser._script = 'main';
	await Browser.gui.refreshIcon(null);
	const setIcon = calls(fake, 'action.setIcon');
	assert.equal(setIcon.length, 1);
	assert.equal(setIcon[0].args[0].tabId, null);
	assert.equal(calls(fake, 'tabs.sendMessage').length, 0, 'the default icon needs no message to any tab');
});

test('rpc.call resolves null when the browser reports no receiver (runtime.lastError)', async () => {
	const fake = fakeBrowser({ reply: undefined });
	const Browser = loadFresh(fake, BROWSER);
	fake.runtime.lastError = { message: 'Could not establish connection. Receiving end does not exist.' };
	assert.equal(await Browser.rpc.call(42, 'getState', []), null);
	fake.runtime.lastError = null;
	fake.calls.length = 0;
	const fake2 = fakeBrowser({ reply: { callUrl: 'https://a.example/' } });
	const Browser2 = loadFresh(fake2, BROWSER);
	assert.deepEqual(await Browser2.rpc.call(42, 'getState', []), { callUrl: 'https://a.example/' });
});

test('rpc.call to the main script uses runtime.sendMessage(message, callback)', async () => {
	const fake = fakeBrowser({ reply: 'ok' });
	const Browser = loadFresh(fake, BROWSER);
	assert.equal(await Browser.rpc.call(null, 'refreshIcon', ['self']), 'ok');
	const sent = calls(fake, 'runtime.sendMessage');
	assert.equal(sent.length, 1);
	assert.equal(sent[0].args.length, 2);
	assert.deepEqual(sent[0].args[0], { method: 'refreshIcon', args: ['self'] });
	assert.equal(typeof sent[0].args[1], 'function');
});

test('Manifest V3 main script: default icon at start, all tabs only on install and startup', async () => {
	const fake = fakeBrowser({ tabs: [{ id: 7 }] });
	const Browser = loadFresh(fake, BROWSER);
	Browser.init('main');
	await tick(); await tick();
	assert.equal(calls(fake, 'tabs.query').length, 0, 'no tab enumeration on a plain worker start');
	assert.equal(calls(fake, 'action.setIcon').filter(c => c.args[0].tabId == null).length, 1, 'default icon refreshed');

	fake.runtime.onStartup.fire();
	await tick(); await tick();
	assert.equal(calls(fake, 'tabs.query').length, 1, 'all tabs refreshed on startup');

	fake.runtime.onInstalled.fire({ reason: 'update' });
	await tick(); await tick();
	assert.equal(calls(fake, 'tabs.query').length, 2, 'all tabs refreshed on install/update');
});

test('Manifest V3 main script: the page-action tabs.onUpdated workaround is not registered', () => {
	const fake = fakeBrowser();
	const Browser = loadFresh(fake, BROWSER);
	Browser.init('main');
	assert.equal(fake.tabs.onUpdated.fns.length, 0);
});

test('Manifest V2 Firefox main script: all icons are refreshed at start, as before', async () => {
	const fake = fakeBrowser({ manifest: mv2FirefoxManifest(), webRequest: true, tabs: [{ id: 7 }] });
	const Browser = loadFresh(fake, BROWSER);
	Browser.init('main');
	await tick(); await tick();
	assert.equal(calls(fake, 'tabs.query').length, 1);
	assert.equal(fake.runtime.onStartup.fns.length, 0, 'no startup listener needed with a persistent background page');
});
