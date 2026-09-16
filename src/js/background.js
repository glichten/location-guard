// Manifest V3 background (service worker) entry point for the Chromium builds.
// Manifest V2 lists the two files in background.scripts; a worker gets one file, so
// import them here in the same order: common.js defines the shared modules that main.js
// requires. Both are browserify bundles produced by the Makefile.
importScripts('common.js', 'main.js');
