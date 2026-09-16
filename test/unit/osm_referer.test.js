// Unit tests for the Referer rewriting applied to OpenStreetMap requests made by
// the extension's own pages (see src/js/osm_referer.js).
//
// Run with:  npm test

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { refererHeaders, install, dnrRule, REFERER, URL_PATTERNS, OSM_HOSTS, RULE_ID } = require('../../src/js/osm_referer');

const EXT_ORIGIN = 'moz-extension://0c2c8085-650c-4ea8-88e7-3b0dc6d7a3d1';

function tileRequest(extra) {
	return Object.assign({
		url: 'https://a.tile.openstreetmap.org/14/8300/5637.png',
		requestHeaders: [
			{ name: 'Host', value: 'a.tile.openstreetmap.org' },
			{ name: 'Accept', value: 'image/avif,image/webp,*/*' },
		],
	}, extra);
}

function header(headers, name) {
	return headers.filter(h => h.name.toLowerCase() == name.toLowerCase());
}

test('adds a Referer to a tile request coming from the extension options page (Firefox originUrl)', () => {
	const details = tileRequest({ originUrl: EXT_ORIGIN + '/options.html' });
	const headers = refererHeaders(details, EXT_ORIGIN);
	assert.ok(headers, 'request should be rewritten');
	assert.deepEqual(header(headers, 'Referer'), [{ name: 'Referer', value: REFERER }]);
});

test('honours the Chrome-style initiator field', () => {
	const details = tileRequest({ initiator: 'chrome-extension://cfohepagpmnodfdmjliccbbigdkfcgia' });
	const headers = refererHeaders(details, 'chrome-extension://cfohepagpmnodfdmjliccbbigdkfcgia');
	assert.ok(headers);
	assert.deepEqual(header(headers, 'Referer'), [{ name: 'Referer', value: REFERER }]);
});

test('keeps the other request headers untouched', () => {
	const details = tileRequest({ originUrl: EXT_ORIGIN + '/options.html' });
	const headers = refererHeaders(details, EXT_ORIGIN);
	assert.deepEqual(header(headers, 'Host'), [{ name: 'Host', value: 'a.tile.openstreetmap.org' }]);
	assert.deepEqual(header(headers, 'Accept'), [{ name: 'Accept', value: 'image/avif,image/webp,*/*' }]);
});

test('replaces an existing Referer instead of sending two', () => {
	const details = tileRequest({ originUrl: EXT_ORIGIN + '/demo.html' });
	details.requestHeaders.push({ name: 'Referer', value: EXT_ORIGIN + '/demo.html' });
	const headers = refererHeaders(details, EXT_ORIGIN);
	assert.deepEqual(header(headers, 'Referer'), [{ name: 'Referer', value: REFERER }]);
});

test('leaves requests made by ordinary web pages alone', () => {
	const details = tileRequest({ originUrl: 'https://www.example.com/map', initiator: 'https://www.example.com' });
	assert.equal(refererHeaders(details, EXT_ORIGIN), null);
});

test('leaves requests with no known origin alone', () => {
	assert.equal(refererHeaders(tileRequest({}), EXT_ORIGIN), null);
});

test('does not treat a look-alike origin as the extension', () => {
	const details = tileRequest({ originUrl: EXT_ORIGIN + '.evil.example/x' });
	assert.equal(refererHeaders(details, EXT_ORIGIN), null);
});

test('REFERER identifies the project over https, as the OSM tile usage policy asks', () => {
	assert.match(REFERER, /^https:\/\/.*location-guard/);
});

test('URL_PATTERNS cover the OSM tile servers and Nominatim, and nothing else', () => {
	assert.deepEqual(URL_PATTERNS.slice().sort(), [
		'*://*.tile.openstreetmap.de/*',
		'*://*.tile.openstreetmap.org/*',
		'*://nominatim.openstreetmap.org/*',
	]);
});

// --- helpers for a fake browser API ------------------------------------------------------

function listeners() {
	const fns = [];
	return { addListener: fn => fns.push(fn), fire: (...args) => fns.map(fn => fn(...args)), fns };
}

