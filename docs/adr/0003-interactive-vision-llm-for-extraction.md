# ADR-0003: 抽出はインタラクティブ Vision LLM（API自動化へ昇格可）

- Status: Accepted
- Date: 2026-06-24

## Context
サンプル仕様PDFは文字が画像化されたベクタPDFで、素のテキスト抽出ができなかった
（カスタムCIDフォントで `pdftotext` 不可）。A-1 の「読み取り」をどう実装するかが論点。

## Decision
**Vision LLM をインタラクティブ運用**する。`a_render.py` で PDF→高解像度PNG 化し、
Claude Code 内で Claude（vision）が `raw_extract.md` / `parameters.yaml` を生成、人がレビューする。
追加実装ゼロ・APIキー不要で開始でき、反復運用が必要になれば同一プロンプトを Anthropic API
（`a1_read.py` / `a2_infer.py`、model `claude-opus-4-8` 等）に送る **②自動化へ昇格**できる。

## Alternatives considered
- OCR＋テキスト解析（Tesseract等）: AI依存を減らせるが日本語OCR精度・表構造崩れのリスク。代替として保持。
- 素のテキスト抽出（pdftotext）: 確定的・最速だが**画像化PDFでは不可**。将来テキストPDF向けに保持。
- 完全手動/半自動: 正確だがスケールしない。
- API自動化を最初から: コスト/鍵が必要で、立ち上げが重い。将来の昇格先とする。

ユーザーは Vision LLM に不慣れだったため選択肢を比較提示し、①インタラクティブを選択。

## Consequences
- B・C は A の抽出方式に非依存（`parameters.yaml` の形式さえ合えば後から差し替え可）。
- LLM出力は非決定的だが、A-2 出力は ADR-0004 の DSL＋ADR-0007 の lint＋人間レビューで担保。
