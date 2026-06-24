#!/usr/bin/env bash
# 初回セットアップ: 外部ツール(brew)と Python 依存(uv)を用意する。
# 何度実行しても安全（冪等）。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== 1/2 外部ツールの確認・インストール (brew) =="
need=()
for t in uv pict magick exiftool pdftoppm; do
  if ! command -v "$t" >/dev/null 2>&1; then need+=("$t"); fi
done
if [ "${#need[@]}" -gt 0 ]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew が必要です。https://brew.sh を見てインストールしてください。" >&2
    exit 1
  fi
  echo "  不足: ${need[*]} を brew で入れます…"
  # ツール名とbrew formula名の対応（magick=imagemagick, pdftoppm=poppler）
  brew install uv poppler ghostscript imagemagick exiftool pict
else
  echo "  すべて入っています: uv pict magick exiftool pdftoppm"
fi

echo "== 2/2 Python 依存の同期 (uv) =="
uv sync
echo
echo "セットアップ完了。次は:  bash scripts/run_all.sh   または  make all"
