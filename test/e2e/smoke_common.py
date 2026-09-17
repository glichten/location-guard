"""Shared pieces of the browser smoke tests: a minimal W3C WebDriver client (standard
library only), helpers for the extension's options page, the checks themselves and a
runner. The per-browser scripts (firefox_smoke.py, chrome_smoke.py) only set up the
session and pick the checks to run."""

import base64
import json
import math
import os
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ELEMENT_KEY = 'element-6066-11e4-a52e-4f735466cecf'
ENTER = '\ue007'   # WebDriver key code for Enter

SYDNEY_OPERA = (-33.8568, 151.2153)
NEW_YORK = (40.7128, -74.0060)

# the WebExtensions API namespace as seen from inside one of the extension's pages
EXT_API = '(globalThis.browser || globalThis.chrome)'


class WebDriver:
    """Minimal W3C WebDriver client. The harness sets `ext_origin` (moz-extension://<uuid>
    or chrome-extension://<id>) after creating the session."""

    ext_origin = None
    # JavaScript prefix defining `geo`, the page's (patched) geolocation object, for scripts
    # that run in a website through the driver. Overridden by the Firefox driver.
    geolocation_prefix = 'var geo = navigator.geolocation;'

    def __init__(self, url):
        self.url = url.rstrip('/')
        self.session = None

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)['value']
        except urllib.error.HTTPError as e:
            raise RuntimeError('%s %s -> %s: %s' % (method, path, e.code, e.read().decode(errors='replace')))

    def new_session(self, caps):
        v = self._req('POST', '/session', {'capabilities': {'alwaysMatch': caps}})
        self.session = v['sessionId']
        return v

    def _s(self, method, path, body=None):
        return self._req(method, '/session/%s%s' % (self.session, path), body)

    def quit(self):
        if self.session:
            try:
                self._s('DELETE', '')
            finally:
                self.session = None

    def get(self, url):
        self._s('POST', '/url', {'url': url})

    def execute(self, script, *args):
        return self._s('POST', '/execute/sync', {'script': script, 'args': list(args)})

    def execute_async(self, script, *args):
        return self._s('POST', '/execute/async', {'script': script, 'args': list(args)})

    # elements are kept as their WebDriver reference dicts, so they can be passed
    # straight back as script arguments
    def find(self, css):
        return self._s('POST', '/element', {'using': 'css selector', 'value': css})

    def find_all(self, css):
        return self._s('POST', '/elements', {'using': 'css selector', 'value': css})

    def click(self, el):
        self._s('POST', '/element/%s/click' % el[ELEMENT_KEY], {})

    def send_keys(self, el, text):
        self._s('POST', '/element/%s/value' % el[ELEMENT_KEY], {'text': text})

    def screenshot(self, path):
        with open(path, 'wb') as f:
            f.write(base64.b64decode(self._s('GET', '/screenshot')))

    def set_timeouts(self, **kw):
        self._s('POST', '/timeouts', kw)

    def handles(self):
        return self._s('GET', '/window/handles')

    def current_handle(self):
        return self._s('GET', '/window')

    def switch_to(self, handle):
        self._s('POST', '/window', {'handle': handle})

    def new_tab(self):
        """Open a new tab, switch to it and return its handle."""
        handle = self._s('POST', '/window/new', {'type': 'tab'})['handle']
        self.switch_to(handle)
        return handle

    # --- extension pages

    def ext_url(self, path):
        return self.ext_origin + '/' + path

    def open_extension_page(self, url):
        """Navigate to one of the extension's own pages. Chromium allows a plain navigation;
        the Firefox driver overrides this."""
        self.get(url)


