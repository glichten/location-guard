#!/usr/bin/env python3
"""End-to-end smoke test for the Firefox build of Location Guard.

Drives a real Firefox through geckodriver (plain W3C WebDriver over HTTP, no
third-party Python packages), installs the built extension as a temporary
add-on, opens its options page and checks that:

  * OpenStreetMap tiles load with HTTP 200 on both maps (no "Access blocked" 403s)
  * searching a place name on the Fixed Location map sets the fixed location
  * typing "lat, lon" on the Fixed Location map sets the fixed location
  * searching a place name on the Privacy Levels map recenters that map

Usage:

  python3 test/e2e/firefox_smoke.py --ext-dir build/firefox [--geckodriver PATH]
                                    [--firefox PATH] [--headless] [--screenshots DIR]

--ext-dir may also point at a packaged .xpi. The directory is zipped into a
temporary .xpi because Firefox needs a path it can read itself.

The script also runs unchanged under Windows Python, which is how it is driven
from WSL on a machine whose Firefox lives on the Windows side (see test/e2e/README.md).
"""

import argparse
import base64
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

ADDON_ID = 'jid1-HdwPLukcGQeOSh@jetpack'          # gecko id from src/manifest.json
ADDON_UUID = '0c2c8085-650c-4ea8-88e7-3b0dc6d7a3d1'  # pre-seeded so we know the moz-extension:// URL
ELEMENT_KEY = 'element-6066-11e4-a52e-4f735466cecf'
ENTER = '\ue007'   # WebDriver key code for Enter

SYDNEY_OPERA = (-33.8568, 151.2153)
NEW_YORK = (40.7128, -74.0060)


class WebDriver:
    """Minimal W3C WebDriver client."""

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

    def install_addon(self, path, temporary=True):
        return self._s('POST', '/moz/addon/install', {'path': path, 'temporary': temporary})

    def get(self, url):
        self._s('POST', '/url', {'url': url})

    def set_context(self, ctx):
        self._s('POST', '/moz/context', {'context': ctx})

    def trusted_get(self, url):
        """Load a URL that WebDriver refuses to navigate to (moz-extension:// pages) via the browser chrome.

        The load goes into the browser's selected tab, which is not necessarily the tab
        WebDriver is looking at (the extension opens a tab of its own on install), so
        afterwards switch WebDriver to whichever tab now shows the URL."""
        self.set_context('chrome')
        try:
            self.execute(
                'gBrowser.selectedBrowser.loadURI(Services.io.newURI(arguments[0]),'
                '  { triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal() });', url)
        finally:
            self.set_context('content')
        wait_for(lambda: self.switch_to_tab_showing(url), 20, 'a tab showing %s' % url)

    def switch_to_tab_showing(self, url):
        for handle in self._s('GET', '/window/handles'):
            self._s('POST', '/window', {'handle': handle})
            if self.execute('return location.href;') == url:
                return handle
        return None

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


# ---------------------------------------------------------------- page helpers

def options_url(page):
    return 'moz-extension://%s/options.html#%s' % (ADDON_UUID, page)


def show_page(d, page):
    """Navigate the options page to one of its jQuery Mobile pages and wait for its map."""
    d.trusted_get(options_url(page))
    map_id = {'fixedPos': 'fixedPosMap', 'levels': 'levelMap'}[page]
    wait_for(lambda: d.execute(
        'var m = document.getElementById(arguments[0]);'
        'return m && m.classList.contains("leaflet-container") && document.getElementById(arguments[1]).classList.contains("ui-page-active");',
        map_id, page), 20, 'page %s to show its map' % page)
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


def assert_real_tile(d, srcs):
    r = tile_response(d, srcs[0])
    assert r['status'] == 200 and not r.get('blocked'), \
        'tile request from the options page was rejected by OSM: %s (resource statuses: %s)' % (r, resource_statuses(d, 'tile.openstreetmap'))


def resource_statuses(d, host_fragment):
    """responseStatus of already-recorded resource loads (0 when the server hides it)."""
    return d.execute(
        'return performance.getEntriesByType("resource")'
        '  .filter(e => e.name.indexOf(arguments[0]) >= 0)'
        '  .map(e => e.responseStatus);', host_fragment)


def fixed_pos(d):
    return d.execute_async(
        'var cb = arguments[arguments.length - 1];'
        'browser.storage.local.get("global").then(r => cb(r.global ? r.global.fixedPos : null), e => cb("error: " + e));')


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
    return pos and abs(pos['latitude'] - target[0]) < tol_deg and abs(pos['longitude'] - target[1]) < tol_deg


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


# ---------------------------------------------------------------------- tests

def test_fixed_location_tiles_load(d):
    map_id = show_page(d, 'fixedPos')
    assert_real_tile(d, wait_tiles_loaded(d, map_id))


def test_privacy_level_tiles_load(d):
    map_id = show_page(d, 'levels')
    assert_real_tile(d, wait_tiles_loaded(d, map_id))


