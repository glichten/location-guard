# End-to-end smoke test (Firefox)

`firefox_smoke.py` drives a real Firefox through [geckodriver](https://github.com/mozilla/geckodriver/releases),
installs `build/firefox` as a temporary add-on and checks, against the live
OpenStreetMap servers, that:

- map tiles on the *Privacy Levels* and *Fixed Location* maps are real tiles and
  not OSM's "Access blocked" tile (OSM serves that one with HTTP 200 plus an
  `x-blocked` header, so the header is what the test looks at);
- searching a place name on the *Fixed Location* map sets the fixed location;
- typing `lat, lon` on the *Fixed Location* map sets the fixed location;
- searching a place name on the *Privacy Levels* map recenters that map.

It needs Python 3 (standard library only), geckodriver 0.36 or newer (for
`--allow-system-access`, which the test uses to open `moz-extension://` pages)
and Firefox.

## Linux / macOS

```sh
make build-firefox
python3 test/e2e/firefox_smoke.py --ext-dir build/firefox --headless
```

`--geckodriver` and `--firefox` take explicit binaries; `--screenshots DIR`
saves one PNG per test; `-k name` runs a subset.

## From WSL with Firefox on Windows

Firefox has to be started by a Windows geckodriver and reached over Windows
loopback, so run the script with Windows Python and give it Windows paths.
Everything in the repo is reachable through the `\\wsl.localhost\...` share:

```sh
make build-firefox
W=$(wslpath -w "$PWD")
python.exe "$W\\test\\e2e\\firefox_smoke.py" \
    --ext-dir "$W\\build\\firefox" \
    --geckodriver "C:\\path\\to\\geckodriver.exe" \
    --firefox "C:\\Program Files\\Mozilla Firefox\\firefox.exe" \
    --headless
```

The unit tests (`npm test`) need no browser.
