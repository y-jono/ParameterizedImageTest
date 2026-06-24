# A-2 因果推論プロンプト（パラメータモデル化）

あなたはテスト設計者です。A-1 の転記（`out/1a_extract/raw_extract.md`）を入力に、
画像メタデータの **テストパラメータ因果モデル** を `out/1b_parameters/parameters.yaml` として作成します。
判断の根拠は必ず転記内の記述に求め、推測した箇所は `notes` に明記してください。

## 出力スキーマ
> 注意: `src/schema/parameters.schema.json` は **構造の目安** にすぎません（`name` と `kind` 程度しか必須にできない）。
> kind 別の必須フィールド・DSL 式の妥当性・oracle の網羅/矛盾は **`src/a2_lint.py`（pydantic＋DSL＋oracle検査）が権威**です。
> JSON Schema だけで valid でも a2_lint で不合格になり得ます。**必ず a2_lint を通して**ください。

- `source`: 出典（転記ファイル名や仕様ページ名）
- `parameters[]`: 各パラメータ。`kind` で分類する。
  - `independent`: 自由に選べる軸。`values: [...]`
  - `derived`: 他から計算で決まる（軸にしない）。
    - 写像なら `lookup: {from: <param>, map: {値: 数}}`（＋必要なら `plus_if: {when: "<DSL条件>", add: N}`）
    - 算術なら `expr: "<DSL算術式>"`
  - `coupled`: 連動グループの一員。`group: <名前>`, `partitions: [代表値...]`（同値/境界）
- `relations[]`: 連動の拘束式（DSL代入）。例 `"physical_w_inch = width / resolution"`
- `interactions[]`: 全網羅したい強相互作用ペア。例 `[[channels, bit_depth], ...]`
- `constraints[]`: 不可能組合せの除去（DSL）。例 `"when format is JPEG then bit_depth is 8"`
- `oracle`: 期待結果。`hit_policy: first`, `rules: ["when <cond> then usable|unusable", ...]`, `otherwise: usable|unusable`
- `limits`: `max_dimension`, `max_file_size`（仕様に数値があれば、無ければ null）
- `notes[]`: 推測・将来の軸候補など

## DSL（式の文法・可読性優先）
- 比較: `is` / `is not` / `in [..]` / `> < >= <=`（`=`/`!=`/`<>` も同義だが、可読性のため `is`/`is not` を推奨）
- 論理: `and` / `or` / `not` / `( )`
- 算術: `+ - * / ( )`
- ルール: `when <条件> then <条件 | usable | unusable>`
- 代入: `<名前> = <算術式>`
- **YAMLの罠回避**: `none`/`yes`/`no`/`true`/`false`/`null` は YAML が型変換するため、
  値として使うときは **クォートする**（例 `values: ["none", "LZW"]`）か、別語（`present`/`absent` 等）にする。

## 必須の品質
- `oracle` は `otherwise` を含め **全有効ケースを網羅** し、**矛盾（同条件で別判定）が無い** こと。
- すべての DSL 式は `src/dsl/imgspec.lark` でパースできること。
- 作成後は **必ず** `uv run python src/a2_lint.py out/1b_parameters/parameters.yaml` を通すこと。

## レビュー観点（このファイルを人が確認する際）
- 軸/値の過不足、`kind`分類の妥当性、relations/interactionsの因果、DSL式の可読性、オラクルの網羅・矛盾。
