// main script
// Here we only handle the install/update events
// Browser-specific functionality for the main script, if needed, is added by browser/*.js
//

const Browser = require('./common/browser');
const Util = require('./common/util');
const OsmReferer = require('./osm_referer');

Browser.log('starting');

// identify the extension's own map/geocoder requests to OpenStreetMap (see osm_referer.js)
const refererReady = OsmReferer.install(browser);

Util.events.addListener('browser.install', async function() {
	// show demo on first install. The demo shows a map right away, so wait until our
	// OpenStreetMap requests are identified, or the first thing a new user sees could be
	// OSM's "Access blocked" tiles.
	await refererReady;
	Browser.gui.showPage('demo.html');
});

Browser.init('main');

// this is used from the content-script of an iframe, to communicate with the content-script
// of the top-window. We just echo the call back to the tab.
//
Browser.rpc.register('apiCalledInFrame', async function(url, tabId) {
	return await Browser.rpc.call(tabId, 'apiCalledInFrame', [url]);
});

if(Browser.testing) {
	// test for nested calls, and for correct passing of tabId
	//
	Browser.rpc.register('nestedTestMain', async function(tabId) {
		Browser.log("in nestedTestMain, call from ", tabId, "calling back nestedTestTab");

		const res = Browser.rpc.call(tabId, 'nestedTestTab', []);
		Browser.log("got from nestedTestTab", res, "adding '_foo' and sending back");
		return res + '_foo';
	});
}
