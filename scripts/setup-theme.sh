#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
THEME_DIR="$ROOT/themes/FixIt"
VERSION="${FIXIT_VERSION:-v0.4.5}"

if [[ -f "$THEME_DIR/hugo.toml" ]]; then
  echo "FixIt theme already installed at $THEME_DIR"
  exit 0
fi

mkdir -p "$ROOT/themes"
git clone --depth 1 --branch "$VERSION" git@github.com:hugo-fixit/FixIt.git "$THEME_DIR"
echo "FixIt $VERSION installed."
