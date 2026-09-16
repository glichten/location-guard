#!/usr/bin/env python3
"""Show the review status of every version of this add-on on addons.mozilla.org.

Uses the same credentials as `make sign-firefox`, read from ~/.web-ext-config.mjs
(apiKey / apiSecret). Standard library only. Run with:  make amo-status

Listing status "incomplete" means no listed version has been submitted yet.
A file status of "unreviewed" is a version awaiting review; "public" is approved
(for the unlisted channel that happens automatically within minutes).
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.request
import uuid

GUID = 'location-guard@glichten.github.io'
API = 'https://addons.mozilla.org/api/v5'


def credentials():
    path = os.path.expanduser('~/.web-ext-config.mjs')
    try:
        cfg = open(path).read()
    except OSError:
        sys.exit('no %s; create it as described in the README' % path)
    key = re.search(r"apiKey:\s*['\"]([^'\"]+)['\"]", cfg)
    secret = re.search(r"apiSecret:\s*['\"]([^'\"]+)['\"]", cfg)
    if not (key and secret):
        sys.exit('%s has no sign.apiKey / sign.apiSecret' % path)
    return key.group(1), secret.group(1)


def jwt(key, secret):
    def b64(data):
        return base64.urlsafe_b64encode(data).rstrip(b'=')
    now = int(time.time())
    header = b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
    payload = b64(json.dumps({'iss': key, 'jti': str(uuid.uuid4()), 'iat': now, 'exp': now + 60}).encode())
    signature = b64(hmac.new(secret.encode(), header + b'.' + payload, hashlib.sha256).digest())
    return (header + b'.' + payload + b'.' + signature).decode()


def get(path, key, secret):
    req = urllib.request.Request(API + path, headers={'Authorization': 'JWT ' + jwt(key, secret)})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main():
    key, secret = credentials()
    addon = get('/addons/addon/%s/' % GUID, key, secret)
    name = addon['name'].get('en-US') if isinstance(addon['name'], dict) else addon['name']
    print('%s  (slug %s)' % (name, addon['slug']))
    print('listing status: %s' % addon['status'])
    print('listing url:    %s' % addon.get('url'))
    print()
    print('%-9s %-9s %-12s %s' % ('version', 'channel', 'file status', 'uploaded'))
    for v in get('/addons/addon/%s/versions/?filter=all_with_unlisted' % GUID, key, secret)['results']:
        f = v.get('file') or {}
        print('%-9s %-9s %-12s %s' % (v['version'], v.get('channel'), f.get('status'), (f.get('created') or '')[:16]))


if __name__ == '__main__':
    main()
