# addons.mozilla.org listing

Text and notes for the listed (public) submission of the Firefox build.
Paste the sections into the corresponding fields on
<https://addons.mozilla.org/developers/>.

## Submission steps

1. `make build-firefox` and `make package-firefox` (or zip `build/firefox`
   with Python, see README). Upload `build/location-guard-firefox-2.7.1.xpi`.
   The version must be new: Mozilla will not accept a version string that
   was already signed, listed or unlisted.
2. In the developer hub, open the add-on (it already exists from the unlisted
   signings), choose **Upload New Version**, and pick **On this site**
   for distribution. Picking **On your own** instead signs the file for
   self-distribution within minutes and creates no listing at all; that is
   what happened to 2.7.0, which is why the listed submission is 2.7.1.
   `make amo-status` shows which channel each version went to.
3. When asked for source code, answer **yes** and upload the archive produced
   by `git archive --format=zip -o build/location-guard-2.7.1-source.zip v2.7.1`.
   The extension ships browserify bundles, so reviewers rebuild it from source.
4. Fill in the listing fields below, add two or three screenshots of the
   options page (Privacy Levels map, Fixed Location map with a search result),
   and submit. Listed submissions get a human review; expect days to a couple
   of weeks.

## Name

Location Guard Revived

## Summary (250 characters max)

Hide your real location from websites: report it with controlled noise added,
or report a fixed location of your choice. A maintained fork of the original
Location Guard, with its map and location search working again.

## Description

Websites can ask the browser for your location. Location Guard intercepts that
request and, if you allow the website to see your location at all, gives it a
fake one instead: either your real location with random noise added, so the
website only learns the general area you are in, or a fixed location that you
pick on a map.

Choose a privacy level per website. Low, medium and high control how much
noise is added, and the options page shows the protection area on a map so you
can see what each level means. "Use fixed location" always reports the same
place, wherever you are, and can skip the browser's location lookup entirely.

This is a maintained fork of the original Location Guard by Kostas
Chatzikokolakis, a product of research at École Polytechnique, CNRS and Inria
on geo-indistinguishability. The original has not been updated since 2022 and
its map and search stopped working. This fork keeps the same privacy design and
fixes:

- the map tiles, which OpenStreetMap had started blocking;
- the location search, which used a third-party service whose shared key had
  run out of quota, and now uses OpenStreetMap's own Nominatim;
- accurate attribution and privacy information.

Source code, issues and the change history are at
https://github.com/glichten/location-guard . Licensed under MIT/X11 or
CeCILL-B, like the original.

Note: Location Guard protects against location requests made through the
browser. It does not hide your IP address, which websites can use to estimate
your location at city level.

## Categories

Privacy & Security

## License

MIT/X11 License

## Privacy policy

Location Guard Revived does not collect, store or transmit any personal data
to its developers or to anyone else on their behalf.

The extension's location protection works entirely inside your browser. When a
website asks for your location and you allow it, only the fake location is
given to that website.

The maps in the extension's options page are the one place where the
extension contacts a server. Showing a map fetches map tiles for the area on
screen from OpenStreetMap (tile.openstreetmap.org), and typing in the map's
search box sends the text you typed to OpenStreetMap's Nominatim search
service (nominatim.openstreetmap.org). These requests happen only while you
use that page and are subject to the OpenStreetMap Foundation privacy policy
at https://osmfoundation.org/wiki/Privacy_Policy . The extension identifies
itself to those servers with a Referer header naming this project, as the
OpenStreetMap tile usage policy requires. No other servers are contacted.

Your settings, including the fixed location you choose, are stored in the
browser's local extension storage and never leave your device.

## Notes to reviewer

**Build from source.** Requires Node.js 20 or newer (built and tested with
25.2), GNU make, the C preprocessor (`cpp`, from gcc or clang) and perl.

    npm ci
    make build-firefox

`build/firefox/` is byte-for-byte what the uploaded .xpi contains (the
Makefile bundles with browserify, copies third-party CSS, and preprocesses
`src/manifest.json` with `cpp -P -Dis_firefox`).

**Third-party code**, all unmodified npm packages pinned in package-lock.json:
leaflet 1.9, leaflet-control-geocoder 4, leaflet.locatecontrol 0.67,
jquery 3, jquery-migrate 3, jquery-mobile 1.4.5 (via jquery-mobile-babel-safe),
intro.js 2.9, sglide 2.1. `js/common-gui.js` is the browserify bundle of these
with the jquery-mobile and leaflet-control-geocoder files appended verbatim.

**Linter output.** `web-ext lint` reports no errors. Its `innerHTML`
warnings all point into `js/common-gui.js`, i.e. into the unmodified
jquery-mobile, leaflet and leaflet-control-geocoder code listed above; the
extension's own code does not assign `innerHTML` from remote data (search
results are rendered by leaflet-control-geocoder, which HTML-escapes them).

**webRequest / webRequestBlocking.** Used in one place, `js/main.js` via
`js/osm_referer.js`: an `onBeforeSendHeaders` listener for
`*.tile.openstreetmap.org`, `*.tile.openstreetmap.de` and
`nominatim.openstreetmap.org` that sets the `Referer` header to the project
URL, and only when the request originates from the extension's own pages
(`details.originUrl` starts with `browser.runtime.getURL('')`). Requests from
web pages are returned unchanged. OpenStreetMap's tile usage policy requires an
identifying Referer and Firefox sends none from `moz-extension://` pages, so
without this the maps show OSM's "Access blocked" tile. `npm test` runs unit
tests for exactly this logic.

**Data collection declaration.** `data_collection_permissions.required` is
`["none"]`: nothing is sent to the developers. The only network traffic is the
user-initiated map on the options page, which fetches OpenStreetMap tiles for
the area displayed and sends typed search text to Nominatim; this is disclosed
in the extension's FAQ and in the privacy policy above. If you consider that
transmission to fall under `locationInfo` or `searchTerms`, say so and it will
be declared in the next version.

**Content script.** `js/content/content.js` runs at `document_start` in all
frames and injects `js/content/inject.js` into the page to replace
`navigator.geolocation` with a version that returns the fake location. This
is the extension's core function and is unchanged from the original.

**Testing.** `npm test` (unit). `test/e2e/firefox_smoke.py` installs the build
into a real Firefox through geckodriver and checks tiles and search against
the live OSM servers; see `test/e2e/README.md`.
