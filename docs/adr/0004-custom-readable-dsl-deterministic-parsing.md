# ADR-0004: 専用の可読DSL＋決定的パース（LLMは起草のみ）

- Status: Accepted
- Date: 2026-06-24

## Context
A-2 の relations/interactions/constraints/oracle/derived を **プログラムで決定的に解釈**したい。
LLM に式を確率的に解釈させたくない。ユーザーは「レビュー可読性が高く・学習コストが低い・
本プログラム専用DSLでも可」を要望。

## Decision
**可読性最優先の専用DSL（imgspec）**を `src/dsl/imgspec.lark`（Lark文法）で定義し、
パーサ（`src/dsl/parser.py`）で **決定的に解釈**する。LLM は文法に従う式を**起草するだけ**。
- 比較 `is`/`is not`/`in`/`> < >= <=`、論理 `and`/`or`/`not`、算術 `+ - * /`、
  ルール `when <条件> then <条件|usable|unusable>`、代入 `<名前> = <算術式>`。
- **constraints は B が内部で PICT 制約文法へトランスパイル**（人はDSLだけ読めばよい）。
- 評価セマンティクス: constraints=全条件成立のみ採用 / oracle=上から first-match＋otherwise / arith=安全評価。

## Alternatives considered
- DMN + FEEL（OMG標準）: 標準準拠で連携性は高いが重く、学習コスト増。却下。
- z3 / SMT-LIB: 最も厳密だが学習コスト高、組合せ網羅戦略との統合が複雑。却下。
- DSLを使わず自由文字列＋LLM解釈: 非決定的でレビュー不能。却下。

## Consequences
- 人間レビューと lint（ADR-0007）を通った式は、B が 100% 決定的に評価できる。
- 文法/評価器を自前保守する必要がある（小規模で許容）。回帰テスト `tests/test_dsl.py`。

## 実装メモ
YAML の型変換罠（`none`/`yes`/`no`/`true`/`false`/`null`）回避のため、値はクォートか別語を使用
（`alpha=present/absent`, `icc_profile=embedded/absent`, `platform_quicktime=installed/absent`,
`compression="none"/"LZW"`）。DSL は bare 語を文字列リテラル、数字を数値として扱う。