function fakeBrowser({ webRequest = false, dnrResult = Promise.resolve() } = {}) {
	const calls = [];
	const api = {
		calls,
		runtime: {
			id: 'oofmknpjjmooccmkmahaghakbfbclgkk',
			getURL: p => EXT_ORIGIN + '/' + p,
			onInstalled: listeners(),
			onStartup: listeners(),
		},
		declarativeNetRequest: {
			updateDynamicRules: arg => { calls.push(arg); return dnrResult; },
		},
	};
	if(webRequest)
		api.webRequest = { onBeforeSendHeaders: listeners() };
	return api;
}

const tick = () => new Promise(resolve => setImmediate(resolve));

// --- the two strategies -------------------------------------------------------------------

test('OSM_HOSTS is the single source for URL_PATTERNS', () => {
	assert.deepEqual(OSM_HOSTS, ['tile.openstreetmap.org', 'tile.openstreetmap.de', 'nominatim.openstreetmap.org']);
	assert.deepEqual(URL_PATTERNS, OSM_HOSTS.map(h => h.startsWith('tile.') ? '*://*.' + h + '/*' : '*://' + h + '/*'));
});

test('dnrRule() sets exactly one Referer on OSM requests made by the given extension', () => {
	const rule = dnrRule('oofmknpjjmooccmkmahaghakbfbclgkk');
	assert.deepEqual(rule, {
		id: RULE_ID,
		priority: 1,
		action: { type: 'modifyHeaders', requestHeaders: [{ header: 'Referer', operation: 'set', value: REFERER }] },
		condition: {
			requestDomains: OSM_HOSTS,
			initiatorDomains: ['oofmknpjjmooccmkmahaghakbfbclgkk'],
			resourceTypes: ['image', 'xmlhttprequest', 'other'],
		},
	});
});

test('install() with blocking webRequest (Firefox) registers the header listener and resolves at once', async () => {
	const api = fakeBrowser({ webRequest: true });
	const how = await install(api);
	assert.equal(how, 'webRequest');
	assert.equal(api.webRequest.onBeforeSendHeaders.fns.length, 1);
	assert.equal(api.calls.length, 0, 'no declarativeNetRequest call');
	assert.equal(api.runtime.onInstalled.fns.length, 0);

	// the registered listener behaves like refererHeaders()
	const fn = api.webRequest.onBeforeSendHeaders.fns[0];
	const rewritten = fn(tileRequest({ originUrl: EXT_ORIGIN + '/options.html' }));
	assert.deepEqual(header(rewritten.requestHeaders, 'Referer'), [{ name: 'Referer', value: REFERER }]);
	assert.deepEqual(fn(tileRequest({ originUrl: 'https://www.example.com/' })), {});
});

test('install() without webRequest (Chromium) registers the DNR rule on install and on startup', async () => {
	const api = fakeBrowser();
	let settled = null;
	install(api).then(how => { settled = how; });
	await tick();
	assert.equal(settled, null, 'nothing is in place until an install/startup event');
	assert.equal(api.calls.length, 0);

	api.runtime.onInstalled.fire({ reason: 'install' });
	await tick();
	assert.equal(settled, 'declarativeNetRequest');
	assert.deepEqual(api.calls, [{ removeRuleIds: [RULE_ID], addRules: [dnrRule(api.runtime.id)] }]);

	api.runtime.onStartup.fire();
	await tick();
	assert.equal(api.calls.length, 2, 'startup re-applies the same rule (idempotent)');
});

test('install() reports a rejected updateDynamicRules and resolves null instead of throwing', async () => {
	const api = fakeBrowser({ dnrResult: Promise.reject(new Error('nope')) });
	const warnings = [];
	const origWarn = console.warn;
	console.warn = (...args) => warnings.push(args);
	try {
		const p = install(api);
		api.runtime.onInstalled.fire({ reason: 'install' });
		assert.equal(await p, null);
	} finally {
		console.warn = origWarn;
	}
	assert.equal(warnings.length, 1);
	assert.match(String(warnings[0][0]), /Referer/);
});

test('install() with neither API resolves null and warns', async () => {
	const warnings = [];
	const origWarn = console.warn;
	console.warn = (...args) => warnings.push(args);
	try {
		assert.equal(await install({ runtime: { id: 'x', onInstalled: listeners(), onStartup: listeners() } }), null);
	} finally {
		console.warn = origWarn;
	}
	assert.equal(warnings.length, 1);
});
