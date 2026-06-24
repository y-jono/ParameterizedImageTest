# 新人向けの簡単な入口。`make help` で一覧。
# 例: make setup → make all
PARAMS ?= out/1b_parameters/parameters.yaml
SPEC   ?= specs/spec_sample.pdf

.PHONY: help setup render lint build images images-pairwise all test clean

help:           ## このヘルプを表示
	@echo "使い方: make <target>"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup:          ## 初回セットアップ（brew + uv）
	bash scripts/setup.sh

render:         ## 仕様PDFを画像化（A-1 の前処理）。SPEC=... で差し替え可
	uv run python src/a_render.py $(SPEC)

lint:           ## parameters.yaml を機械チェック（A-2 の検証ゲート）
	uv run python src/a2_lint.py $(PARAMS)

build:          ## B: ディシジョンテーブル一式を生成
	uv run python src/b_table.py $(PARAMS)

images:         ## C: 最小スイートの画像生成＋検証 → out/3_images/
	uv run python src/c_generate.py --params $(PARAMS)

images-pairwise: ## C: 広域(pairwise)スイートも生成 → out/3_images_pairwise/
	uv run python src/c_generate.py --params $(PARAMS) \
	  --table out/2_decision_table/pairwise.csv --outdir out/3_images_pairwise

all:            ## lint→B→C→C(pairwise) を一括実行
	bash scripts/run_all.sh

test:           ## DSL回帰テスト + lint（画像は作らない）
	bash scripts/check.sh

clean:          ## 生成物(B/C)を削除（A の成果物 1a/1b は残す）
	rm -rf out/2_decision_table out/3_images out/3_images_pairwise
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	@echo "cleaned (out/1a_extract と out/1b_parameters は保持)"
