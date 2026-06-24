#!/usr/bin/env bash
# 健全性チェック: DSL の回帰テストと parameters.yaml の lint だけを実行（画像生成はしない）。
# 変更後に「壊れていないか」を素早く確かめたいとき用。
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== DSL 回帰テスト =="
uv run python tests/test_dsl.py

echo
echo "== a2_lint（parameters.yaml の機械チェック）=="
uv run python src/a2_lint.py out/1b_parameters/parameters.yaml

echo
echo "OK: チェック完了。"
