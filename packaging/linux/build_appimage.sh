#!/usr/bin/env bash
# Build dist/PkgFree-x86_64.AppImage. Needs: Python deps + pyinstaller installed, curl.
set -euo pipefail
cd "$(dirname "$0")/../.."

APPIMAGETOOL_VERSION=1.9.1
TOOL="build/appimagetool-${APPIMAGETOOL_VERSION}-x86_64.AppImage"

pyinstaller --noconfirm --onedir --name PkgFree --icon assets/pkgfree.png \
    --exclude-module tkinter pkgfree_main.py

rm -rf build/AppDir
mkdir -p build/AppDir/usr/bin
cp -a dist/PkgFree build/AppDir/usr/bin/PkgFree
cp packaging/linux/AppRun build/AppDir/AppRun
cp packaging/linux/pkgfree.desktop build/AppDir/pkgfree.desktop
cp assets/pkgfree.png build/AppDir/pkgfree.png
ln -sf pkgfree.png build/AppDir/.DirIcon

if [ ! -x "$TOOL" ]; then
    mkdir -p build
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi
# Extract-and-run: CI runners have no FUSE.
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" build/AppDir dist/PkgFree-x86_64.AppImage
echo "Creato dist/PkgFree-x86_64.AppImage"
