#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 APP_PATH" >&2
  exit 64
fi
: "${APPLE_TEAM_ID:?Missing Apple team ID}"
: "${MACOS_SIGNING_IDENTITY:?Missing Developer ID signing identity}"
: "${SAFARI_BUNDLE_ID:?Missing Safari bundle ID}"
APP_PATH="$1"
ENTITLEMENTS="$(cd "$(dirname "$0")/../.github/apple" && pwd)/safari.entitlements"
actual_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$APP_PATH/Contents/Info.plist")
[[ "$actual_id" == "$SAFARI_BUNDLE_ID" ]] || { echo "Unexpected app bundle ID" >&2; exit 1; }
# Xcode's converter produces one Safari extension. Sign inside out, never using
# --deep to sign (it is used only for verification).
shopt -s nullglob
extensions=("$APP_PATH"/Contents/PlugIns/*.appex)
[[ ${#extensions[@]} -eq 1 ]] || { echo "Expected one Safari extension" >&2; exit 1; }
for extension in "${extensions[@]}"; do
  extension_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$extension/Contents/Info.plist")
  [[ "$extension_id" == "$SAFARI_BUNDLE_ID".* ]] || { echo "Unexpected extension bundle ID" >&2; exit 1; }
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" \
    --sign "$MACOS_SIGNING_IDENTITY" "$extension"
done
codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" \
  --sign "$MACOS_SIGNING_IDENTITY" "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
for bundle in "${extensions[@]}" "$APP_PATH"; do
  team=$(codesign -d --verbose=4 "$bundle" 2>&1 | sed -n 's/^TeamIdentifier=//p')
  [[ "$team" == "$APPLE_TEAM_ID" ]] || { echo "Unexpected signing team" >&2; exit 1; }
  sandbox=$(codesign -d --entitlements :- "$bundle" 2>/dev/null | plutil -extract 'com\.apple\.security\.app-sandbox' raw -o - -)
  [[ "$sandbox" == true ]] || { echo "App sandbox is missing" >&2; exit 1; }
done
