#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h}"
BUILD_DIR="$ROOT/.build/sync-contract"
mkdir -p "$BUILD_DIR/module-cache"

CLANG_MODULE_CACHE_PATH="$BUILD_DIR/module-cache" \
SWIFT_MODULECACHE_PATH="$BUILD_DIR/module-cache" \
swiftc \
  "$ROOT/Sources/LeahCloudAgent/Models.swift" \
  "$ROOT/Tests/EventSnapshotDeltaContract/main.swift" \
  -o "$BUILD_DIR/event-snapshot-delta-contract"

"$BUILD_DIR/event-snapshot-delta-contract"
