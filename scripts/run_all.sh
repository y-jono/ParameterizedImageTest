#!/usr/bin/env bash
# B→C を一気通貫で実行する（LLM・エージェント不要）。
# 前提: A の成果物 out/1b_parameters/parameters.yaml が存在すること
#       （サンプルは同梱済み。別仕様で使うときは先に parameters.yaml を用意）。
set -euo pipefail
cd "$(dirname "$0")/.."

PARAMS="out/1b_parameters/parameters.yaml"
if [ ! -f "$PARAMS" ]; then
  echo "ERROR: $PARAMS がありません。" >&2
  echo "  A（仕様→条件）を先に用意してください（docs/HANDBOOK.md の手順4-A）。" >&2
  exit 1
fi

echo "############ STEP A検証: parameters.yaml を機械チェック (a2_lint) ############"
uv run python src/a2_lint.py "$PARAMS"

echo
echo "############ STEP B: ディシジョンテーブル生成 (b_table) ############"
uv run python src/b_table.py "$PARAMS"

echo
echo "############ STEP C: 画像生成＋検証（最小スイート） (c_generate) ############"
uv run python src/c_generate.py --params "$PARAMS"

echo
echo "############ STEP C(広域): pairwise スイートも生成 ############"
uv run python src/c_generate.py --params "$PARAMS" \
    --table out/2_decision_table/pairwise.csv --outdir out/3_images_pairwise

cat <<'EOF'

============================================================
完了しました。次の順で成果物を見てください（詳しくは docs/HANDBOOK.md 手順5）:
  1) out/2_decision_table/independent_factors.md   テストの軸と値
  2) out/2_decision_table/interaction_strength.md  どの組合せを厚く試すか
  3) out/2_decision_table/constraints.md           あり得ない組合せの除外
  4) out/2_decision_table/derived_partitions.md    計算で決まる値・境界値
  5) out/2_decision_table/decision_table.md        圧縮済みの最終表（正解付き）
  6) out/3_images/verify_report.md                 生成画像が意図どおりかの検証
  7) out/3_images/manifest.csv                     1画像=1行の台帳
============================================================
EOF
