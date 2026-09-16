// test/unit/helpers/fake_browser.js
//
// A fake of the WebExtensions API surface the background and Browser-layer code touch,
// recording every call, plus a loader that requires the extension's modules fresh with
// the fake installed as the global `browser`/`chrome` and, deliberately, no `window`.

const path = require('path');

function listeners() {
	const fns = [];
	return { addListener: fn => fns.push(fn), fire: (...args) => fns.map(fn => fn(...args)), fns };
}

function actionApi(calls, ns) {
	const api = {};
	for(const m of ['setTitle', 'setBadgeText', 'setBadgeBackgroundColor', 'setPopup', 'setIcon', 'show', 'hide'])
		api[m] = (...args) => {
			calls.push({ name: ns + '.' + m, args });
			const cb = args[args.length - 1];
			if(typeof cb == 'function') cb();
		};
	return api;
}

function mv3Manifest() {
	return {
		manifest_version: 3,
		action: {},
		content_scripts: [
			{ js: ['js/content/inject.js'], world: 'MAIN' },
			{ js: ['js/common.js', 'js/content/content.js'] },
		],
	};
}

function mv2FirefoxManifest() {
	return {
		manifest_version: 2,
		page_action: {},
		content_scripts: [{ js: ['js/common.js', 'js/content/content.js'] }],
	};
}

// opts: manifest, webRequest (bool), dnrResult (promise), reply (value passed to sendMessage callbacks), tabs (array)
function fakeBrowser(opts = {}) {
	const manifest = opts.manifest || mv3Manifest();
	const calls = [];
	let stored = null;
	const withCallback = name => (...args) => {
		calls.push({ name, args });
		const cb = args[args.length - 1];
		if(typeof cb == 'function') cb(opts.reply);
	};
	const fake = {
		calls,
		runtime: {
			id: 'oofmknpjjmooccmkmahaghakbfbclgkk',
			lastError: null,
			getURL: p => 'chrome-extension://oofmknpjjmooccmkmahaghakbfbclgkk/' + p,
			getManifest: () => manifest,
			onInstalled: listeners(),
			onStartup: listeners(),
			onMessage: listeners(),
			sendMessage: withCallback('runtime.sendMessage'),
		},
		tabs: {
			query: (q, cb) => { calls.push({ name: 'tabs.query', args: [q] }); cb((opts.tabs || []).slice()); },
			create: withCallback('tabs.create'),
			remove: withCallback('tabs.remove'),
			sendMessage: withCallback('tabs.sendMessage'),
			onUpdated: listeners(),
		},
		storage: { local: {
			get: (key, cb) => cb(stored ? { [key]: stored } : {}),
			set: (items, cb) => { stored = items.global; if(cb) cb(); },
			clear: cb => { stored = null; if(cb) cb(); },
		} },
		declarativeNetRequest: {
			updateDynamicRules: arg => { calls.push({ name: 'updateDynamicRules', args: [arg] }); return opts.dnrResult || Promise.resolve(); },
		},
	};
	if(manifest.action)         fake.action = actionApi(calls, 'action');
	if(manifest.browser_action) fake.browserAction = actionApi(calls, 'browserAction');
	if(manifest.page_action)    fake.pageAction = actionApi(calls, 'pageAction');
	if(opts.webRequest)         fake.webRequest = { onBeforeSendHeaders: listeners() };
	return fake;
}

// Require `modulePath` (relative to this file) with all extension modules evicted from the
// require cache and `fake` installed as the global API. Returns the module's exports.
function loadFresh(fake, modulePath) {
	const marker = path.sep + 'src' + path.sep + 'js' + path.sep;
	for(const k of Object.keys(require.cache))
		if(k.includes(marker)) delete require.cache[k];
	globalThis.browser = fake;
	globalThis.chrome = fake;
	const base = require('../../../src/js/common/browser_base');
	base.debugging = false;			// keep Browser.log quiet in test output
	return require(modulePath);
}

const calls = (fake, name) => fake.calls.filter(c => c.name == name);
const tick = () => new Promise(resolve => setImmediate(resolve));

module.exports = { fakeBrowser, loadFresh, listeners, mv3Manifest, mv2FirefoxManifest, calls, tick };
