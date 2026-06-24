# Architecture Decision Records (ADR)

このディレクトリは、本プロジェクトの設計判断を記録する ADR 集です。
各 ADR は「1つの判断」を、文脈・決定・検討した代替案・結果（トレードオフ）とともに残します。
設計プラン全文は [../plan.md](../plan.md)、確定仕様と実行手順は [../../README.md](../../README.md)。

- フォーマット: MADR 簡易版（Status / Context / Decision / Alternatives / Consequences / 実装メモ）
- ステータス: `Proposed` → `Accepted` → （必要なら）`Superseded by ADR-XXXX`
- すべて 2026-06-24 のセッションで合意・採用（Accepted）。

| ADR | タイトル | 要旨 |
|---|---|---|
| [0001](0001-three-stage-pipeline-with-review-gates.md) | 3段パイプライン＋レビューゲート | A→B→C を中間成果物で分割し各段を人がレビュー |
| [0002](0002-split-a-into-read-and-infer.md) | A を読み取り(A-1)と因果推論(A-2)に分離 | 誤読と推論ミスを切り分け可能にする |
| [0003](0003-interactive-vision-llm-for-extraction.md) | 抽出はインタラクティブ Vision LLM | 画像化PDFに対応・追加実装ゼロ・API自動化へ昇格可 |
| [0004](0004-custom-readable-dsl-deterministic-parsing.md) | 専用の可読DSL＋決定的パース | LLMは起草のみ、解釈はパーサ。DMN/FEEL/z3は不採用 |
| [0005](0005-causal-aware-layered-combination-with-pict.md) | 因果を尊重した層別組合せ（PICT） | 独立/派生/連動で分類、強相互作用フル・残りpairwise |
| [0006](0006-lossless-dontcare-compression-plus-pairwise.md) | ロスレス don't-care 圧縮＋pairwise併産 | 全有効空間を漏れなく最小表現＋具体covering set |
| [0007](0007-self-documenting-decomposed-outputs.md) | 自己文書化・関心分割の成果物 | 全プロパティに凡例、Bは5ファイルに分割しレビュー負荷分散 |
| [0008](0008-c-scope-and-generate-then-verify.md) | C の範囲と生成後検証 | JPEG/TIFF自動・PSD手動、intended↔actualを読み戻し突合 |
| [0009](0009-python-tooling-with-uv.md) | uv ベースの Python 構成 | pip/venv/requirements.txt を使わない |
| [0010](0010-anonymize-confidential-spec-source.md) | 機密の仕様出典を匿名化 | 製品名・文書IDを出力に残さない |
