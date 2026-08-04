#!/usr/bin/env bash
#
# Build MindFlow for one target, with the compile-time configuration every
# target needs.
#
# It exists because that configuration is not optional and not memorable. The
# API base URL and the Supabase credentials arrive through `--dart-define`; a
# build that forgets them compiles cleanly and produces an application that
# points at `http://localhost:8000` and cannot sign anybody in. That failure
# appears only when somebody runs the artefact, which is usually somebody else.
#
#   ./tool/build.sh web
#   ./tool/build.sh linux --debug
#   MINDFLOW_API_BASE_URL=https://api.mindflow.ai ./tool/build.sh macos
#
# Windows and macOS builds only run on Windows and macOS respectively: Flutter
# links against the platform SDK, and there is no cross-compilation. The script
# refuses rather than emitting a confusing toolchain error.

set -euo pipefail

TARGET="${1:-}"
MODE="${2:---release}"

API_BASE_URL="${MINDFLOW_API_BASE_URL:-http://localhost:8000}"
SUPABASE_URL="${SUPABASE_URL:-}"
SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY:-}"
# Web is served from the root by default. A deployment under a sub-path needs
# this set, and getting it wrong yields a page that loads its own assets with
# 404s — visible immediately, which is why it is a variable and not a guess.
WEB_BASE_HREF="${WEB_BASE_HREF:-/}"

usage() {
  echo "usage: $0 {web|linux|windows|macos} [--release|--debug|--profile]" >&2
  exit 64
}

[[ -n "$TARGET" ]] || usage

host="$(uname -s)"
case "$TARGET" in
  windows)
    [[ "$host" == MINGW* || "$host" == MSYS* || "$host" == CYGWIN* ]] || {
      echo "error: a Windows build requires a Windows host — Flutter links" >&2
      echo "       against the Windows SDK and does not cross-compile." >&2
      exit 1
    }
    ;;
  macos)
    [[ "$host" == "Darwin" ]] || {
      echo "error: a macOS build requires a macOS host with Xcode." >&2
      exit 1
    }
    ;;
  linux|web) ;;
  *) usage ;;
esac

if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_ANON_KEY" ]]; then
  # Not fatal: the local auth mode exists precisely so the client can be built
  # and run without a Supabase project (ADR-036). Saying so beats a login screen
  # that fails for a reason nobody can see.
  echo "note: SUPABASE_URL / SUPABASE_ANON_KEY unset — building with local auth." >&2
  AUTH_DEFINES=(--dart-define=MINDFLOW_LOCAL_AUTH=true)
else
  AUTH_DEFINES=(
    --dart-define=SUPABASE_URL="$SUPABASE_URL"
    --dart-define=SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY"
  )
fi

DEFINES=(--dart-define=MINDFLOW_API_BASE_URL="$API_BASE_URL" "${AUTH_DEFINES[@]}")

echo "→ flutter build $TARGET $MODE  (api: $API_BASE_URL)"

case "$TARGET" in
  web)
    # `--base-href` only applies to web; passing it elsewhere is an error.
    flutter build web "$MODE" --base-href "$WEB_BASE_HREF" "${DEFINES[@]}"
    echo "→ build/web"
    ;;
  linux)
    flutter build linux "$MODE" "${DEFINES[@]}"
    echo "→ build/linux/x64/${MODE#--}/bundle"
    ;;
  windows)
    flutter build windows "$MODE" "${DEFINES[@]}"
    echo "→ build/windows/x64/runner/${MODE#--}"
    ;;
  macos)
    flutter build macos "$MODE" "${DEFINES[@]}"
    echo "→ build/macos/Build/Products/${MODE#--}"
    ;;
esac
