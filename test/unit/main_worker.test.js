// test/unit/main_worker.test.js
//
// The background script (main.js) under a Manifest V3 service worker: loads without a
// window, and on first install opens the demo page only once the OpenStreetMap Referer
// rule is in place (the demo shows a map immediately).

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { fakeBrowser, loadFresh, mv2FirefoxManifest, calls, tick } = require('./helpers/fake_browser');

// module paths given to loadFresh() are resolved from test/unit/helpers/, where it lives
const MAIN = '../../../src/js/main';

test('main.js loads in a worker-like global with no window', () => {
	assert.equal(typeof globalThis.window, 'undefined');
	assert.doesNotThrow(() => loadFresh(fakeBrowser(), MAIN));
});

test('Chromium: on first install the demo page opens only after the Referer rule is registered', async () => {
	let resolveRule;
	const fake = fakeBrowser({ dnrResult: new Promise(resolve => { resolveRule = resolve; }) });
	loadFresh(fake, MAIN);

	fake.runtime.onInstalled.fire({ reason: 'install' });
	await tick(); await tick();
	assert.equal(calls(fake, 'updateDynamicRules').length, 1);
	assert.equal(calls(fake, 'tabs.create').length, 0, 'the demo page must wait for the rule');

	resolveRule();
	await tick(); await tick();
	assert.deepEqual(calls(fake, 'tabs.create').map(c => c.args[0]),
		[{ url: 'chrome-extension://oofmknpjjmooccmkmahaghakbfbclgkk/demo.html' }]);
});

test('Chromium: an update does not open the demo page', async () => {
	const fake = fakeBrowser();
	loadFresh(fake, MAIN);
	fake.runtime.onInstalled.fire({ reason: 'update' });
	await tick(); await tick();
	assert.equal(calls(fake, 'tabs.create').length, 0);
	assert.equal(calls(fake, 'updateDynamicRules').length, 1, 'the rule is (re)applied on update');
});

test('Firefox (blocking webRequest): the demo page opens on first install as before', async () => {
	const fake = fakeBrowser({ manifest: mv2FirefoxManifest(), webRequest: true });
	loadFresh(fake, MAIN);
	assert.equal(fake.webRequest.onBeforeSendHeaders.fns.length, 1);
	fake.runtime.onInstalled.fire({ reason: 'install' });
	await tick(); await tick();
	assert.equal(calls(fake, 'tabs.create').length, 1);
	assert.equal(calls(fake, 'updateDynamicRules').length, 0);
});
