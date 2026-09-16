// OpenStreetMap's tile servers (and its Nominatim geocoder) reject requests that look like
// they come from a browser but carry no Referer identifying the site or app, serving an
// "Access blocked" tile instead. See
//   https://operations.osmfoundation.org/policies/tiles/
//   https://wiki.openstreetmap.org/wiki/Blocked_tiles
// Firefox never sends a Referer from moz-extension:// pages, so the maps in the options
// page were blocked. The main script therefore adds a Referer that identifies the project,
// but only to requests made by the extension's own pages: websites the user visits that
// embed OSM maps keep whatever Referer they send themselves.

const REFERER = 'https://github.com/chatziko/location-guard';

const URL_PATTERNS = [
	'*://*.tile.openstreetmap.org/*',
	'*://*.tile.openstreetmap.de/*',
	'*://nominatim.openstreetmap.org/*',
];

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

// Register the listener on browser.webRequest. extensionOrigin is browser.runtime.getURL('').
function install(webRequest, extensionOrigin) {
	webRequest.onBeforeSendHeaders.addListener(
		function(details) {
			const headers = refererHeaders(details, extensionOrigin);
			return headers ? { requestHeaders: headers } : {};
		},
		{ urls: URL_PATTERNS },
		['blocking', 'requestHeaders']
	);
}

module.exports = { refererHeaders, install, REFERER, URL_PATTERNS };
