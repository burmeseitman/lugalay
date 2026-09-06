#!/bin/bash
# Sign the built app with a stable identity so macOS microphone/camera
# permissions survive upgrades. Fall back to ad-hoc only on machines where the
# local Lugalay certificate has not been installed yet.
set -euo pipefail

APP="${1:-dist/Lugalay.app}"

if [ ! -d "$APP" ]; then
    echo "sign: no app at $APP" >&2
    exit 1
fi

# Use ad-hoc signing by default so no Keychain password prompt ever appears
IDENTITY="${CODESIGN_IDENTITY:--}"

chmod -R u+w "$APP" || true
if [ -d "$APP/Contents/Frameworks" ]; then
    find "$APP/Contents/Frameworks" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 | xargs -0 -n 1 codesign --force -s "$IDENTITY" 2>/dev/null || true
fi

if [ -f "$APP/Contents/MacOS/Lugalay" ]; then
    codesign --force -s "$IDENTITY" "$APP/Contents/MacOS/Lugalay"
fi

codesign --force -s "$IDENTITY" "$APP"

if [ "$IDENTITY" != "-" ]; then
    who=$(codesign -dvvv "$APP" 2>&1 | grep '^Authority=' | head -1 || true)
    echo "sign: $who"
else
    echo "sign: ad-hoc signed (no keychain prompt)"
fi
