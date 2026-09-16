# Chrome and Edge support via Manifest V3

Status: proposal, awaiting review. Date: 2026-09-16.

## Goal

Location Guard Revived installs and works in current Google Chrome and
Microsoft Edge. Both stopped loading Manifest V2 extensions in 2025 (Chrome
139 and later refuse them even unpacked), so the Chrome and Edge builds move
to Manifest V3. The Firefox build stays on Manifest V2 and is not changed by
this work: it is the version under review on addons.mozilla.org, and Firefox
still supports V2.

Done means: `make build-chrome` produces a directory that loads through
"Load unpacked" in Chrome and Edge, with the options page maps and search
working (no OSM "Access blocked" tiles), the icon and popup working, and a
website that calls `navigator.geolocation.getCurrentPosition` receiving the
fake location. The same is proven by an automated smoke test against Chrome.

## Non-goals

- Moving Firefox to Manifest V3. Firefox needs an event page rather than a
  service worker; that is a later step with its own spec.
- Publishing to the Chrome Web Store or Edge Add-ons. Listing preparation is
  a follow-up once the build is verified.
- Any change to the user interface, privacy model, or noise mechanism.

## Findings that shape the design

All verified on this machine on 2026-09-16 with Chrome 152.

1. **Chromium sends no Referer from extension pages**, exactly like
   Firefox. A probe extension's page fetched `httpbin.org/headers` and OSM
   tiles: no `Referer` header arrived, `Sec-Fetch-Site: none`, and OSM served
   its block tile with the `x-blocked` header. The upstream issue comment
   claiming the Chrome V3 fork "works fine" is not reproducible.
2. **A `declarativeNetRequest` `modifyHeaders` rule fixes it**, and the rule
   can be scoped to the extension's own requests: `initiatorDomains` accepts
   the extension ID. With that rule OSM delivered real tiles and httpbin saw
   `Referer: https://github.com/glichten/location-guard`; without the
   initiator filter the rule also works but would rewrite every website's OSM
   requests, which we do not want.
3. **Branded Chrome 137+ ignores `--load-extension`** (the page shows
   "&lt;id&gt; is blocked"). Chrome for Testing honours it, and chromedriver
   can drive it headless with the extension loaded, so an automated test is
   feasible. Developer-mode "Load unpacked" in regular Chrome and Edge is
   unaffected.
4. **No inline scripts or `eval`** exist in the extension's pages or in the
   bundled libraries, so Manifest V3's fixed page CSP (`script-src 'self'`)
   breaks nothing.
5. **The background script already registers every listener synchronously
   at top level** (`main.js` and `Browser._main_script`), which is the
   service-worker requirement. Two things are not service-worker safe:
   `browser_base.js` assigns `window.browser = chrome` (`window` does not
   exist in a worker), and the background bundle relies on `js/common.js`
   being loaded first by the manifest's `scripts` list, which Manifest V3
   replaces with a single `service_worker` file.

## Design

### 1. Manifest

`src/manifest.json` is preprocessed with `cpp` per browser. The shared keys
(`name`, `description`, `author`, `homepage_url`, `icons`, `version`,
`options_ui`) stay shared. The Firefox branch keeps everything it has today.
The `is_chrome || is_edge` branch becomes:

```json
"manifest_version": 3,
"key": "<RSA public key, base64>",
"permissions": ["storage", "declarativeNetRequestWithHostAccess"],
"host_permissions": ["<all_urls>"],
"background": { "service_worker": "js/background.js" },
"action": {
    "default_icon": { ...same sizes as today... },
    "default_popup": "popup.html",
    "default_title": "Location Guard Revived"
},
"content_scripts": [
    { "js": ["js/content/inject.js"],
      "matches": ["<all_urls>"], "run_at": "document_start", "all_frames": true,
      "world": "MAIN" },
    { "js": ["js/common.js", "js/content/content.js"],
      "matches": ["<all_urls>"], "run_at": "document_start", "all_frames": true }
]
```

Notes:

- `key` pins the extension ID (`oofmknpjjmooccmkmahaghakbfbclgkk`) so the
  unpacked build, the test harness and a future Web Store listing all share
  it. Only the public key is committed; the private key stays in
  `~/.config/location-guard/chrome-key.pem` and nothing depends on it.
- `declarativeNetRequestWithHostAccess` adds no install-time warning beyond
  the `<all_urls>` host access the extension already needs for its content
  script. The Firefox-only `webRequest`/`webRequestBlocking` pair is not
  requested on Chrome.
- `data_collection_permissions` is a Firefox key and stays in the Firefox
  branch.
