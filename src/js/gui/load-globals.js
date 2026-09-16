// Some GUI libraries cannot go through browserify and are instead appended
// verbatim to common-gui.js by the Makefile. They find their dependencies as
// globals, which this entry point sets up:
//
// - jquery-mobile 1.4.5 has no proper npm version, but a
//   "jquery-mobile-babel-safe" package exists and can be loaded in a hack-ish way
//   by appending the whole file in common-gui.js.
// - leaflet-control-geocoder's build uses ES2022 syntax that browserify's parser
//   rejects, so its UMD file is appended as well and attaches to window.L.

// We load jquery, and store it globally to be accessible to jquery-mobile
window.jQuery = require('jquery');

// jquery-mobile does not support jquery 3, so we need the migration package
require('jquery-migrate');
window.jQuery.migrateMute = true;	// but no need for the warnings

// leaflet is bundled here (-r leaflet) and shared with the other bundles; leaflet-control-geocoder
// registers L.Control.Geocoder on this same instance
window.L = require('leaflet');