def test_search_by_name_sets_fixed_location(d):
    map_id = show_page(d, 'fixedPos')
    before = fixed_pos(d)
    assert not near(before, SYDNEY_OPERA, 0.05), 'test precondition: fixed location already at the Sydney Opera House'
    geocoder_search(d, map_id, 'Sydney Opera House')
    pick_first_result_if_listed(d, map_id, 20, lambda: near(fixed_pos(d), SYDNEY_OPERA, 0.05))
    pos = wait_for(lambda: fixed_pos(d) if near(fixed_pos(d), SYDNEY_OPERA, 0.05) else None, 20, 'fixed location to move to the Sydney Opera House')
    assert near(pos, SYDNEY_OPERA, 0.05), pos


def test_search_by_coordinates_sets_fixed_location(d):
    map_id = show_page(d, 'fixedPos')
    geocoder_search(d, map_id, '%s, %s' % NEW_YORK)
    pos = wait_for(lambda: fixed_pos(d) if near(fixed_pos(d), NEW_YORK, 0.0005) else None, 20, 'fixed location to move to the typed coordinates')
    assert near(pos, NEW_YORK, 0.0005), pos


def test_search_by_name_recenters_privacy_level_map(d):
    map_id = show_page(d, 'levels')
    wait_tiles_loaded(d, map_id)
    assert not map_shows(d, map_id, SYDNEY_OPERA), 'test precondition: level map already shows the Sydney Opera House'
    geocoder_search(d, map_id, 'Sydney Opera House')
    pick_first_result_if_listed(d, map_id, 20, lambda: map_shows(d, map_id, SYDNEY_OPERA))
    wait_for(lambda: map_shows(d, map_id, SYDNEY_OPERA), 20, 'privacy level map to move to the Sydney Opera House')


TESTS = [
    test_fixed_location_tiles_load,
    test_privacy_level_tiles_load,
    test_search_by_name_sets_fixed_location,
    test_search_by_coordinates_sets_fixed_location,
    test_search_by_name_recenters_privacy_level_map,
]


# ----------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ext-dir', required=True, help='unpacked extension dir (build/firefox) or a packaged .xpi')
    ap.add_argument('--geckodriver', default='geckodriver', help='geckodriver executable (default: from PATH)')
    ap.add_argument('--firefox', default=None, help='firefox binary (default: geckodriver picks one)')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--screenshots', default=None, help='directory to save a screenshot per test')
    ap.add_argument('-k', dest='only', default=None, help='run only tests whose name contains this')
    args = ap.parse_args()

    if args.ext_dir.lower().endswith('.xpi'):
        xpi, cleanup_xpi = os.path.abspath(args.ext_dir), False
    else:
        xpi, cleanup_xpi = package_xpi(args.ext_dir), True

    port = free_port()
    # --allow-system-access lets us switch Marionette to the chrome context (see trusted_get)
    gd = subprocess.Popen([args.geckodriver, '--host', '127.0.0.1', '--port', str(port), '--allow-system-access'],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    d = WebDriver('http://127.0.0.1:%d' % port)
    failures = 0
    try:
        wait_for(lambda: _alive(d), 15, 'geckodriver to start')
        ff = {'prefs': {
            'extensions.webextensions.uuids': json.dumps({ADDON_ID: ADDON_UUID}),
            'geo.enabled': False,               # keep the locate control from prompting
        }, 'args': []}
        if args.firefox:
            ff['binary'] = args.firefox
        if args.headless:
            ff['args'].append('-headless')
        d.new_session({'browserName': 'firefox', 'moz:firefoxOptions': ff})
        d.set_timeouts(script=60000, pageLoad=60000)
        addon = d.install_addon(xpi, temporary=True)
        assert addon == ADDON_ID, 'unexpected add-on id %r' % addon
        time.sleep(1)   # let the background page start

        for t in TESTS:
            if args.only and args.only not in t.__name__:
                continue
            start = time.time()
            try:
                t(d)
                print('PASS %-55s %.1fs' % (t.__name__, time.time() - start))
            except Exception as e:  # noqa: BLE001 - report every failure, keep going
                failures += 1
                print('FAIL %-55s %.1fs\n     %s: %s' % (t.__name__, time.time() - start, type(e).__name__, e))
            if args.screenshots:
                os.makedirs(args.screenshots, exist_ok=True)
                try:
                    d.screenshot(os.path.join(args.screenshots, t.__name__ + '.png'))
                except Exception as e:  # noqa: BLE001
                    print('     (screenshot failed: %s)' % e)
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
        gd.terminate()
        try:
            gd.wait(10)
        except subprocess.TimeoutExpired:
            gd.kill()
        if cleanup_xpi:
            try:
                os.remove(xpi)
            except OSError:
                pass

    print('%d test(s) failed' % failures if failures else 'all tests passed')
    return 1 if failures else 0


def _alive(d):
    try:
        d._req('GET', '/status')
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == '__main__':
    sys.exit(main())
