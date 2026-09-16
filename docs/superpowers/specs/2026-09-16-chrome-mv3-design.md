# Chrome and Edge support via Manifest V3

Status: revision 2 after design review, awaiting approval. Date: 2026-09-16.

Revision 2 incorporates two independent reviews (a second-model review and
an adversarial code-verified review). Changes from revision 1 are marked
**[rev2]**.

## Goal

Location Guard Revived installs and works in current Google Chrome and
Microsoft Edge. Both stopped loading Manifest V2 extensions in 2025 (Chrome
139 and later refuse them even unpacked), so the Chromium builds (Chrome,
Edge, Opera) move to Manifest V3. The Firefox build stays on Manifest V2 and
is not changed by this work: it is the version under review on
addons.mozilla.org, and Firefox still supports V2.

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
- **[rev2]** Frames with no URL of their own (`about:blank`, `srcdoc`,
  `blob:`). Neither build injects into them today, so a page can read the
  real location through such a frame's `navigator.geolocation`. Fixing it
  needs `match_origin_as_fallback` (Chrome) / `match_about_blank` (Firefox)
  *and* a change to `PostRPC`, whose `targetOrigin` of `window.origin` is
  the string `"null"` in opaque-origin frames and would make `postMessage`
  throw. Both builds are affected equally, so it is tracked as a follow-up
  for both rather than done here.

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
   requests, which we do not want. **[rev2]** Initiator matching uses the
   initiator origin's host, and an extension page's initiator is
   `chrome-extension://<id>`, so this is not a special case that is likely to
   disappear; if a future Chrome rejected the rule, `updateDynamicRules`
   would reject with an error we log, and the smoke test's tile check would
   fail. There is deliberately no silent fallback to an initiator-less rule.
3. **Branded Chrome 137+ ignores `--load-extension`** (the page shows
   "&lt;id&gt; is blocked"). Chrome for Testing honours it, and chromedriver
   can drive it headless with the extension loaded, so an automated test is
   feasible. Developer-mode "Load unpacked" in regular Chrome and Edge is
   unaffected. Branded Edge is presumably the same and is not verified.
4. **No inline scripts or `eval`** exist in the extension's pages or in the
   bundled libraries, so Manifest V3's fixed page CSP (`script-src 'self'`)
   breaks nothing.
5. **The background script already registers every listener synchronously
   at top level** (`main.js` and `Browser._main_script`), which is the
   service-worker requirement. In the worker-bound bundle, `window` appears
   only in `browser_base.js` (`window.browser = chrome`) and in the
   popup-only `closePopup`; there is no `document`, XHR, timer or
   `localStorage` use. The built `common.js` defines `require` as an implicit
   global, so a second file can `importScripts` it and then load `main.js`.
6. **[rev2] Two pre-existing background behaviours matter under a worker.**
   The Firefox page-action workaround in `Browser._main_script` is gated on
   `!needsPAManualHide()`, which is true on Chrome and false on Firefox, the
   opposite of its comment: on Chrome it registers a `tabs.onUpdated`
   listener that is dead code (it only acts when `iconShown` is set, which
   only the page-action path does) but would wake the worker on every tab
   change. And `refreshAllIcons()` runs unconditionally at startup, which on
   a worker means on every wake-up.

## Design

### 1. Manifest

`src/manifest.json` is preprocessed with `cpp` per browser. The shared keys
(`name`, `description`, `author`, `homepage_url`, `icons`, `version`,
`options_ui`) stay shared. The Firefox branch keeps everything it has today.
The `is_chrome || is_edge || is_opera` branch **[rev2: Opera added; it is
Chromium and previously fell into the Firefox-style `#else`]** becomes:

