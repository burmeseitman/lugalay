#!/bin/bash
# Sign the built app with Lugalay's own code-signing identity, if one exists.
#
# Ad-hoc signing gives every rebuild a new identity, which macOS TCC treats as
# a different program — so camera and microphone permissions dropped on every
# build. A self-signed certificate stays put; permissions survive.
#
# Set up once by running packaging/setup-signing.sh. Skips silently otherwise
# so a fresh clone still builds; falls back to ad-hoc in that case.
set -eu

APP="${1:-dist/Lugalay.app}"
IDENTITY="Lugalay Developer"
KC="$HOME/Library/Keychains/lugalay.keychain-db"

if [ ! -d "$APP" ]; then
    echo "sign: no app at $APP" >&2
    exit 1
fi

if [ -f "$KC" ] && security find-identity -v -p codesigning \
        | grep -q "$IDENTITY"; then
    codesign --force --deep --keychain "$KC" -s "$IDENTITY" "$APP" 2>&1 | tail -1
    who=$(codesign -dvvv "$APP" 2>&1 | grep '^Authority=' | head -1)
    echo "sign: $who"
else
    codesign --force --deep -s - "$APP" 2>&1 | tail -1
    echo "sign: ad-hoc (run packaging/setup-signing.sh once for stable identity)"
fi