- No `web_accessible_resources`: with the main-world content script nothing
  is loaded from the page.

### 2. Referer for OpenStreetMap (`src/js/osm_referer.js`)

The module keeps `REFERER`, `URL_PATTERNS`, `refererHeaders()` and the
blocking-webRequest path, and gains a second strategy:

- `OSM_HOSTS = ['tile.openstreetmap.org', 'tile.openstreetmap.de',
  'nominatim.openstreetmap.org']`, from which `URL_PATTERNS` is derived.
- `dnrRule(extensionId)` returns one rule: `id 1`, `priority 1`, action
  `modifyHeaders` setting `Referer` to `REFERER`, condition
  `requestDomains: OSM_HOSTS` (DNR domain matching includes subdomains such
  as `a.tile.openstreetmap.org`), `initiatorDomains: [extensionId]`,
  `resourceTypes: ['image', 'xmlhttprequest', 'other']`.
- `install(browserApi)` decides at runtime: if
  `browserApi.webRequest?.onBeforeSendHeaders` exists, register the blocking
  listener as today (Firefox). Otherwise, on `runtime.onInstalled` (fires on
  install, update and developer reloads) call
  `declarativeNetRequest.updateDynamicRules({ removeRuleIds: [1], addRules:
  [dnrRule(runtime.id)] })`. Dynamic rules persist across browser restarts and
  service-worker restarts, so registering on install is enough and avoids
  rewriting the rule on every worker wake-up. Using `runtime.id` at runtime
  rather than baking the ID into a static ruleset keeps the rule correct if a
  store ever assigns a different ID.

### 3. Page injection

Today `content.js` builds an inline `<script>` from the injected code and
inserts it into the page at `document_start`, falling back to an external
script if the page's CSP blocks inline scripts. On Manifest V3 the manifest
declares `js/content/inject.js` (already built by the Makefile: it is
`injectedCode(PostRPC)`) as a content script in the page's `MAIN` world at
`document_start` in all frames. That runs before any page script, is not
subject to the page's CSP, and needs no DOM manipulation.

`content.js` gains one check: a new capability
`Browser.capabilities.injectsViaManifest()`, true when
`browser.runtime.getManifest().manifest_version >= 3`, and skips its
`insertScript` path when it is true. The demo-page path (`Browser.inDemo`)
is unchanged. Everything after injection (the `PostRPC` channel over
`window.postMessage`, `getNoisyPosition`, `watchAllowed`, storage, icon
refresh) is unchanged.

### 4. Background service worker

- New file `src/js/background.js`, one line:
  `importScripts('common.js', 'main.js');`. It replaces the Manifest V2
  `scripts` list and needs no bundling; the Makefile copies it into
  `build/<browser>/js/` (the build deletes and regenerates everything else
  under `js/`).
- `browser_base.js`: `globalThis.browser = chrome` instead of
  `window.browser = chrome`.
- `Browser._main_script`: the unconditional `refreshAllIcons()` at startup
  runs only on `runtime.onInstalled` and `runtime.onStartup` when
  `manifest_version >= 3`. A Manifest V3 worker starts many times per
  session and each start would otherwise query every tab and message every
  content script; per-tab action state (icon, badge, popup URL) is kept by
  the browser while the tab lives, so it does not need re-applying on wake.
  Manifest V2 behaviour is unchanged.
- `Browser.gui`: the action API is resolved as
  `browser.action || browser.browserAction`;
  `Browser.capabilities.permanentIcon()` returns true when the manifest has
  `action` or `browser_action`. The `pageAction` code paths are Firefox-only
  and untouched.
- `Browser.log` already guards `browser.extension.getBackgroundPage`, which
  no longer exists; nothing to change.
- `Browser.rpc` uses callback-style `tabs.sendMessage` /
  `runtime.sendMessage`, which Chrome still supports in Manifest V3. Unchanged.

### 5. Popup and options pages

`action.setPopup` per tab keeps passing `popup.html?tabId=`; `getCallUrl`
uses `tabs.query`; `closePopup` uses `window.close()`. The options page,
demo and FAQ are unchanged. All are already free of inline scripts.

### 6. Build

- Makefile: copy `src/js/background.js` into the build's `js/` directory
  after the bundling step; everything else already exists (`build-chrome`,
  `build-edge`, `package-chrome`, `package-edge`).
- `test-chrome` / `test-edge` Makefile targets keep launching the system
  browser with `--load-extension`; they will only work with Chrome for
  Testing or Chromium now, and the README says so.

## Data flow (unchanged, restated for the Manifest V3 case)

