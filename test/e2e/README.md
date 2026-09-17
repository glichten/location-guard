# End-to-end smoke tests

`firefox_smoke.py` and `chrome_smoke.py` drive a real browser through its
WebDriver (geckodriver / chromedriver), load the built extension, and run
the checks in `smoke_common.py` against the live OpenStreetMap servers:

- map tiles on the *Privacy Levels* and *Fixed Location* maps are real tiles
  and not OSM's "Access blocked" tile (OSM serves that one with HTTP 200 plus
  an `x-blocked` header, so the header is what the test looks at);
- searching a place name on the *Fixed Location* map sets the fixed location;
- typing `lat, lon` on the *Fixed Location* map sets the fixed location;
- searching a place name on the *Privacy Levels* map recenters that map;
- a website (example.com, and github.com with its strict CSP) asking for the
  location receives the fixed location;
- Chromium only: the toolbar badge of that website's tab counts the call.

They need Python 3 (standard library only) and:

- Firefox plus geckodriver 0.36 or newer (for `--allow-system-access`,
  which the test uses to open `moz-extension://` pages);
- Chrome for Testing (or Chromium) plus a matching chromedriver, both from
  <https://googlechromelabs.github.io/chrome-for-testing/>. Branded Google
  Chrome 137+ ignores `--load-extension`.

## Linux / macOS

```sh
make build-firefox build-chrome
python3 test/e2e/firefox_smoke.py --ext-dir build/firefox --headless
python3 test/e2e/chrome_smoke.py --ext-dir build/chrome --chrome /path/to/chrome-for-testing --headless
```

`--geckodriver` / `--chromedriver` and `--firefox` / `--chrome` take explicit
binaries; `--screenshots DIR` saves one PNG per test; `-k name` runs a subset.

## From WSL with the browsers on Windows

The browsers have to be started by a Windows driver and reached over Windows
loopback, so run the scripts with Windows Python and give them Windows paths.
Everything in the repo is reachable through the `\\wsl.localhost\...` share:

```sh
make build-firefox build-chrome
W=$(wslpath -w "$PWD")
python.exe "$W\\test\\e2e\\firefox_smoke.py" --ext-dir "$W\\build\\firefox" \
    --geckodriver "C:\\path\\to\\geckodriver.exe" \
    --firefox "C:\\Program Files\\Mozilla Firefox\\firefox.exe" --headless
python.exe "$W\\test\\e2e\\chrome_smoke.py" --ext-dir "$W\\build\\chrome" \
    --chromedriver "C:\\path\\to\\chromedriver.exe" \
    --chrome "C:\\path\\to\\chrome-win64\\chrome.exe" --headless
```

The unit tests (`npm test`) need no browser.
