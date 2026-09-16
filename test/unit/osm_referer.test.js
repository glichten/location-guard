// Unit tests for the Referer rewriting applied to OpenStreetMap requests made by
// the extension's own pages (see src/js/osm_referer.js).
//
// Run with:  npm test

const { test } = require('node:test');
const assert = require('node:assert/strict');

const { refererHeaders, install, REFERER, URL_PATTERNS } = require('../../src/js/osm_referer');

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

test('install() registers one blocking request-header listener for the OSM hosts', () => {
	const calls = [];
	const webRequest = { onBeforeSendHeaders: { addListener: (fn, filter, extra) => calls.push({ fn, filter, extra }) } };
	install(webRequest, EXT_ORIGIN + '/');		// runtime.getURL('') gives a trailing slash
	assert.equal(calls.length, 1);
	assert.deepEqual(calls[0].filter, { urls: URL_PATTERNS });
	assert.deepEqual(calls[0].extra, ['blocking', 'requestHeaders']);

	const rewritten = calls[0].fn(tileRequest({ originUrl: EXT_ORIGIN + '/options.html' }));
	assert.deepEqual(header(rewritten.requestHeaders, 'Referer'), [{ name: 'Referer', value: REFERER }]);

	assert.deepEqual(calls[0].fn(tileRequest({ originUrl: 'https://www.example.com/' })), {});
});
