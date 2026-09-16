// OpenStreetMap's tile servers (and its Nominatim geocoder) reject requests that look like
// they come from a browser but carry no Referer identifying the site or app, serving an
// "Access blocked" tile instead. See
//   https://operations.osmfoundation.org/policies/tiles/
//   https://wiki.openstreetmap.org/wiki/Blocked_tiles
// Neither Firefox nor Chromium sends a Referer from an extension page, so the maps in the
// options page were blocked. The main script therefore adds a Referer that identifies the
// project, but only to requests made by the extension's own pages: websites the user visits
// that embed OSM maps keep whatever Referer they send themselves.
//
// Two strategies, chosen at runtime by install():
//  - blocking webRequest (Firefox, Manifest V2): rewrite the headers of each request;
//  - declarativeNetRequest (Chromium, Manifest V3): one dynamic rule, registered on install
//    and on browser startup, scoped to requests initiated by this extension.
//
// This module is loaded by the Node unit tests, so it must not require the Browser layer.

const REFERER = 'https://github.com/glichten/location-guard';

const OSM_HOSTS = [
	'tile.openstreetmap.org',
	'tile.openstreetmap.de',
	'nominatim.openstreetmap.org',
];

// webRequest match patterns: the tile servers use subdomains (a.tile..., b.tile...)
const URL_PATTERNS = OSM_HOSTS.map(h => h.startsWith('tile.') ? '*://*.' + h + '/*' : '*://' + h + '/*');

const RULE_ID = 1;

// --- strategy 1: blocking webRequest --------------------------------------------------------

// Request headers to send for a webRequest.onBeforeSendHeaders `details` object, or
// null if the request was not made by the extension itself and must be left alone.
function refererHeaders(details, extensionOrigin) {
	if(!fromExtension(details, extensionOrigin))
		return null;

	const headers = (details.requestHeaders || []).filter(h => h.name.toLowerCase() != 'referer');
	headers.push({ name: 'Referer', value: REFERER });
	return headers;
}

function fromExtension(details, extensionOrigin) {
	const origin = extensionOrigin.replace(/\/+$/, '');

	if(details.originUrl != null)		// Firefox: full URL of the document making the request
		return details.originUrl == origin || details.originUrl.startsWith(origin + '/');
	if(details.initiator != null)		// Chrome: origin of the document making the request
		return details.initiator == origin;
	return false;
}

function installWebRequest(webRequest, extensionOrigin) {
	webRequest.onBeforeSendHeaders.addListener(
		function(details) {
			const headers = refererHeaders(details, extensionOrigin);
			return headers ? { requestHeaders: headers } : {};
		},
		{ urls: URL_PATTERNS },
		['blocking', 'requestHeaders']
	);
}

// --- strategy 2: declarativeNetRequest ------------------------------------------------------

// The dynamic rule: set the Referer on OSM requests whose initiator is this extension.
// requestDomains matches subdomains too (a.tile.openstreetmap.org).
function dnrRule(extensionId) {
	return {
		id: RULE_ID,
		priority: 1,
		action: {
			type: 'modifyHeaders',
			requestHeaders: [{ header: 'Referer', operation: 'set', value: REFERER }],
		},
		condition: {
			requestDomains: OSM_HOSTS,
			initiatorDomains: [extensionId],
			resourceTypes: ['image', 'xmlhttprequest', 'other'],
		},
	};
}

function installDnr(browserApi) {
	return new Promise(resolve => {
		function apply() {
			browserApi.declarativeNetRequest
				.updateDynamicRules({ removeRuleIds: [RULE_ID], addRules: [dnrRule(browserApi.runtime.id)] })
				.then(
					() => resolve('declarativeNetRequest'),
					err => {
						console.warn('Location Guard: could not register the OpenStreetMap Referer rule, the options page maps may be blocked', err);
						resolve(null);
					});
		}
		// Dynamic rules persist across browser and worker restarts; (re)applying on these two
		// events is cheap and idempotent, and no other event is needed on a plain worker wake-up.
		browserApi.runtime.onInstalled.addListener(apply);
		browserApi.runtime.onStartup.addListener(apply);
	});
}

// --- entry point ----------------------------------------------------------------------------

// Set up whichever strategy the browser supports. Resolves with the strategy name once the
// Referer is guaranteed to be sent (for declarativeNetRequest that is after the first
// install/startup event has applied the rule), or with null if nothing could be set up.
function install(browserApi) {
	if(browserApi.webRequest && browserApi.webRequest.onBeforeSendHeaders) {
		installWebRequest(browserApi.webRequest, browserApi.runtime.getURL(''));
		return Promise.resolve('webRequest');
	}
	if(browserApi.declarativeNetRequest)
		return installDnr(browserApi);

	console.warn('Location Guard: no API available to add a Referer to OpenStreetMap requests');
	return Promise.resolve(null);
}

module.exports = { refererHeaders, install, dnrRule, REFERER, URL_PATTERNS, OSM_HOSTS, RULE_ID };
