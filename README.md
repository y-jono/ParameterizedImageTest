# ParameterizedImageTest

画像レイアウトアプリ向けの **パラメタライズド画像テスト基盤**。
仕様ドキュメント（画像ファイル仕様ページ）を起点に、テストパラメータ → ディシジョンテーブル →
入力画像 を **3段パイプライン** で生成する。各段は人間がレビュー・編集できる中間成果物を出し、
その成果物が次段の入力になる（レビューゲート方式）。

```
仕様PDF ─[A1:読み取り]──→ out/1a_extract/raw_extract.md       …(レビュー: 読めたか)
        ─[A2:因果推論]──→ out/1b_parameters/parameters.yaml   …(レビュー: モデル化が正しいか / a2_lint で機械検査)
        ─[B]───────────→ out/2_decision_table/*               …(レビュー: 関心ごとに分割した5ファイル)
        ─[C]───────────→ out/3_images/* + manifest + verify   …(レビュー: 意図↔実測の一致)
```

## ドキュメント
- 設計プラン（設計時スナップショット）: [docs/plan.md](docs/plan.md)
- 設計判断の記録（ADR）: [docs/adr/](docs/adr/README.md) — 3段構成・A分割・Vision LLM・専用DSL・層別組合せ・
  ロスレス圧縮・自己文書化・C範囲と検証・uv構成・匿名化 の10件

## セットアップ
```bash
brew install uv poppler ghostscript imagemagick exiftool pict
uv sync          # pyproject.toml / uv.lock から依存をインストール
# 仮想環境は uv が自動管理。venv / pip / requirements.txt は使わない。
```

## 使い方（A → B → C）

### A-1 読み取り（仕様 → 忠実な転記）
```bash
uv run python src/a_render.py specs/spec_sample.pdf      # PDF→PNG
```
→ 生成された PNG と `prompts/a1_read.md` を使い、Claude Code 内でページ内容を
`out/1a_extract/raw_extract.md` に **忠実に転記**（推論禁止）。
**レビュー**: 誤読・取りこぼしが無いか。

### A-2 因果推論（転記 → パラメータ因果モデル）
`out/1a_extract/raw_extract.md` と `prompts/a2_infer.md` を使い、Claude Code 内で
`out/1b_parameters/parameters.yaml` を作成。式は専用DSL（下記）で記述。
```bash
uv run python src/a2_lint.py out/1b_parameters/parameters.yaml   # 機械検査（必須）
```
→ 構造・全DSL式のパース・名前解決・lookup整合・oracle網羅/矛盾を検査し、問題はレビューに差し戻す。
**レビュー**: 軸/値・kind分類・relations/interactions・DSL式・オラクルの網羅/矛盾。

### B 組合せ（パラメータ → ディシジョンテーブル）
```bash
uv run python src/b_table.py
```
→ `out/2_decision_table/` に **関心ごとに分割した自己文書化ファイル**を生成（各冒頭に凡例）:
1. `independent_factors.md` — 独立因子と値
2. `interaction_strength.md` — 組合せ強度（full / pairwise）
3. `constraints.md` — 制約と除外例
4. `derived_partitions.md` — 派生/連動の同値・境界＋観点
5. `decision_table.md` / `.csv` — 全有効空間を don't-care 圧縮した最小ルール（ロスレス）
   - `profiles.csv` — 連動グループ geometry の代表プロファイル
   - `pairwise.csv` — PICT covering set（pairwise＋強相互作用フル網羅）

**レビュー**: ①→②→③→④→⑤ の順に段階的に。各ファイルの凡例だけで読める。

### C 画像生成＋検証（テーブル → 入力画像）
```bash
uv run python src/c_generate.py                          # decision_table から最小スイート → out/3_images/
uv run python src/c_generate.py --table out/2_decision_table/pairwise.csv \
                                --outdir out/3_images_pairwise   # 広域スイート（16bit/LZW等も網羅）
```
→ ImageMagick で画像生成後、**exiftool/identify で読み戻して intended と突合**。
- `manifest.csv` — intended（要求値）/ actual（実測値）/ match / expected（oracle判定）/ 由来ルール
- `verify_report.md` — 各画像の意図↔実測の一致/不一致（✓/✗）
- PSD は自動生成対象外。`generation=manual` で記録し、作成手順を report に出力。

**レビュー**: 画像が意図どおりか、検証で不一致が無いか、PSD手動対象の妥当性。

## 専用DSL（imgspec, `src/dsl/imgspec.lark`）
可読性最優先・低学習コスト。LLM は式の起草のみ、解釈はパーサが決定的に行う。
- 比較: `is` / `is not` / `in [..]` / `> < >= <=`
- 論理: `and` / `or` / `not` / `( )`
- 算術: `+ - * / ( )`
- ルール: `when <条件> then <条件 | usable | unusable>`
- 代入: `<名前> = <算術式>`（relations）
- 例: `when format is JPEG then bit_depth is 8` / `when color_mode in [CMYK, Grayscale] then unusable`
- YAMLの罠回避: `none`/`yes`/`no`/`true`/`false` は値として使うときクォート、または別語（`present`/`absent`）。

## ディレクトリ
```
specs/        入力PDF
prompts/      A-1 / A-2 のプロンプト
src/dsl/      DSL 文法・パーサ・評価・PICTトランスパイル
src/schema/   parameters.yaml の pydantic モデル & JSON Schema
src/derive.py 共有評価エンジン（制約/派生/オラクル/空間列挙）
src/*.py      a_render / a2_lint / b_table / c_generate / image_spec
out/          各段の成果物（レビュー対象）
tests/        DSL 回帰テスト（uv run python tests/test_dsl.py）
```

## 別仕様への適用 / 拡張
- 別の仕様ページに使うときは A-1→A-2 で新しい `parameters.yaml` を作るだけ。B・C は不変。
- 寸法/サイズ上限が判明したら `limits` に設定し、`oracle` に `when file_size > max_file_size then unusable` を追加。
- `manifest.csv` は将来のアプリ実行テスト（画像投入→受理/拒否を expected と突合）にそのまま使える。
