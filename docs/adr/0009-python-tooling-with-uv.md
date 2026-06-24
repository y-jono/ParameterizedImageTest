# ADR-0009: Python 構成は uv ベース（pip/venv/requirements.txt 不使用）

- Status: Accepted
- Date: 2026-06-24

## Context
Python プロジェクトの依存・実行管理方式の選択。C の生成品質（16bit TIFF・CMYK・ICC・LZW）は
外部ツールにも依存する。

## Decision
- **uv** で管理（`pyproject.toml` + `uv.lock`、実行は `uv run`、同期は `uv sync`）。
  **pip / venv / requirements.txt は使わない**。
- 外部ツール: **ImageMagick + exiftool + PICT**（組合せ）、PDFレンダリングは **poppler(pdftoppm)**（macOS は qlmanage 代替）。
  いずれも `brew install`。
- Python 依存: lark, pydantic, jsonschema, allpairspy, anthropic, PyYAML, pandas。
  （当初入れていた sympy は relations を一方向評価に確定したため未使用となり削除。ADR-0005 参照）

## Alternatives considered
- pip + venv + requirements.txt: 一般的だが解決が遅く lock も別管理。ユーザー要望により却下。
- Pillow のみ（追加ツールなし）: CMYK/16bit TIFF/ICC 埋め込みに制約。却下。

## Consequences
- 高速・再現性のある依存解決（lock）。`uv run` で環境を自動管理。
- ランタイムに brew 外部ツールが必要（セットアップ手順を README に明記）。
