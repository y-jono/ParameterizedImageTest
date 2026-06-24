# ADR-0008: C の範囲（JPEG/TIFF自動・PSD手動）と生成後検証

- Status: Accepted
- Date: 2026-06-24

## Context
3次出力（入力画像）の生成は形式により難易度が異なる。PSD・16bit・CMYK・ICC埋め込みは特に難しい。
また ImageMagick は指定どおりに作れないことがある（例: TIFF+LZW で 16bit を要求しても 8bit に落ちる、
`-alpha on` でも α が付かない、ICC が埋め込まれない）。ユーザーは「JPEG/TIFF を完全自動化、PSD は別扱い」を選択。

## Decision
- **JPEG/TIFF を ImageMagick で完全自動生成**（colorspace/depth/compression/alpha/ICC をフラグで反映）。
  識別可能なテストパターン（グラデーション＋ケースID/パラメータを焼き込み）。
- **PSD は自動生成対象外**。manifest に `generation=manual` と作成手順を記録。
- **生成後検証（必須）**: `exiftool` / `magick identify` で実ファイルを読み戻し、
  **intended（生成時の指定）↔ actual（実測値）** をフィールド単位で突合。1つでも不一致なら失敗として
  `verify_report.md` に記録。「意図したメタデータを実際に持たない画像はテスト入力として無効」だから。

## Alternatives considered
- 生成だけして検証しない: ツールの暗黙変換を見逃しテストが無効化。却下。
- PSD も自動化（psd-tools/GIMP/Photoshop連携）: 実装コスト高。将来課題として別扱い。

## Consequences
- 入力画像が「意図どおりのメタデータを持つ」ことを保証できる（本サンプルで自動分は全件一致を確認）。
- `manifest.csv` は intended/actual/match/expected/source_rule を持ち、将来のアプリ実行テスト
  （画像投入→受理/拒否を expected と突合）にそのまま使える。
- C は decision_table（最小スイート）でも pairwise.csv（広域スイート, 16bit/LZW等を網羅）でも生成可能。

## 実装メモ
ICC 埋め込みは RGB のみ（constraints）。macOS 同梱 `sRGB Profile.icc` を使用。ImageMagick の
既定フォント不在に対応し注釈フォントを明示。寸法はサイズ上限が無いためオラクル非対象＝640x480固定で生成。