def wait_for(fn, timeout, what, interval=0.5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError('timed out after %ss waiting for %s (last value: %r)' % (timeout, what, last))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def alive(d):
    try:
        d._req('GET', '/status')
        return True
    except Exception:  # noqa: BLE001
        return False


def package_xpi(ext_dir):
    """Zip an unpacked extension directory into a temporary .xpi and return its path."""
    fd, xpi = tempfile.mkstemp(prefix='location-guard-', suffix='.xpi')
    os.close(fd)
    with zipfile.ZipFile(xpi, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(ext_dir):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.relpath(full, ext_dir))
    return xpi


def copy_ext_dir(ext_dir):
    """Copy an unpacked extension directory somewhere local (the browser must be able to read
    it, and the source may be on a network share) and return the copy's path."""
    dest = tempfile.mkdtemp(prefix='location-guard-ext-')
    shutil.rmtree(dest)
    shutil.copytree(ext_dir, dest)
    return dest


# ---------------------------------------------------------------- page helpers

MAP_IDS = {'fixedPos': 'fixedPosMap', 'levels': 'levelMap', 'options': None}


def show_page(d, page):
    """Open one of the options page's jQuery Mobile pages and wait for it (and its map, if it
    has one) to be ready. Returns the map's element id, or None."""
    d.open_extension_page(d.ext_url('options.html#' + page))
    map_id = MAP_IDS[page]
    wait_for(lambda: d.execute(
        'var page = document.getElementById(arguments[1]);'
        'if(!page || !page.classList.contains("ui-page-active")) return false;'
        'if(!arguments[0]) return true;'
        'var m = document.getElementById(arguments[0]);'
        'return !!(m && m.classList.contains("leaflet-container"));',
        map_id, page), 20, 'page %s to be ready' % page)
    return map_id


def wait_tiles_loaded(d, map_id):
    return wait_for(lambda: d.execute(
        'var tiles = document.querySelectorAll("#" + arguments[0] + " img.leaflet-tile");'
        'if(!tiles.length) return null;'
        'var loaded = Array.prototype.filter.call(tiles, t => t.classList.contains("leaflet-tile-loaded"));'
        'return loaded.length == tiles.length ? Array.prototype.map.call(tiles, t => t.src) : null;',
        map_id), 30, 'tiles of %s to finish loading' % map_id)


def tile_response(d, url):
    """What the extension page gets for a tile URL (same origin and headers as the <img> loads).

    OSM serves its "Access blocked" tile with HTTP 200 and an x-blocked header, so the
    status alone says nothing; the header is what tells a real tile from a block tile."""
    return d.execute_async(
        'var cb = arguments[arguments.length - 1];'
        'fetch(arguments[0], { cache: "no-store" })'
        '  .then(r => cb({ status: r.status, blocked: r.headers.get("x-blocked") }), e => cb({ status: "error: " + e }));', url)


def resource_statuses(d, host_fragment):
    """responseStatus of already-recorded resource loads (0 when the server hides it)."""
    return d.execute(
        'return performance.getEntriesByType("resource")'
        '  .filter(e => e.name.indexOf(arguments[0]) >= 0)'
        '  .map(e => e.responseStatus);', host_fragment)


def assert_real_tile(d, srcs):
    r = tile_response(d, srcs[0])
    assert r['status'] == 200 and not r.get('blocked'), \
        'tile request from the options page was rejected by OSM: %s (resource statuses: %s)' % (r, resource_statuses(d, 'tile.openstreetmap'))


def storage_get(d, key):
    """One key of the extension's settings object, read from an extension page."""
    return d.execute_async(
        'var cb = arguments[arguments.length - 1];'
        + EXT_API + '.storage.local.get("global").then(r => cb(r.global ? r.global[arguments[0]] : null), e => cb("error: " + e));', key)


def set_default_level(d, level):
    """Choose the default privacy level on the Options page the way a user would (the select's
    change event is what saves it) and wait until it is stored."""
    show_page(d, 'options')
    d.execute(
        'var s = document.getElementById("defaultLevel");'
        's.value = arguments[0];'
        's.dispatchEvent(new Event("change", { bubbles: true }));', level)
    wait_for(lambda: storage_get(d, 'defaultLevel') == level, 10, 'default level %r to be saved' % level)


def geocoder_search(d, map_id, text):
    """Type into the map's geocoder box and submit."""
    control = d.find('#%s .leaflet-control-geocoder' % map_id)
    expanded = lambda: 'leaflet-control-geocoder-expanded' in d.execute('return arguments[0].className;', control)
    if not expanded():
        d.click(d.find('#%s .leaflet-control-geocoder-icon' % map_id))
        wait_for(expanded, 5, 'search box to expand')
    box = d.find('#%s .leaflet-control-geocoder-form input' % map_id)
    # not WebDriver's clear(): it blurs the box afterwards, which collapses the control
    d.execute('arguments[0].value = "";', box)
    d.send_keys(box, text + ENTER)


def pick_first_result_if_listed(d, map_id, timeout, done):
    """After a search either `done()` becomes true directly, or a result list shows up and we pick the first entry."""
    def step():
        if done():
            return 'done'
        items = d.find_all('#%s .leaflet-control-geocoder-alternatives li a' % map_id)
        if items:
            d.click(items[0])
            return 'clicked'
        return None
    wait_for(step, timeout, 'search results')


def near(pos, target, tol_deg):
    return bool(pos) and isinstance(pos, dict) and abs(pos['latitude'] - target[0]) < tol_deg and abs(pos['longitude'] - target[1]) < tol_deg


def tile_xy(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def map_shows(d, map_id, latlon):
    """True when one of the map's loaded tiles is the tile containing latlon at the map's zoom."""
    srcs = d.execute('return Array.prototype.map.call(document.querySelectorAll("#" + arguments[0] + " img.leaflet-tile-loaded"), t => t.src);', map_id)
    for src in srcs:
        try:
            z, x, y = [int(p) for p in src.rsplit('.png', 1)[0].rsplit('/', 3)[1:]]
        except ValueError:
            continue
        if (x, y) == tile_xy(latlon[0], latlon[1], z):
            return True
    return False


def website_geolocation(d, url, new_tab=False):
    """Open a website and ask it for the user's location through the page's own
    navigator.geolocation, i.e. through the extension's replacement. Returns [lat, lon] or
    an error string."""
    if new_tab:
        d.new_tab()
    d.get(url)
    return d.execute_async(
        d.geolocation_prefix +
        'var cb = arguments[arguments.length - 1];'
        'geo.getCurrentPosition(p => cb([p.coords.latitude, p.coords.longitude]),'
        '                       e => cb("error: " + e.message), { timeout: 15000 });')


# ---------------------------------------------------------------------- checks

def test_fixed_location_tiles_load(d):
    map_id = show_page(d, 'fixedPos')
    assert_real_tile(d, wait_tiles_loaded(d, map_id))


def test_privacy_level_tiles_load(d):
    map_id = show_page(d, 'levels')
    assert_real_tile(d, wait_tiles_loaded(d, map_id))


def test_search_by_name_sets_fixed_location(d):
    map_id = show_page(d, 'fixedPos')
    before = storage_get(d, 'fixedPos')
    assert not near(before, SYDNEY_OPERA, 0.05), 'test precondition: fixed location already at the Sydney Opera House'
    geocoder_search(d, map_id, 'Sydney Opera House')
    pick_first_result_if_listed(d, map_id, 20, lambda: near(storage_get(d, 'fixedPos'), SYDNEY_OPERA, 0.05))
    pos = wait_for(lambda: (lambda p: p if near(p, SYDNEY_OPERA, 0.05) else None)(storage_get(d, 'fixedPos')), 20, 'fixed location to move to the Sydney Opera House')
    assert near(pos, SYDNEY_OPERA, 0.05), pos


def test_search_by_coordinates_sets_fixed_location(d):
    map_id = show_page(d, 'fixedPos')
    geocoder_search(d, map_id, '%s, %s' % NEW_YORK)
    pos = wait_for(lambda: (lambda p: p if near(p, NEW_YORK, 0.0005) else None)(storage_get(d, 'fixedPos')), 20, 'fixed location to move to the typed coordinates')
    assert near(pos, NEW_YORK, 0.0005), pos


def test_search_by_name_recenters_privacy_level_map(d):
    map_id = show_page(d, 'levels')
    wait_tiles_loaded(d, map_id)
    assert not map_shows(d, map_id, SYDNEY_OPERA), 'test precondition: level map already shows the Sydney Opera House'
    geocoder_search(d, map_id, 'Sydney Opera House')
    pick_first_result_if_listed(d, map_id, 20, lambda: map_shows(d, map_id, SYDNEY_OPERA))
    wait_for(lambda: map_shows(d, map_id, SYDNEY_OPERA), 20, 'privacy level map to move to the Sydney Opera House')


def near_list(got, expected, tol_deg=1e-6):
    return isinstance(got, list) and len(got) == 2 and isinstance(expected, dict) \
        and abs(got[0] - expected['latitude']) < tol_deg and abs(got[1] - expected['longitude']) < tol_deg


def _website_receives_fixed_location(d, url):
    set_default_level(d, 'fixed')
    expected = storage_get(d, 'fixedPos')
    got = website_geolocation(d, url)
    assert near_list(got, expected), 'page at %s got %r, fixed location is %r' % (url, got, expected)


def test_website_receives_fixed_location(d):
    """A website asking for the location gets the fixed location: the page-world replacement,
    the page/content message channel, storage and the content script all work."""
    _website_receives_fixed_location(d, 'https://example.com/')


def test_csp_strict_website_receives_fixed_location(d):
    """Same on a page whose Content-Security-Policy forbids inline scripts (github.com), the
    case the old inline <script> injection could not handle."""
    _website_receives_fixed_location(d, 'https://github.com/')


def test_badge_counts_website_call(d):
    """After a website called geolocation, that tab's toolbar badge shows the call count. This
    is the only path that needs the background script: content script -> worker -> action.
    Chromium only (Firefox uses a page action, which has no badge)."""
    set_default_level(d, 'fixed')
    options_tab = d.current_handle()
    website_geolocation(d, 'https://example.com/', new_tab=True)   # a new tab: navigating the
    d.switch_to(options_tab)                                        # website tab away would reset its badge
    show_page(d, 'options')
    badges = wait_for(lambda: (lambda b: b if '1' in b else None)(d.execute_async(
        'var cb = arguments[arguments.length - 1];'
        'chrome.tabs.query({}, tabs => Promise.all(tabs.map(t => chrome.action.getBadgeText({ tabId: t.id }))).then(cb, e => cb(["error: " + e])));')),
        15, 'a tab badge showing 1')
    assert badges.count('1') == 1, badges


TESTS_WEBSITE = [
    test_website_receives_fixed_location,
    test_csp_strict_website_receives_fixed_location,
]


TESTS_OPTIONS = [
    test_fixed_location_tiles_load,
    test_privacy_level_tiles_load,
    test_search_by_name_sets_fixed_location,
    test_search_by_coordinates_sets_fixed_location,
    test_search_by_name_recenters_privacy_level_map,
]


# ---------------------------------------------------------------------- runner

def run_tests(d, tests, only=None, screenshots=None):
    """Run the checks, print one PASS/FAIL line each, return the number of failures."""
    failures = 0
    for t in tests:
        if only and only not in t.__name__:
            continue
        start = time.time()
        try:
            t(d)
            print('PASS %-55s %.1fs' % (t.__name__, time.time() - start))
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print('FAIL %-55s %.1fs\n     %s: %s' % (t.__name__, time.time() - start, type(e).__name__, e))
        if screenshots:
            os.makedirs(screenshots, exist_ok=True)
            try:
                d.screenshot(os.path.join(screenshots, t.__name__ + '.png'))
            except Exception as e:  # noqa: BLE001
                print('     (screenshot failed: %s)' % e)
    print('%d test(s) failed' % failures if failures else 'all tests passed')
    return failures
