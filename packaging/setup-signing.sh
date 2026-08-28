#!/bin/bash
# One-time: make a self-signed code-signing certificate so that every rebuild
# gets the same identity, and macOS treats it as the same program — camera and
# microphone permissions then survive `pyinstaller`.
#
# Idempotent: skips work that is already done. Nothing here needs sudo, but
# `security add-trusted-cert` will ask for your login password once, to record
# the new identity as trusted for code signing in your user trust store.
set -eu

NAME="Lugalay Developer"
KC="$HOME/Library/Keychains/lugalay.keychain-db"
TMP="$(mktemp -d)"
trap "rm -rf $TMP" EXIT

if security find-identity -v -p codesigning | grep -q "$NAME"; then
    echo "already set up: '$NAME' is a valid code-signing identity"
    exit 0
fi

echo "==> generating self-signed cert (never leaves this machine)"
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout "$TMP/key.pem" -out "$TMP/cert.pem" \
    -subj "/CN=$NAME/O=Lugalay" \
    -addext "keyUsage=critical,digitalSignature" \
    -addext "extendedKeyUsage=critical,codeSigning" >/dev/null 2>&1
openssl pkcs12 -export -legacy -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
    -out "$TMP/bundle.p12" -passout pass:lugalay -name "$NAME" >/dev/null 2>&1

echo "==> creating a dedicated keychain for it"
if [ ! -f "$KC" ]; then
    security create-keychain -p lugalay "$KC"
    security set-keychain-settings -lut 21600 "$KC"
fi
security unlock-keychain -p lugalay "$KC"
security import "$TMP/bundle.p12" -k "$KC" -P lugalay \
    -T /usr/bin/codesign >/dev/null 2>&1
security set-key-partition-list -S apple-tool:,apple:,codesign: \
    -s -k lugalay "$KC" >/dev/null 2>&1

echo "==> adding to the keychain search list so codesign finds it"
existing=$(security list-keychains -d user | tr -d '"' | awk '{$1=$1};1')
security list-keychains -d user -s "$KC" $existing

echo "==> marking trusted for code signing (asks for your login password once)"
security add-trusted-cert -r trustRoot -p codeSign -k "$KC" "$TMP/cert.pem"

echo
security find-identity -v -p codesigning | grep "$NAME"
echo "done. Future builds sign with this identity; camera permissions survive."
