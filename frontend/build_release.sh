#!/bin/bash
set -e

# SoulPulse Flutter Release Build Script
# Includes obfuscation and split-debug-info for release builds

API_BASE_URL="${API_BASE_URL:-http://123.57.227.61}"
DEBUG_INFO_DIR="build/debug-info"

echo "=== SoulPulse Release Build ==="
echo "API_BASE_URL: $API_BASE_URL"
echo "Debug info output: $DEBUG_INFO_DIR"
echo ""

# Ensure debug-info directory exists
mkdir -p "$DEBUG_INFO_DIR"

build_apk() {
    echo "[APK] Building Android release with obfuscation..."
    flutter build apk --release \
        --obfuscate \
        --split-debug-info="$DEBUG_INFO_DIR" \
        --dart-define=API_BASE_URL="$API_BASE_URL"
    echo "[APK] Done: build/app/outputs/flutter-apk/app-release.apk"
}

build_ios() {
    echo "[iOS] Building iOS release with obfuscation..."
    flutter build ios --release \
        --obfuscate \
        --split-debug-info="$DEBUG_INFO_DIR" \
        --dart-define=API_BASE_URL="$API_BASE_URL"
    echo "[iOS] Done."
}

build_web() {
    echo "[Web] Building web release..."
    flutter build web --release \
        --dart-define=API_BASE_URL="$API_BASE_URL"
    echo "[Web] Done: build/web/"
}

# Parse arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 [apk|ios|web|all]"
    echo ""
    echo "  apk  - Build Android APK with obfuscation"
    echo "  ios  - Build iOS with obfuscation"
    echo "  web  - Build web (no obfuscation needed)"
    echo "  all  - Build all targets"
    exit 0
fi

for target in "$@"; do
    case "$target" in
        apk) build_apk ;;
        ios) build_ios ;;
        web) build_web ;;
        all)
            build_apk
            build_ios
            build_web
            ;;
        *)
            echo "Unknown target: $target"
            echo "Valid targets: apk, ios, web, all"
            exit 1
            ;;
    esac
done

echo ""
echo "=== Build Complete ==="
echo "Debug symbols saved to: $DEBUG_INFO_DIR"
echo "Keep debug-info for crash symbolication!"
