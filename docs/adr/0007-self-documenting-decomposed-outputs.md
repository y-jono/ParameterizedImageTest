# ADR-0007: 自己文書化・関心分割の成果物＋機械lint

- Status: Accepted
- Date: 2026-06-24

## Context
B の処理が複雑化し、1枚の大きな決定表ではレビュー負荷が高い。ユーザーは
(1) 出力スキーマの全プロパティに凡例コメントを付けマニュアル不要にすること、
(2) 独立因子・組合せ強度ペア・constraints・派生の分割観点を **それぞれ別の成果物** にすること、
(3) 派生（同値/境界）の **分割観点（rationale）** をコメント出力すること、を要望。

## Decision
- **横断原則: すべての出力を自己文書化**（各ファイル冒頭に凡例＝列の意味＋レビュー観点）。
- **B 出力を関心ごとに分割**して段階レビュー:
  ① `independent_factors.md` ② `interaction_strength.md` ③ `constraints.md`
  ④ `derived_partitions.md`（同値/境界＋観点） ⑤ `decision_table.md/.csv`（統合）＋ `profiles.csv` / `pairwise.csv`。
- **A-2 は機械 lint（`a2_lint.py`）で差し戻し**: 構造（pydantic）＋全DSL式パース＋名前解決＋lookup整合＋
  oracle 網羅/矛盾（到達不能ルール検出）。失敗は赤表示。

## Alternatives considered
- 単一の決定表に全部入れる: レビュー負荷が高く、誤りの所在が見えにくい。却下。
- 人手レビューのみ（lintなし）: タイポ/非網羅/矛盾を見落とす。却下。

## Consequences
- レビュアーは ①→⑤ の順に小さく確認でき、各ファイルの凡例だけで読める。
- ③constraints は「落とす組合せ数＋例」、④derived は「kind＝boundary/normal＋rationale」を自動算出し表示。
- lint 通過＝決定的解釈可能な状態、を保証してから人間レビューに回せる。
