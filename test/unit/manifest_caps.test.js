// test/unit/manifest_caps.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');

const { hasPermanentIcon, injectsViaManifest, hasPersistentBackground } = require('../../src/js/common/manifest_caps');

test('hasPermanentIcon: true for a Manifest V3 "action"', () => {
	assert.equal(hasPermanentIcon({ manifest_version: 3, action: {} }), true);
});

test('hasPermanentIcon: true for a Manifest V2 "browser_action", false for "page_action"', () => {
	assert.equal(hasPermanentIcon({ manifest_version: 2, browser_action: {} }), true);
	assert.equal(hasPermanentIcon({ manifest_version: 2, page_action: {} }), false);
});

test('injectsViaManifest: true only when a content script runs in the MAIN world', () => {
	assert.equal(injectsViaManifest({ content_scripts: [
		{ js: ['js/content/inject.js'], world: 'MAIN' },
		{ js: ['js/common.js', 'js/content/content.js'] },
	] }), true);
	assert.equal(injectsViaManifest({ content_scripts: [{ js: ['js/common.js', 'js/content/content.js'] }] }), false);
	assert.equal(injectsViaManifest({ manifest_version: 3 }), false);		// no content scripts at all
});

test('hasPersistentBackground: true for Manifest V2, false for V3', () => {
	assert.equal(hasPersistentBackground({ manifest_version: 2 }), true);
	assert.equal(hasPersistentBackground({ manifest_version: 3 }), false);
});
