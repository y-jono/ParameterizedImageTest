---
name: parameterized-image-test
description: Run this project's parameterized image-test pipeline (spec PDF → test parameters → decision table → verified input images). Use when the user wants to generate test images from an image-spec document, build/refresh the decision table, author or update parameters.yaml from a spec page, or run stages A/B/C of ParameterizedImageTest. The A stage (reading the spec + inferring parameters) needs the model; B/C are plain scripts.
---

# パラメタライズド画像テスト パイプライン実行スキル

このリポジトリの A→B→C を実行する。A（仕様読解→パラメータ化）はモデルが担い、
B/C は決定的なスクリプト。各段に人間のレビューゲートがある。詳細は `docs/HANDBOOK.md`。

## 前提
- 初回は `bash scripts/setup.sh`（brew + uv）。
- 入力は仕様ページの **PDF または画像**。`specs/` に置く（既定 `specs/spec_sample.pdf`）。
  対応入力（コード変更不要、詳細は docs/HANDBOOK.md 第8節）:
  - PNG/JPEG/GIF(静止)/WebP → **a_render.py 不要**。画像を直接 Read して A-1 へ。
  - PDF → `a_render.py`（pdftoppm で PNG 化、複数ページ対応）。
  - TIFF/BMP/HEIC 等 → 直接は読めないので `magick 入力 出力.png` で PNG 化してから直接 Read。

## 手順

### A-1 読み取り（仕様 → 忠実な転記）
1. 入力を A-1 が読める PNG/JPEG にする:
   - PDF: `uv run python src/a_render.py <pdf>` → `out/1a_extract/<stem>-N.png`
   - すでに PNG/JPEG/GIF/WebP: そのまま次へ（変換不要）
   - TIFF/HEIC 等: `magick <入力> out/1a_extract/<name>.png`
2. その画像を **Read で開いて見て**、`prompts/a1_read.md`（**推論禁止・忠実転記**）に従い
   `out/1a_extract/raw_extract.md` を作成する。
3. ユーザーにレビューを促す（観点: 誤読・取りこぼし）。

### A-2 因果推論（転記 → parameters.yaml）
1. `out/1a_extract/raw_extract.md` と `prompts/a2_infer.md` を読み、
   `out/1b_parameters/parameters.yaml` を作成する。式は専用DSL（`when 条件 then 結果`、`is`/`in`/`and`…）。
   - `kind`: independent / derived(lookup|expr) / coupled(group+partitions)。
   - YAML型変換の罠回避: `none`等はクォート、真偽は `present/absent` 等の別語。
2. **必ず** `uv run python src/a2_lint.py out/1b_parameters/parameters.yaml` を実行し、ERROR が出たら直す。
3. ユーザーにレビューを促す（観点: 軸/値・因果・DSL・オラクル網羅/矛盾）。

### B 組合せ（parameters.yaml → 表）
- `uv run python src/b_table.py`。`out/2_decision_table/` の5ファイルを①→⑤で確認するよう案内。

### C 画像生成＋検証（表 → 画像）
- 最小スイート: `uv run python src/c_generate.py`
- 広域スイート: `uv run python src/c_generate.py --table out/2_decision_table/pairwise.csv --outdir out/3_images_pairwise`
- `out/3_images/verify_report.md` で intended↔actual・rule_consistent を確認。PSD は manual。

## まとめて実行（A 完了後）
- B→C を一括: `bash scripts/run_all.sh`（または `make all`）。
- 健全性のみ: `bash scripts/check.sh`（DSLテスト + lint）。

## 注意
- A の出力（parameters.yaml）さえ正しければ B/C は不変。別仕様への適用は A だけ作り直す。
- 生成画像・検証は決定的。verify_report に不一致が出たら ImageMagick の生成オプションを調整する。
- 機密の仕様出典は匿名化する（製品名・具体的文書IDを残さない）。
