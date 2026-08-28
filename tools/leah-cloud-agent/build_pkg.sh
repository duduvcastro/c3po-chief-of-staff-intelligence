#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
APP_NAME="Leah Cloud Agent.app"
OUTPUT="${1:-$ROOT/../../c3po/frontend/public/downloads/leah-cloud-agent-macos.pkg}"
STAGE="$(mktemp -d /tmp/leah-cloud-agent.XXXXXX)"
PACKAGE="$STAGE/leah-cloud-agent-macos.pkg"

trap 'rm -rf "$STAGE"' EXIT

"$ROOT/build_app.sh"
ditto --noextattr --noqtn "$ROOT/dist/$APP_NAME" "$STAGE/$APP_NAME"
xattr -cr "$STAGE/$APP_NAME"
codesign --force --deep --sign - "$STAGE/$APP_NAME"
codesign --verify --deep --strict --verbose=2 "$STAGE/$APP_NAME"
pkgbuild \
  --component "$STAGE/$APP_NAME" \
  --install-location /Applications \
  --identifier br.com.eduardocastro.leah-cloud-agent \
  --version 1.0.2 \
  "$PACKAGE"
mv "$PACKAGE" "$OUTPUT"
shasum -a 256 "$OUTPUT"
