#!/usr/bin/env python3
"""End-to-end smoke test for the Chromium (Manifest V3) build of Location Guard.

Drives Chrome for Testing (or Chromium) through chromedriver with the unpacked
extension loaded, opens its options page and runs the checks in smoke_common.py.
Branded Google Chrome 137+ ignores --load-extension, so give --chrome a Chrome for
Testing binary (https://googlechromelabs.github.io/chrome-for-testing/).

Usage:

  python3 test/e2e/chrome_smoke.py --ext-dir build/chrome [--chromedriver PATH]
                                   [--chrome PATH] [--headless] [--screenshots DIR]

The extension directory is copied to a local temporary directory first, because
the browser must be able to read it and the source may be on a network share.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smoke_common import (WebDriver, TESTS_OPTIONS, TESTS_WEBSITE, alive, copy_ext_dir,  # noqa: E402
                          free_port, run_tests, test_badge_counts_website_call, wait_for)

EXT_ID = 'oofmknpjjmooccmkmahaghakbfbclgkk'   # pinned by the "key" in src/manifest.json


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ext-dir', required=True, help='unpacked extension dir (build/chrome)')
    ap.add_argument('--chromedriver', default='chromedriver', help='chromedriver executable (default: from PATH)')
    ap.add_argument('--chrome', default=None, help='Chrome for Testing / Chromium binary (default: chromedriver picks one)')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--screenshots', default=None, help='directory to save a screenshot per test')
    ap.add_argument('-k', dest='only', default=None, help='run only tests whose name contains this')
    args = ap.parse_args()

    ext_dir = copy_ext_dir(args.ext_dir)
    profile = tempfile.mkdtemp(prefix='location-guard-profile-')
    port = free_port()
    cd = subprocess.Popen([args.chromedriver, '--port=%d' % port], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    d = WebDriver('http://127.0.0.1:%d' % port)
    d.ext_origin = 'chrome-extension://' + EXT_ID
    failures = 0
    try:
        wait_for(lambda: alive(d), 15, 'chromedriver to start')
        opts = {'args': ['--load-extension=' + ext_dir, '--user-data-dir=' + profile,
                         '--no-first-run', '--no-default-browser-check']}
        if args.chrome:
            opts['binary'] = args.chrome
        if args.headless:
            opts['args'].append('--headless=new')
        d.new_session({'browserName': 'chrome', 'goog:chromeOptions': opts})
        d.set_timeouts(script=60000, pageLoad=60000)
        time.sleep(2)   # let onInstalled run: it registers the OSM Referer rule and opens the demo tab
        failures = run_tests(d, TESTS_OPTIONS + TESTS_WEBSITE + [test_badge_counts_website_call], args.only, args.screenshots)
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
        cd.terminate()
        try:
            cd.wait(10)
        except subprocess.TimeoutExpired:
            cd.kill()
        shutil.rmtree(ext_dir, ignore_errors=True)
        shutil.rmtree(profile, ignore_errors=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
