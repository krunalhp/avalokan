#!/usr/bin/env bash
# Opens YouTube in a Desktop-window Chrome where you can sign in.
# The profile lives at ~/.config/google-chrome so yt-dlp (configured with
# AVALOKAN_YTDLP_COOKIES_FROM_BROWSER=chrome) can read the session cookies.
set -euo pipefail

chrome=$(ls -d "$HOME"/.agent-browser/browsers/chrome-*/chrome 2>/dev/null | sort -V | tail -n1)
if [[ -z "$chrome" ]]; then
  echo "No Chrome for Testing binary found under ~/.agent-browser/browsers" >&2
  exit 1
fi

exec "$chrome" \
  --user-data-dir="$HOME/.config/google-chrome" \
  --password-store=basic \
  --test-type \
  --no-first-run \
  --no-default-browser-check \
  --window-size=790,700 \
  --window-position=2,2 \
  "https://www.youtube.com/"
