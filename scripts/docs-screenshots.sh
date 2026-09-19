#!/bin/sh
# Re-render the README screenshots from the fabricated demo desktop, never from a real capture.
# Maintainer-only: needs Chromium and ImageMagick. `just check` validates the committed PNGs.
set -eu
cd "$(dirname "$0")/.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
uv run --frozen python scripts/demo-desktop.py "$work" >/dev/null

shot() { # page, CSS height, output name[, CSS width, scale]
    chromium --headless=new --hide-scrollbars --force-device-scale-factor="${5:-2}" \
        --window-size="${4:-1120},$2" --screenshot="$work/$3" "file://$work/$1" 2>/dev/null
    # Palette-reduce and drop every text/time/profile chunk: only pixels may leave this script.
    magick "$work/$3" -strip -define png:exclude-chunks=all -colors 96 "PNG8:docs/assets/$3"
}
mkdir -p docs/assets
shot preview.html 1312 preview-map.png
shot after-reboot.html 1219 preview-after-reboot.png
shot social.html 640 social-preview.png 1280 1 # upload in repo Settings > Social preview
uv run --frozen python scripts/check-portability.py
