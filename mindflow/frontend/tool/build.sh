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
#   ./tool/build.sh android
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
  echo "usage: $0 {web|linux|android|windows|macos} [--release|--debug|--profile]" >&2
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
  android)
    # Un téléphone ne joint pas le `localhost` de la machine de développement.
    # Le dire ici épargne la demi-heure passée à chercher pourquoi
    # l'application « ne fait rien » : elle appelle une adresse qui, pour elle,
    # n'existe pas.
    if [[ "$API_BASE_URL" == *localhost* || "$API_BASE_URL" == *127.0.0.1* ]]; then
      echo "warning: MINDFLOW_API_BASE_URL vaut $API_BASE_URL." >&2
      echo "         Sur un téléphone, cette adresse désigne le téléphone." >&2
      echo "         Utilisez l'IP de cette machine sur le réseau local," >&2
      echo "         ou 10.0.2.2 depuis l'émulateur Android." >&2
    fi
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
    # CanvasKit is served from our own origin, not from gstatic.com.
    #
    # By default a Flutter web build fetches its renderer from a Google CDN at
    # start-up. That is fatal here for two separate reasons: an application
    # whose entire point is working without a network cannot begin by
    # downloading 19 MB from a third party, and any deployment behind a proxy
    # that does not allow gstatic.com shows a blank page with a console error
    # nobody outside the team can interpret. Verified, not assumed — the first
    # build of this client failed to boot in a headless Chromium for exactly
    # this reason.
    #
    # `--no-web-resources-cdn` is what makes the renderer local. It emits
    # `canvaskit/` into the bundle and sets `useLocalCanvasKit` in the loader
    # config, so the bootstrap stops falling back to the CDN.
    #
    # `--base-href` only applies to web; passing it elsewhere is an error.
    flutter build web "$MODE" \
      --base-href "$WEB_BASE_HREF" \
      --no-web-resources-cdn \
      "${DEFINES[@]}"

    if [[ ! -d build/web/canvaskit ]]; then
      echo "warning: no local canvaskit/ in the bundle — this build will fetch" >&2
      echo "         its renderer from gstatic.com and fail without a network." >&2
    fi
    echo "→ build/web"
    ;;
  linux)
    flutter build linux "$MODE" "${DEFINES[@]}"
    echo "→ build/linux/x64/${MODE#--}/bundle"
    ;;
  android)
    # `apk` et non `appbundle` : ce qui s'installe sur son propre téléphone.
    # Un `.aab` ne s'installe pas, il se dépose sur une boutique.
    flutter build apk "$MODE" "${DEFINES[@]}"
    echo "→ build/app/outputs/flutter-apk/app-${MODE#--}.apk"
    echo "  Installation : adb install -r build/app/outputs/flutter-apk/app-${MODE#--}.apk"
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