```json
"manifest_version": 3,
"minimum_chrome_version": "111",
"key": "<RSA public key, base64>",
"permissions": ["storage", "declarativeNetRequestWithHostAccess"],
"host_permissions": [
    "*://*.tile.openstreetmap.org/*",
    "*://*.tile.openstreetmap.de/*",
    "*://nominatim.openstreetmap.org/*"
],
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

- **[rev2]** `minimum_chrome_version` 111: `content_scripts[].world` is
  Chrome 111+. An older Chrome would ignore the key, run `inject.js` in the
  isolated world, and let the real location through while the icon claims
  protection. `initiatorDomains`/`requestDomains` (101+) are covered too.
- **[rev2]** `host_permissions` is narrowed to the three OSM hosts. Content
  script injection is granted by `content_scripts.matches` on its own, and
  `modifyHeaders` needs host permission only for the request URL. The
  install-time warning is unchanged (the `<all_urls>` content script already
  produces it) but the Web Store sees the minimum.
- `key` pins the extension ID (`oofmknpjjmooccmkmahaghakbfbclgkk`) so the
  unpacked build, the test harness and a future Web Store listing all share
  it. Only the public key is committed; the private key stays in
  `~/.config/location-guard/chrome-key.pem` and nothing depends on it.
- `declarativeNetRequestWithHostAccess` adds no install-time warning. The
  Firefox-only `webRequest`/`webRequestBlocking` pair is not requested on
  Chromium builds.
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
- `install(browserApi)` decides at runtime and **[rev2] returns a promise
  that resolves once the Referer mechanism is in place**:
  - if `browserApi.webRequest?.onBeforeSendHeaders` exists (Firefox),
    register the blocking listener as today and resolve immediately;
  - otherwise call `declarativeNetRequest.updateDynamicRules({ removeRuleIds:
    [1], addRules: [dnrRule(runtime.id)] })` **[rev2] from both
    `runtime.onInstalled` and `runtime.onStartup`**. The call is idempotent
    and cheap; dynamic rules persist across browser and worker restarts, and
    no case is known where they vanish without one of those events, so no
    `getDynamicRules` inspection is needed. Using `runtime.id` at runtime
    rather than baking the ID into a static ruleset keeps the rule correct if
    a store ever assigns a different ID.
- **[rev2]** The module stays free of any `require` of the `Browser`
  layer, whose module body touches `window`/`chrome` and would break the
  Node unit tests; failures are reported with `console.warn`.
- **[rev2]** `main.js` opens the demo page on first install only after
  `install()`'s promise resolves. The demo page shows a map immediately, and
  without this the first thing a new user sees could be block tiles.

### 3. Page injection

Today `content.js` builds an inline `<script>` from the injected code and
inserts it into the page at `document_start`, falling back to an external
script if the page's CSP blocks inline scripts. On Manifest V3 the manifest
declares `js/content/inject.js` (already built by the Makefile: it is
`injectedCode(PostRPC)`) as a content script in the page's `MAIN` world at
`document_start` in all frames. That runs before any page script, is not
subject to the page's CSP, and needs no DOM manipulation.

`content.js` gains one check: a new capability
`Browser.capabilities.injectsViaManifest()`, **[rev2] true when the manifest
declares a content script with `world: "MAIN"`** (rather than keying on the
manifest version, so a future Firefox V3 event-page build without a
main-world script keeps the inline path), and skips its `insertScript` path
when it is true. The demo-page path (`Browser.inDemo`) is unchanged.
Everything after injection (the `PostRPC` channel over `window.postMessage`,
`getNoisyPosition`, `watchAllowed`, storage, icon refresh) is unchanged.

Ordering between the two `document_start` scripts does not matter: no page
script can run before both have run, and even a synchronous page call
becomes a `postMessage` delivered as a queued task, after `content.js` has
registered its listener synchronously.

### 4. Background service worker

- New file `src/js/background.js`, one line:
  `importScripts('common.js', 'main.js');`. It replaces the Manifest V2
  `scripts` list and needs no bundling; the Makefile copies it into
  `build/<browser>/js/` **[rev2] for Chromium builds only**, so the Firefox
  package carries no stray file.
- `browser_base.js`: `globalThis.browser = chrome` instead of
  `window.browser = chrome`.
- `Browser._main_script`, when the manifest has `action` (Manifest V3):
  - **[rev2]** at top level call `refreshIcon(null)`, which refreshes only
    the default icon and title from one storage read with no tab enumeration
    or messaging (verified: `getIconInfo(null)` skips the RPC because
    `typeof null` is `'object'`). This covers disable-then-enable, where
    Chrome rebuilds the action from manifest defaults and neither
    `onInstalled` nor `onStartup` fires, so a paused user would otherwise see
    the "protecting" icon.
  - run the full `refreshAllIcons()` only on `runtime.onInstalled` and
    `runtime.onStartup`. Per-tab action state (icon, badge, popup URL) is
    kept by the browser while the tab lives, so it needs no re-applying on
    worker wake-ups.
  - **[rev2]** do not register the page-action `tabs.onUpdated` workaround:
    gate it on `!needsPAManualHide() && !permanentIcon()`. Firefox behaviour
    is unchanged (the gate was already false there); Chrome stops registering
    a dead listener that would wake the worker on every tab change. The
    inverted upstream gate itself is noted as a Firefox follow-up.
  - Manifest V2 behaviour is otherwise unchanged.
- `Browser.gui`: the action API is resolved as
  `browser.action || browser.browserAction`;
  `Browser.capabilities.permanentIcon()` returns true when the manifest has
  `action` or `browser_action`. The `pageAction` code paths are Firefox-only
  and untouched.
- **[rev2]** `Browser.rpc.call`: read `browser.runtime.lastError` inside the
  callback and resolve `null` when it is set. Messaging a tab without a
  content script is expected (the popup relies on a null state), and under
  Manifest V3 every unchecked `lastError` is surfaced in the extension's
  Errors panel. Also call `runtime.sendMessage(message, callback)` instead of
  passing `null` as the extension id; the form with `null` works today but
  the two-argument form is the documented one.
- `Browser.log` already guards `browser.extension.getBackgroundPage`, which
  no longer exists; nothing to change.

### 5. Popup and options pages

`action.setPopup` per tab keeps passing `popup.html?tabId=`; `getCallUrl`
uses `tabs.query`; `closePopup` uses `window.close()`. The options page,
demo and FAQ are unchanged. All are already free of inline scripts.

### 6. Build

- Makefile: copy `src/js/background.js` into `build/$*/js/` when `$*` is
  `chrome`, `edge` or `opera`; everything else already exists
  (`build-chrome`, `build-edge`, `package-chrome`, `package-edge`).
- `test-chrome` / `test-edge` / `test-opera` targets keep launching a
  browser with `--load-extension`; the README states they need Chrome for
  Testing or Chromium, since branded Chrome and Edge ignore the flag.

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
  hand-edited manifest, or a future Chrome rejecting the initiator
  condition) is logged with `console.warn`; the maps then show OSM's block
  tile, which is the current behaviour, and nothing else is affected. No
  silent fallback to a broader rule.
- If a page has no `navigator.geolocation` the page-world script does
  nothing, as today.
- A message sent to a tab without a content script resolves to `null` in
  `Browser.rpc.call` with `lastError` consumed; callers already handle a
  null state.

## Testing

Test first, then implementation, per the repo's existing practice.

Unit (`npm test`, node:test):

- `dnrRule(id)` has the documented shape, sets exactly one `Referer` to
  `REFERER`, covers exactly `OSM_HOSTS`, and scopes to the given initiator.
- `install()` with a fake `browser` lacking `webRequest` registers
  `onInstalled` and `onStartup` handlers that each call `updateDynamicRules`
  with `removeRuleIds: [1]` and the rule for `runtime.id`, and its promise
  resolves after the first successful call; with `webRequest` present it
  registers the blocking listener, touches no DNR API, and resolves at once.
  A rejected `updateDynamicRules` is reported and does not throw.
- `injectsViaManifest(manifest)` is true only when a content script has
  `world: "MAIN"`.
- `permanentIcon(manifest)` is true for `action` or `browser_action`.
- The install handler in `main.js` opens the demo page only after the
  Referer promise resolves (fake `Browser.gui.showPage`, ordering asserted).

End-to-end (`test/e2e/chrome_smoke.py`, sharing a common module with the
Firefox script: WebDriver client, page helpers, the five existing checks):

- The five existing checks (tiles on both maps not blocked; search by name
  sets the fixed location; typed coordinates set it; search recenters the
  level map) against `build/chrome` in headless Chrome for Testing through
  chromedriver, navigating directly to `chrome-extension://<id>/options.html`
  (Chrome allows that, unlike Firefox).
