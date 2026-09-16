
find = $(foreach dir,$(1),$(foreach d,$(wildcard $(dir)/*),$(call find,$(d),$(2))) $(wildcard $(dir)/$(strip $(2))))

FIREFOX ?= $(shell which firefox)
CHROME  ?= $(shell which google-chrome)
EDGE    ?= $(shell which microsoft-edge)
OPERA   ?= $(shell which opera)
VER      = $(shell perl -ne 'print $$1 and exit if /"version":\s*"([^"]*)"/' src/manifest.json)


default:
	@echo "\nbuilding:"
	@echo make build-chrome
	@echo make build-firefox
	@echo "\npackaging:"
	@echo make package-chrome
	@echo make package-firefox
	@echo "\nsigning (needs AMO API credentials, see README):"
	@echo make sign-firefox
	@echo "\ntesting:"
	@echo make [CHROME=/path/to/google-chrome] test-chrome
	@echo make [FIREFOX=/path/to/firefox] test-firefox
	@echo make test-firefox-android
	@echo

clean:
	rm -rf build/


# build ##############################################################

build-chrome: build/chrome
build-opera: build/opera
build-firefox: build/firefox
build-edge: build/edge

COMMON_MODULES = -x ./src/js/common/browser_base.js -x ./src/js/common/browser.js -x ./src/js/common/util.js -x ./src/js/common/post-rpc.js -x ./src/js/common/laplace.js -x leaflet -x leaflet.locatecontrol -x intro.js -x jquery -x sglide

# no trailing slash on the target: GNU make 4.4+ handles $@/$* of directory targets
# written as build/%/ inconsistently, so the slash is added explicitly below
build/%: $(call find, src, *)
	rm -rf $@
	mkdir -p $@
	cp -r src/* $@/
	rm $@/js/*.js $@/js/**/*.js

	# bundles with common modules
	npx browserify -r ./src/js/common/browser_base.js -r ./src/js/common/browser.js -r ./src/js/common/util.js -r ./src/js/common/post-rpc.js -r ./src/js/common/laplace.js  > $@/js/common.js
	npx browserify -r leaflet -r leaflet.locatecontrol -r intro.js -r jquery -r sglide ./src/js/gui/load-globals.js   > $@/js/common-gui.js

	# jquery has no proper npm package, we just append the code (from jquery-mobile-babel-safe) into common-gui.js. See also load-globals.js.
	cat ./node_modules/jquery-mobile-babel-safe/js/jquery.mobile-1.4.5.js >> $@/js/common-gui.js
	# leaflet-control-geocoder ships ES2022 syntax that browserify's parser rejects, so it is appended
	# the same way; it attaches itself to the global L exposed by load-globals.js
	cat ./node_modules/leaflet-control-geocoder/dist/Control.Geocoder.js >> $@/js/common-gui.js

	# entry points
	npx browserify $(COMMON_MODULES) ./src/js/main.js            > $@/js/main.js
	npx browserify $(COMMON_MODULES) ./src/js/content/content.js > $@/js/content/content.js
	npx browserify $(COMMON_MODULES) ./src/js/gui/options.js     > $@/js/gui/options.js
	npx browserify $(COMMON_MODULES) ./src/js/gui/demo.js        > $@/js/gui/demo.js
	npx browserify $(COMMON_MODULES) ./src/js/gui/popup.js       > $@/js/gui/popup.js
	npx browserify $(COMMON_MODULES) ./src/js/gui/faq.js         > $@/js/gui/faq.js

	npx browserify ./src/js/content/inject.js                    > $@/js/content/inject.js

	# copy module css/images
	cp -r node_modules/jquery-mobile-babel-safe/css/images node_modules/jquery-mobile-babel-safe/css/jquery.mobile-1.4.5.min.css $@/css/
	cp -r node_modules/leaflet/dist/images                 node_modules/leaflet/dist/leaflet.css                                 $@/css/
	cp node_modules/leaflet-control-geocoder/dist/Control.Geocoder.css                                                         $@/css/
	cp node_modules/intro.js/minified/introjs.min.css                                                                            $@/css/

	cpp -P -Dis_$* src/manifest.json > $@/manifest.json
	perl -pi -e 's/%BUILD%/$*/' $@/js/common.js


# package #############################################################

package-chrome:  build/location-guard-chrome-$(VER).zip
package-opera:   build/location-guard-opera-$(VER).zip
package-firefox: build/location-guard-firefox-$(VER).xpi
package-edge:    build/location-guard-edge-$(VER).zip

build/location-guard-%-$(VER).zip: build/%
	rm -f build/location-guard-$*-$(VER).zip
	(cd build/$* && zip -r ../location-guard-$*-$(VER).zip .)

build/location-guard-%-$(VER).xpi: build/location-guard-%-$(VER).zip
	mv $< $@


# sign #################################################################

# Release Firefox only keeps signed extensions. Mozilla signs self-distributed
# ("unlisted") add-ons through its API; web-ext takes the credentials from
# ~/.web-ext-config.mjs or from WEB_EXT_API_KEY / WEB_EXT_API_SECRET.
sign-firefox: build/firefox
	npx web-ext sign --channel unlisted --source-dir build/firefox --artifacts-dir build/signed

# review status of the versions on addons.mozilla.org (same credentials as sign-firefox)
amo-status:
	python3 scripts/amo_status.py

# test #################################################################

test-chrome: build/chrome
	@rm -rf /tmp/lg-chrome-profile
	$(CHROME) --load-extension=build/chrome --user-data-dir=/tmp/lg-chrome-profile --no-first-run --no-default-browser-check

test-opera: build/opera
	@rm -rf /tmp/lg-opera-profile
	$(OPERA) --load-extension=build/opera --user-data-dir=/tmp/lg-opera-profile --no-first-run --no-default-browser-check

test-firefox: build/firefox
	npx web-ext --source-dir build/firefox -f $(FIREFOX) run --browser-console

test-firefox-android: build/location-guard-firefox-$(VER).xpi
	adb push build/location-guard-firefox-$(VER).xpi /mnt/sdcard/
	adb shell am start -a android.intent.action.VIEW -n org.mozilla.firefox/.App -d 'file:///mnt/sdcard/location-guard-firefox-$(VER).xpi'

test-edge: build/edge
	@rm -rf /tmp/lg-edge-profile
	$(EDGE) --load-extension=build/edge --user-data-dir=/tmp/lg-edge-profile --no-first-run --no-default-browser-check
