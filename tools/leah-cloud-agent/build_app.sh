#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
OUTPUT="${ROOT}/dist/Leah Cloud Agent.app"

cd "$ROOT"
"$ROOT/test_sync.sh"
swift build --disable-sandbox -c release
rm -rf "$OUTPUT"
mkdir -p "$OUTPUT/Contents/MacOS" "$OUTPUT/Contents/Resources"
cp ".build/release/LeahCloudAgent" "$OUTPUT/Contents/MacOS/LeahCloudAgent"
cp "Resources/Info.plist" "$OUTPUT/Contents/Info.plist"
cp "../../c3po/frontend/public/nina-castro-mark.svg" "$OUTPUT/Contents/Resources/nina-castro-mark.svg"
codesign --force --deep --sign - "$OUTPUT"
echo "$OUTPUT"
