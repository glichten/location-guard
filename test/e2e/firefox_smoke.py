#!/usr/bin/env python3
"""End-to-end smoke test for the Firefox build of Location Guard.

Drives a real Firefox through geckodriver, installs the built extension as a temporary
add-on, opens its options page and runs the checks in smoke_common.py:

  * OpenStreetMap tiles load with real tiles on both maps (no "Access blocked" tiles)
  * searching a place name on the Fixed Location map sets the fixed location
  * typing "lat, lon" on the Fixed Location map sets the fixed location
  * searching a place name on the Privacy Levels map recenters that map
  * a website's navigator.geolocation gets the fixed location, also on a strict-CSP page

Usage:

  python3 test/e2e/firefox_smoke.py --ext-dir build/firefox [--geckodriver PATH]
                                    [--firefox PATH] [--headless] [--screenshots DIR]

--ext-dir may also point at a packaged .xpi. The directory is zipped into a
temporary .xpi because Firefox needs a path it can read itself.

The script also runs unchanged under Windows Python, which is how it is driven
from WSL on a machine whose Firefox lives on the Windows side (see test/e2e/README.md).
"""

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_common import (WebDriver, TESTS_OPTIONS, TESTS_WEBSITE, alive, free_port,  # noqa: E402
                          package_xpi, run_tests, wait_for)

ADDON_ID = 'location-guard@glichten.github.io'   # gecko id from src/manifest.json
ADDON_UUID = '0c2c8085-650c-4ea8-88e7-3b0dc6d7a3d1'  # pre-seeded so we know the moz-extension:// URL


class FirefoxDriver(WebDriver):
    # Depending on the Firefox version, Marionette either runs scripts in a sandbox that sees
    # page objects through Xray wrappers -- which hide the extension's replacement of
    # navigator.geolocation, so the wrappers have to be waived -- or directly against the
    # page's own window, where `wrappedJSObject` does not exist. Handle both.
    geolocation_prefix = ('var win = window.wrappedJSObject || window;'
                          'var geo = win.navigator.geolocation;')

    def set_context(self, ctx):
        self._s('POST', '/moz/context', {'context': ctx})

    def install_addon(self, path, temporary=True):
        return self._s('POST', '/moz/addon/install', {'path': path, 'temporary': temporary})

    def open_extension_page(self, url):
        """WebDriver refuses to navigate to moz-extension:// pages, so load the URL through the
        browser chrome. The load goes into the browser's selected tab, which is not
        necessarily the one WebDriver is looking at (the extension opens a tab of its own on
        install), so afterwards switch WebDriver to whichever tab now shows the URL."""
        self.set_context('chrome')
        try:
            self.execute(
                'gBrowser.selectedBrowser.loadURI(Services.io.newURI(arguments[0]),'
                '  { triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal() });', url)
        finally:
            self.set_context('content')
        wait_for(lambda: self.switch_to_tab_showing(url), 20, 'a tab showing %s' % url)

    def switch_to_tab_showing(self, url):
        for handle in self.handles():
            self.switch_to(handle)
            if self.execute('return location.href;') == url:
                return handle
        return None


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
    # --allow-system-access lets us switch Marionette to the chrome context (see open_extension_page)
    gd = subprocess.Popen([args.geckodriver, '--host', '127.0.0.1', '--port', str(port), '--allow-system-access'],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    d = FirefoxDriver('http://127.0.0.1:%d' % port)
    d.ext_origin = 'moz-extension://' + ADDON_UUID
    failures = 0
    try:
        wait_for(lambda: alive(d), 15, 'geckodriver to start')
        ff = {'prefs': {
            'extensions.webextensions.uuids': json.dumps({ADDON_ID: ADDON_UUID}),
            # Deny geolocation instead of switching it off: geo.enabled=false removes
            # navigator.geolocation altogether, and then the extension has nothing to replace,
            # so a website could never receive the fixed location. Denying keeps the object
            # there and still stops the maps' locate control from prompting.
            'permissions.default.geo': 2,
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
        failures = run_tests(d, TESTS_OPTIONS + TESTS_WEBSITE, args.only, args.screenshots)
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
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