1. Page loads. Chrome runs `inject.js` in the page world and
   `common.js`+`content.js` in the isolated world, both before page scripts.
2. Page calls `navigator.geolocation.getCurrentPosition`. The page-world
   replacement sends `getNoisyPosition` over `PostRPC` (`window.postMessage`
   to `window.origin`).
3. `content.js` reads settings from `storage.local`, either returns the
   fixed position or calls the real API and adds noise, and asks the
   background (via `runtime.sendMessage`) to refresh the tab's icon. In an
   iframe it asks the background to echo `apiCalledInFrame` to the top frame.
4. The background service worker wakes for those messages, updates
   `action` state for the tab, and goes idle again.
5. Options page maps request OSM tiles and Nominatim; the dynamic DNR rule
   adds the Referer because the initiator is the extension.

## Error handling

- `updateDynamicRules` failure (for example the permission missing in a
  hand-edited manifest) is logged through `Browser.log`; the maps then show
  OSM's block tile, which is the current behaviour, and nothing else is
  affected.
- If a page has no `navigator.geolocation` the page-world script does
  nothing, as today.
- A message sent to a tab without a content script resolves to `undefined`
  in `Browser.rpc.call`, as today; callers already handle a null state.

## Testing

Test first, then implementation, per the repo's existing practice.

Unit (`npm test`, node:test):

- `dnrRule(id)` has the documented shape, sets exactly one `Referer` to
  `REFERER`, covers exactly `OSM_HOSTS`, and scopes to the given initiator.
- `install()` with a fake `browser` lacking `webRequest` registers an
  `onInstalled` listener whose handler calls `updateDynamicRules` with
  `removeRuleIds: [1]` and the rule for `runtime.id`; with `webRequest`
  present it registers the blocking listener and touches no DNR API.
- `injectsViaManifest(manifest)` is true for `manifest_version` 3 and false
  for 2.
- `permanentIcon(manifest)` is true for `action` or `browser_action`.

End-to-end (`test/e2e/chrome_smoke.py`, sharing a common module with the
Firefox script: WebDriver client, page helpers, the five existing checks):

- The five existing checks (tiles on both maps not blocked; search by name
  sets the fixed location; typed coordinates set it; search recenters the
  level map) against `build/chrome` in headless Chrome for Testing through
  chromedriver, navigating directly to `chrome-extension://<id>/options.html`
  (Chrome allows that, unlike Firefox).
- New: `test_website_receives_fixed_location`. Set the default level to
  "fixed" through the options page, open `https://example.com/`, call
  `navigator.geolocation.getCurrentPosition` from the page context and
  assert the coordinates equal the stored fixed position. This exercises
  main-world injection, `PostRPC`, storage and the content script under
  Manifest V3; nothing tests that path today. The same check is added to
  the Firefox script for parity.

Manual before calling it done: "Load unpacked" in Chrome and in Edge,
visit browserleaks.com/geo, change the site's level from the popup, confirm
the icon and badge update, and confirm the maps and search in the options
page.

## Risks and open questions for review

1. `initiatorDomains` with an extension ID is verified on Chrome 152 but is
   not documented behaviour. Fallback if a future version rejects it: drop
   the initiator condition (the rule then applies to all OSM requests in the
   browser, replacing websites' own Referer) or use session rules keyed to
   the options tab. Is the verified behaviour acceptable to rely on?
2. Registering the DNR rule only on `onInstalled`: is there a case where the
   dynamic rule is lost without `onInstalled` firing again (profile
   corruption, browser downgrade), and is a cheap `getDynamicRules` check on
   `onStartup` worth adding?
3. Both content scripts are `document_start`; the page-world script needs
   the isolated-world message listener to exist by the time a page script
   calls geolocation. Page scripts cannot run before both have run, so
   ordering between the two should not matter. Confirm.
4. Worker safety of the shared modules: a grep of `browser_base.js`,
   `util.js`, `post-rpc.js`, `laplace.js`, `osm_referer.js` and `main.js`
   finds `window` only in the `window.browser = chrome` assignment (the rest
   are comments), and no `document`. `common.js` also bundles `browser.js`,
   whose `window.close()` sits inside `closePopup` and is never reached in
   the worker. Reviewers may know of spots the grep would miss.
5. `refreshAllIcons` moved off the per-wake path: any case where the action
   icon for an existing tab would be stale after a browser restart that
   `onStartup` does not cover?
6. Edge: same engine, but the Edge Add-ons store assigns its own extension
   ID regardless of `key`. The DNR rule uses `runtime.id` at runtime so this
   is fine; is anything else ID-dependent?
