//
// What a manifest implies about the build, as pure functions of the object returned by
// browser.runtime.getManifest(). Kept free of any browser API so it can be unit tested.

// The icon is a permanent toolbar button (browser action / Manifest V3 action) rather than
// a page action that is only shown on pages that use geolocation.
function hasPermanentIcon(manifest) {
	return !!(manifest.action || manifest.browser_action);
}

// The manifest itself injects our geolocation replacement into the page's own JavaScript
// world (a content script with world: "MAIN"), so the content script must not inject it
// through the DOM as well.
function injectsViaManifest(manifest) {
	return (manifest.content_scripts || []).some(cs => cs.world == 'MAIN');
}

// Manifest V2 has a background page that lives as long as the browser; Manifest V3 has a
// service worker that is started on demand and stopped when idle.
function hasPersistentBackground(manifest) {
	return (manifest.manifest_version || 2) < 3;
}

module.exports = { hasPermanentIcon, injectsViaManifest, hasPersistentBackground };