- New: `test_website_receives_fixed_location`. Set the default level to
  "fixed" through the options page (the select must get a `change` event,
  which is what saves it), open `https://example.com/`, call
  `navigator.geolocation.getCurrentPosition` from the page context and
  assert the coordinates equal the stored fixed position. This exercises
  main-world injection, `PostRPC`, storage and the content script under
  Manifest V3; nothing tests that path today.
- **[rev2]** New: the same call on a page with a strict CSP
  (`https://github.com/`), which proves the main-world script is not subject
  to page CSP, the one property the inline-script approach lacked.
- **[rev2]** New: after the website call, read
  `chrome.action.getBadgeText({ tabId })` from the options page context and
  assert it is `"1"`. That proves the content script reached the worker and
  the worker updated the action, the only worker-dependent path.
- **[rev2]** The Firefox script gets the website test for parity, using
  `window.wrappedJSObject.navigator.geolocation` because Marionette's
  sandbox would otherwise see the native method through Xray wrappers.

Left untested, on purpose, and recorded here: service-worker restart during
a session; dynamic-rule persistence across a browser restart with a reused
profile; iframes; `watchPosition`; the noise levels themselves; Edge
(same engine, manual check only). There is no CI; adding a workflow that
runs `npm test` and `web-ext lint` is a cheap follow-up outside this spec.

Manual before calling it done: "Load unpacked" in Chrome and in Edge,
visit browserleaks.com/geo, change the site's level from the popup, confirm
the icon and badge update, and confirm the maps and search in the options
page.

## Review outcome and follow-ups

Accepted from review: `minimum_chrome_version`; narrower `host_permissions`;
Opera in the Chromium branch; DNR registration on startup as well as install;
awaiting the rule before opening the demo page; no `Browser` dependency in
`osm_referer.js`; default-icon refresh at worker start; skipping the dead
`tabs.onUpdated` listener on Chromium; `lastError` handling and the
two-argument `sendMessage`; capability keyed on the main-world script;
background.js copied for Chromium builds only; the CSP-strict page, badge
and Firefox-parity tests.

Considered and deferred, with reasons: `match_origin_as_fallback` (needs a
`PostRPC` change, affects both builds, see non-goals); a `getDynamicRules`
repair pass (no known loss scenario, idempotent re-registration on startup
covers it); worker-restart and iframe end-to-end tests (valuable, but not
what this change puts at risk).

Follow-ups outside this spec: opaque-origin frames in both builds; the
top frame's `apiCalledInFrame` handler being registered after an `await` in
`content.js` (a pre-existing race for very early iframe calls); the inverted
page-action workaround gate on Firefox; a CI workflow; Web Store and Edge
Add-ons listing preparation.
