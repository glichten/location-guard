// Runs injectedCode (the navigator.geolocation replacement) in the page's own JavaScript world.
// On the Manifest V3 (Chromium) builds this is the primary path: the manifest declares this
// file as a content script with world: "MAIN" at document_start. On the Manifest V2 (Firefox)
// build it is the fallback content.js loads as an external script when the page's CSP blocks
// the inline <script> injection.
//
const PostRPC = require('../common/post-rpc');
const injectedCode = require('./injected');

injectedCode(PostRPC);