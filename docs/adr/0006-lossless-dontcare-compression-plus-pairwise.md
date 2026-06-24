# ADR-0006: ロスレス don't-care 圧縮を主、pairwise を併産

- Status: Accepted
- Date: 2026-06-24

## Context
「全テストケースを人間がレビュー可能なサイズに圧縮したディシジョンテーブル」をどう解釈するか。
ロスレス（全ケースを漏れなく表現）と pairwise（サンプリングで縮約、一部組合せは落ちる）はトレードオフ。
ユーザーは「両方を併用」を選択。

## Decision
- **主出力＝ロスレス don't-care 圧縮**: 全有効空間（制約適用後）を verdict ごとに、結果に効かない条件を
  `—`（don't-care）に畳んで最小ルール化（Quine–McCluskey 風 greedy）。**全ケースを漏れなく表現**しつつ行数最小。
- **併産＝pairwise（PICT covering set）**: pairwise＋強相互作用フル網羅の具体ケース集合（`pairwise.csv`）。
  圧縮ルールが閾値を超えるときの実用的な縮約スイートとして提示。

## Alternatives considered
- pairwise のみ: 小さいが一部組合せが落ちる（ロッシー）。主出力には不適。
- ロスレスのみ: 漏れないが大きくなり得る。pairwise を補完として併産。

## Consequences
- decision_table はロスレス（本サンプル: 有効78→**10ルール**）でレビューしやすい。
- C は decision_table から最小スイート、pairwise から広域スイートのどちらも生成可（ADR-0008）。

## 実装メモ
キューブは「同一 verdict の有効組合せのみ」を覆う（無効領域をまたがない）方針。完全最小ではないが
正確・レビュー容易。ロスレス性は再展開して verdict 一致を検証（mismatches=0 を確認済み）。
