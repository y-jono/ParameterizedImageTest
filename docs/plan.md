<!--
これは設計時点で承認された「設計プラン」のスナップショットです（2026-06-24）。
- 意思決定の経緯と理由は docs/adr/ の ADR 群を参照。
- 実装後の確定仕様・実行手順は README.md を参照。
- 設計→実装で精緻化した差分（as-built）は各 ADR の「実装メモ」に記載。
  代表例: DSL値の YAML 罠回避（alpha=present/absent, icc=embedded/absent,
  platform_quicktime=installed/absent, compression="none"/"LZW"）、派生 compression_ratio の追加、
  本サンプルでは limits 未設定のため oracle の file_size ルールは不採用。
-->

# パラメタライズド画像テスト基盤（A・B・C）設計プラン

## Context（背景・目的）

画像レイアウトアプリの保守において、「アプリが受け入れる/拒否する画像メタデータ」を
網羅した入力画像でテストしたい。手作業だと組合せ爆発し、網羅性も担保できない。

そこで、仕様ドキュメントを起点に **3段パイプライン** を作る。各段は **人間がレビュー・編集できる中間成果物** を
出力し、その成果物が次段の入力になる（レビューゲート方式）。

```
仕様PDF ─[A1:読み取り]──→ 1a: raw_extract.md      ─(レビュー: 読めたか)→
        ─[A2:因果推論]──→ 1b: parameters.yaml     ─(レビュー: モデル化が正しいか)→
        ─[B]───────────→ 2次: decision_table.md/.csv ─(レビュー)→
        ─[C]───────────→ 3次: images/* + manifest.csv + verify_report.md ─(レビュー)
```
※ A を「読み取り(A1)」と「因果推論(A2)」に分離し、誤りの原因（誤読 vs 推論ミス）を切り分けやすくする。

サンプル仕様PDF（画像ファイル仕様ページ）から抽出できる軸:
ファイル形式 / カラーモード / ビット深度 / 圧縮 / αチャンネル / ICCプロファイル / プラットフォーム(QuickTime)。
各組合せには **期待結果（使用できる/できない）** が紐づく → これがディシジョンテーブルの「アクション（テストオラクル）」になる。

### 確定した方針（ユーザー選択）
- **A**: **2段に分離**して各々を独立にレビュー可能にする。
  - **A-1 読み取り**: Vision LLM 抽出・インタラクティブ運用で、ドキュメントを **忠実に転記**（推論禁止）→ `raw_extract.md`。
  - **A-2 因果推論**: 転記から **パラメータ・kind・relations・interactions・制約・オラクル** を導出 → `parameters.yaml`。
    式は **可読性最優先の専用DSL**（`when … then …` / `is / in / and / or / not`）で記述し、**Larkで決定的にパース**。
    LLMは式の起草のみ、解釈はパーサが担う。`a2_lint` が未パース・構造不正・oracle非網羅/矛盾を差し戻す。
  追加実装ゼロで開始でき、運用が固まったら各段とも API 自動化（②）へ昇格可能。B・Cはこの選択に依存しない。
- **B**: **因果を尊重した層別組合せ**。パラメータを 独立因子／派生／連動グループ に分類し、
  強相互作用ペアはフル網羅・残りはペアワイズ・連動数値はEP+BVAプロファイル・派生は計算。
  エンジンは PICT、**constraints は B が内部で PICT 制約文法へトランスパイル**、relations は sympy。
  **レビュー負荷を下げるため出力を関心ごとに分割**: 独立因子／組合せ強度ペア／constraints／派生の分割観点を
  それぞれ独立した自己文書化ファイルで出し、最後に統合の decision_table（ロスレス don't-care 圧縮、ペアワイズ併産）。
- **成果物の原則（横断）**: すべての出力は **自己文書化**（全プロパティに凡例コメント／レビュー観点を併記し、別途マニュアルを読まずに済む）。
- **C**: JPEG/TIFF を完全自動生成、**PSD は別扱い**（manifest に手動対象として記録）
- **スタック**: Python（lark, sympy, pydantic）+ ImageMagick + exiftool + PICT（PDFレンダリングは poppler/qlmanage）
- **形式化**: 専用DSL（可読性・低学習コスト重視、Larkで決定的解釈）。DMN/FEELやz3は採用せず、constraintsはPICTへ変換。

---

## リポジトリ構成

```
ParameterizedImageTest/
  specs/                         # 入力PDF（spec_sample.pdf 等）
  prompts/
    a1_read.md                   # A-1 読み取り（忠実転記・推論禁止）のプロンプト
    a2_infer.md                  # A-2 因果推論（パラメータ/kind/relations/interactions/制約/oracle）のプロンプト
  src/
    dsl/
      imgspec.lark               # 専用DSL文法（条件＋算術、when/then/is/in/and/or/not）
      parser.py                  # Lark→AST、安全評価（条件/算術）、PICT制約へのトランスパイル
    schema/
      parameters.schema.json     # parameters.yaml の構造スキーマ（JSON Schema）
      models.py                  # pydantic モデル（型付きロード）
    a_render.py                  # PDF→高解像度PNG（A-1 の前処理）
    a1_read.py                   # 【任意/②昇格】PNG→Vision LLM/OCR→raw_extract.md
    a2_infer.py                  # 【任意/②昇格】raw_extract.md→parameters.yaml
    a2_lint.py                   # parameters.yaml 検証（構造＋全式パース＋oracle網羅/矛盾）→ レビュー差し戻し
    b_table.py                   # parameters.yaml→因果層別組合せ(PICT)＋EP/BVA＋don't-care統合＋pairwise
    c_generate.py                # decision_table.csv→画像生成→exiftoolで検証
    image_spec.py                # パラメータ→ImageMagick/exiftool コマンド変換の共通定義
  out/
    1a_extract/raw_extract.md    # A-1 成果物（読み取り）
    1b_parameters/parameters.yaml # A-2 成果物（因果モデル）
    2_decision_table/            # B 出力（関心ごとに分割・各ファイル自己文書化）
      independent_factors.md     #   独立因子と値（レビュー: 軸/値の過不足）
      interaction_strength.md    #   組合せ強度ペア full/pairwise（レビュー: 強度割当）
      constraints.md             #   制約と根拠・除外例（レビュー: 制約の正しさ）
      derived_partitions.md      #   派生/連動の同値クラス・境界値＋観点（レビュー: 分割の妥当性）
      decision_table.md, decision_table.csv   # 統合表（don't-care圧縮・凡例付き）
      profiles.csv, pairwise.csv #   連動プロファイル実値／ペアワイズ併産案
    3_images/TC####_*.jpg|tif, manifest.csv, verify_report.md
  pyproject.toml                 # uv 管理（依存: PyYAML, lark, sympy, pydantic, jsonschema, allpairspy, anthropic, pandas）
  uv.lock                        # uv が生成するロックファイル
  README.md                      # 3段の実行手順とレビュー観点
```

---

## 仕組みA: ドキュメント → テストパラメータ（2段構成）— ①インタラクティブ運用

A は **読み取り(A-1)** と **因果推論(A-2)** に分離する。各段が独立した成果物とレビューゲートを持ち、
parameters.yaml に問題があっても「誤読(A-1)」か「推論ミス(A-2)」かを切り分けられる。

### A-1: 読み取り（忠実な転記）→ `raw_extract.md`
1. `uv run python src/a_render.py specs/<doc>.pdf` で PDF を高解像度PNG化（`pdftoppm -r 300`／macOS は `qlmanage -t -s 2000`）。
2. **Claude Code 内で** PNG と `prompts/a1_read.md`（**推論禁止・書いてある通りに転記**）を使い、
   ページ内容をそのまま `raw_extract.md` に書き出す（使用できる/できない一覧、重要・参考の注記）。
3. 人がレビュー（**観点: 誤読がないか／取りこぼしがないか**）。最初のレビューゲート。

`raw_extract.md`（例・忠実な転記のみ）:
```markdown
## 使用できる画像ファイル
- JPEG (RGBモード) 8bit
- TIFF (RGBモード) 8bit/16bit
- TIFF (LZW圧縮) 8bit/16bit
- PSD 8bit (Windows は QuickTime がインストールされている場合のみ)
## 使用できない画像ファイル
- JPEG (CMYKモード) / TIFF (αチャンネル付き) / TIFF (CMYKモード) / TIFF (グレースケール)
## 重要・参考
- （注記をそのまま転記）
```

### A-2: 因果推論（パラメータモデル化）→ `parameters.yaml`
1. **Claude Code 内で** `raw_extract.md` と `prompts/a2_infer.md` を使い、転記から
   **パラメータ・値・kind(独立/派生/連動)・relations・interactions・constraints・oracle** を導出。
2. 人がレビュー（**観点: 因果モデル化が正しいか**。下記スキーマ参照）。2番目のレビューゲート。

【将来の②昇格】各段とも `src/a1_read.py` / `src/a2_infer.py` で Anthropic API
（model `claude-opus-4-8`／コスト優先なら `claude-sonnet-4-6`）に同プロンプトを送り完全自動化。出力形式は同一。

**式の記法 = 専用DSL（可読性・低学習コスト重視、`src/dsl/imgspec.lark`）**
語彙はこれだけ: 比較 `is` / `is not` / `in` / `> < >= <=`、論理 `and` / `or` / `not`、算術 `+ - * / ( )`、
ルール `when <条件> then <条件or判定>`。例:
```
when format is JPEG then compression is none and bit_depth is 8   # 制約（含意）
when color_mode is CMYK then unusable                              # オラクル（判定）
when color_mode in [CMYK, Grayscale] then unusable                # 集合
file_size = width * height * channels * (bit_depth / 8) / compression_ratio   # 算術
```
セマンティクス（B が決定的に評価）: constraints=全条件を満たす組合せのみ採用／oracle=上から **first-match**、
最後に `otherwise` で網羅保証／formula=安全評価／relations=sympyで任意変数を解く。

**A-2 出力スキーマ（`parameters.yaml` = 1b）** — パラメータの **因果（kind/relations/interactions）・制約・オラクル** まで捕捉。
各パラメータは `kind: independent|derived|coupled` で分類:
```yaml
# 凡例（このファイルだけで意味が分かるように）:
#   kind: independent=自由に選べる軸 / derived=他から計算で決まる(軸にしない) / coupled=連動グループの一員
#   values=取りうる値 / lookup=写像(構造化) / expr=算術式(DSL) / partitions=同値/境界の代表値
#   relations=連動の拘束式(sympyで解く) / interactions=全網羅したい強相互作用ペア
#   constraints=不可能組合せの除去(when 条件 then 条件) / oracle=期待結果(when 条件 then usable|unusable, first-match)
source: "spec_sample.pdf 画像ファイル仕様ページ"
parameters:
  # --- 独立因子（組合せ対象）---
  - {name: format,      kind: independent, values: [JPEG, TIFF, PSD]}
  - {name: color_mode,  kind: independent, values: [RGB, CMYK, Grayscale]}
  - {name: bit_depth,   kind: independent, values: [8, 16]}
  - {name: compression, kind: independent, values: [none, LZW]}
  - {name: alpha,       kind: independent, values: [false, true]}
  - {name: icc_profile, kind: independent, values: [none, embedded]}
  - {name: platform_quicktime, kind: independent, values: [yes, no]}  # PSD可否のみ影響
  # --- 派生（他から計算で決定。軸にしない）---
  - name: channels        # 写像は式にせず構造化マップ（曖昧さ排除）
    kind: derived
    lookup: {from: color_mode, map: {Grayscale: 1, RGB: 3, CMYK: 4}}
    plus_if: {when: "alpha is true", add: 1}
  - {name: file_size, kind: derived, expr: "width * height * channels * (bit_depth / 8) / compression_ratio"}
  # --- 連動グループ geometry（physical=pixels/dpi で拘束。EP+BVAでプロファイル化）---
  - {name: width,       kind: coupled, group: geometry, partitions: [1, 4000, 30000]}
  - {name: height,      kind: coupled, group: geometry, partitions: [1, 3000, 30000]}
  - {name: resolution,  kind: coupled, group: geometry, partitions: [72, 350, 720]}   # dpi
relations:          # 連動の拘束式（sympyで任意変数を解ける等式）
  - "physical_w_inch = width / resolution"
  - "physical_h_inch = height / resolution"
interactions:       # 強相互作用ペア（フル網羅）。識別子リスト＝そのままPICTサブモデル
  - [channels, bit_depth]      # 例: 16bit×4ch の成否
  - [format, compression]
  - [color_mode, icc_profile]
constraints:        # DSL: when <cond> then <cond>（B が PICT 制約へトランスパイル）
  - "when format is JPEG then compression is none and bit_depth is 8"
  - "when format is PSD  then bit_depth is 8"
  - "when alpha is true  then format is TIFF"
  - "when icc_profile is embedded then color_mode is RGB"
  - "when compression is LZW then format is TIFF"
oracle:             # DSL: when <cond> then usable|unusable（first-match）
  hit_policy: first
  rules:
    - "when color_mode in [CMYK, Grayscale] then unusable"
    - "when format is TIFF and alpha is true then unusable"
    - "when file_size > max_file_size then unusable"
    - "when format is JPEG and color_mode is RGB and bit_depth is 8 then usable"
    - "when format is TIFF and color_mode is RGB then usable"
    - "when format is PSD and bit_depth is 8 and platform_quicktime is yes then usable"
  otherwise: unusable    # 網羅保証（デフォルト判定）
limits:             # 数値系オラクルの根拠（あれば数値、無ければ null）
  max_dimension: null
  max_file_size: null
notes:
  - "モノクロ印刷は将来の軸候補"
```

**A-2 レビュー観点**: 軸の過不足、`kind`分類の妥当性、relations/interactionsの因果、DSL式の可読性、
オラクルの網羅・矛盾（`a2_lint` が機械検査）。レビュアーは DSL（自然な中置記法）だけ読めばよい。

---

## 仕組みB: パラメータ → ディシジョンテーブル（2次出力）— 因果を尊重した層別組合せ

**設計の要点**: 画像メタデータは独立でなく強い因果がある。全因子を独立扱いする素のペアワイズは
(1) あり得ない組合せを生み、(2) 派生値を無駄に増やし、(3) 強相互作用ペアを取りこぼす。
そこで `kind` 分類ごとに最適な手法を当てる。**かつ、複雑さをそのまま一枚の表で見せず、関心ごとに分割した
自己文書化ファイルを段階的にレビューさせ**、最後に統合表を見る（レビュー負荷を分散）。

**処理**（`b_table.py`、組合せエンジンに **PICT**）
1. **分類**（A の `kind`）: 独立因子 / 派生(channels, file_size) / 連動グループ(geometry: width,height,resolution)。
2. **連動数値グループは EP+BVA で代表プロファイル化**（各次元 min/標準/max・解像度・file_size上限の直前/丁度/超過）。
3. **組合せは因果の強さで強度を変える**: `interactions` の強相互作用ペアは **フル網羅**、残りは **ペアワイズ**、
   `constraints` で不可能組合せを除去（PICT の sub-model/constraints/weight で表現）。
4. **派生値は計算**してオラクル/閾値判定に使用。
5. **提示用にロスレス don't-care 統合**（効かない条件を `—`、Quine–McCluskey 的 greedy merge）。ペアワイズ版も併産。

### B 出力（関心ごとに分割・各ファイル冒頭に凡例＝マニュアル不要）

**① `independent_factors.md`** — 独立因子のみ（レビュー: 軸/値の過不足）
```markdown
# 独立因子（自由に選べる軸）。凡例: factor=軸名 / values=取りうる値 / source=根拠 / note=補足
| factor      | values            | source        | note                       |
|-------------|-------------------|---------------|----------------------------|
| format      | JPEG, TIFF, PSD   | 使用可一覧    | 出力拡張子を決める         |
| color_mode  | RGB, CMYK, Gray   | 使用可/不可一覧 | CMYK/Grayは不可判定の主因 |
```

**② `interaction_strength.md`** — 組合せ強度の割当（レビュー: どこを全網羅し、どこをペアワイズにするか）
```markdown
# 凡例: members=対象ペア / strength=full(全網羅)|pairwise / reason=その強度にした因果上の理由
## 強相互作用（full=全網羅。取りこぼすと危険）
| members              | strength | reason                              |
|----------------------|----------|-------------------------------------|
| channels × bit_depth | full     | 16bit×4ch など形式対応が破綻する境目 |
| format × compression | full     | LZWはTIFFのみ等、形式依存が強い      |
| color_mode × icc     | full     | ICCはRGBのみ等                       |
## 弱相互作用（pairwise=2因子網羅で十分）
| members              | strength | reason                              |
| 上記以外の独立因子   | pairwise | 相互作用が弱く2因子網羅で十分        |
```

**③ `constraints.md`** — 制約（レビュー: 制約の正しさ）
```markdown
# 凡例: dsl=制約式(専用DSL) / reason=根拠 / prunes=この制約が落とす組合せ例
| dsl                                  | reason          | prunes(例)         |
|--------------------------------------|-----------------|--------------------|
| when format is JPEG then bit_depth is 8 | JPEGは8bitのみ | JPEG×16bit を除去   |
| when alpha is true then format is TIFF  | αはTIFFのみ    | JPEG/PSD×alpha 除去 |
```

**④ `derived_partitions.md`** — 派生/連動の同値クラス・境界値と**観点**（レビュー: 分割が妥当か）
```markdown
# 凡例: variable=対象 / class=同値クラス / representative=代表値 / kind=normal(同値)|boundary(境界) / rationale=観点
## width（連動グループ geometry）
| class      | representative | kind     | rationale                   |
|------------|----------------|----------|-----------------------------|
| 最小       | 1px            | boundary | 下限境界（0/1の振る舞い差）  |
| 標準       | 4000px         | normal   | 一般的な写真サイズの代表     |
| 上限直前   | max-1          | boundary | 受理上限の直前               |
| 上限超過   | max+1          | boundary | 超過＝unusable 期待          |
## file_size（派生）— 上限直前/丁度/超過 を境界として試験（観点: サイズ上限の判定境目）
```

**⑤ `decision_table.md` + `.csv`** — 統合表（冒頭に凡例。`—`=don't-care、geometry=代表プロファイル）
```markdown
# 凡例: 各条件列=その値に固定 / "—"=don't-care(結果に影響しない=どの値でも可)
#       geometry=連動グループの代表プロファイル(P1..Pk, 実値は profiles.csv)
#       action=期待結果(usable=受理/unusable=拒否, oracleをfirst-matchで評価)
#       metrics: full=全組合せ valid=制約後 compressed=本表行数 pairwise=別案件数
| rule | format | color_mode | bit_depth | channels | geometry | action   |
|------|--------|------------|-----------|----------|----------|----------|
| R1   | JPEG   | RGB        | 8         | 3        | —        | usable   |
| R2   | TIFF   | RGB        | —         | —        | —        | usable   |
| R3   | —      | CMYK       | —         | —        | —        | unusable |
| R4   | TIFF   | RGB        | 16        | 4        | Pmax     | usable   |
```
`profiles.csv`（連動プロファイル実値）・`pairwise.csv`（ペアワイズ併産案）も同様に凡例ヘッダ付き。

**レビュー観点（段階的・各ファイルで完結）**: ①軸/値 → ②強度割当 → ③制約 → ④分割観点 → ⑤統合表の順に
小さく確認。各ファイル冒頭の凡例だけで意味が分かる（マニュアル不要）。

---

## 仕組みC: ディシジョンテーブル → 入力画像（3次出力）

**処理**（`c_generate.py` + `image_spec.py`）
1. `decision_table.csv` の各ルールを **具体値にインスタンス化**（`—` は制約を満たす代表値を選択、選択内容を記録）。
   `geometry` 列は `profiles.csv` から width/height/resolution の具体値に展開（派生 channels/file_size も確定）。
   ルール1件 → 代表テスト画像1枚（最小スイート）。必要に応じ `—` を代表値展開も可。
2. ImageMagick で **識別可能なテストパターン**（カラーバー＋ケースID/パラメータを焼き込み）を生成し、
   パラメータをファイル属性に反映:
   - `color_mode`: `-colorspace sRGB|CMYK|Gray`
   - `bit_depth`: `-depth 8|16`
   - `compression`(TIFF): `-compress None|LZW`
   - `alpha`(TIFF): `-alpha on`（αチャンネル付与）
   - `icc_profile`: `-profile <sRGB|CMYK>.icc` で埋め込み / `+profile icc` で除去
   - `format`: 出力拡張子（.jpg/.tif）
3. **検証ステップ（重要）— なぜ必要か**: ImageMagick は指定どおりに作れないことがある
   （例: TIFF+LZW で 16bit を要求しても 8bit に落ちる／`-alpha on` でも α が付かない／ICC が埋め込まれない）。
   **「作らせた指定」と「実ファイルが実際に持つ値」がズレた画像は、テスト入力として無効**なので、必ず読み戻して突合する。
   - **intended（意図パラメータ）** = ルールが要求した値＝生成時に ImageMagick へ渡した指定。
   - **actual（検証済みパラメータ）** = 生成後のファイルから `exiftool` / `magick identify` で読み出した実測値。
   - **判定** = intended と actual をフィールド単位で比較。1つでも不一致なら `verify_report.md` に記録し、そのケースは失敗（要修正/手動）。

   | パラメータ | intended（生成時の指定） | actual の読み取り元（exiftool/identify） | 一致条件 |
   |---|---|---|---|
   | format | 出力拡張子 `.tif/.jpg` | `FileType` | 一致 |
   | color_mode | `-colorspace RGB/CMYK/Gray` | `ColorSpace` / `PhotometricInterpretation` / `ColorComponents` | 一致 |
   | bit_depth | `-depth 8/16` | `BitsPerSample`（例 `16 16 16`） | 一致 |
   | compression | `-compress None/LZW` | `Compression` | 一致 |
   | alpha | `-alpha on/off` | `ExtraSamples` / `SamplesPerPixel`(=4) | 有無一致 |
   | icc_profile | `-profile *.icc` / `+profile icc` | `ICC_Profile` / `ProfileDescription` の有無 | 有無一致 |

4. **PSD は別扱い**: 自動生成対象外。manifest に `generation: manual` と作成手順を記録。
5. ファイル命名: `TC0007_TIFF_RGB_16bit_LZW_alpha_iccNone.tif`。

**3次出力**（各ファイル冒頭に凡例＝マニュアル不要）
- `out/3_images/TC####_*.jpg|tif`（実画像）
- `manifest.csv`: `case_id, file, intended_*(意図=要求値), actual_*(実測=読み戻し値), match(true/false), expected(usable/unusable=オラクル判定), source_rule(由来ルールID)`
- `verify_report.md`: 各ファイルの intended↔actual の一致/不一致サマリ（不一致は原因とともに赤表示）

manifest は将来のアプリ実行テスト（画像を投入し受理/拒否をオラクルと突合）にそのまま使える契約とする。

**レビュー観点**: 画像が意図どおりか、検証レポートで不一致が無いか、PSD等の手動対象の妥当性。

---

## 前提ツールのセットアップ
```
brew install uv poppler ghostscript imagemagick exiftool pict   # PICT = 組合せエンジン
uv init                                                          # 既存なら不要
uv add PyYAML lark sympy pydantic jsonschema allpairspy anthropic pandas
# uv run でコマンド実行（仮想環境は uv が自動管理。venv/pip/requirements.txt は使わない）
# export ANTHROPIC_API_KEY=...   # ②API自動化に昇格する場合のみ必要（①では不要）
```

## 検証（エンドツーエンド）
1a. **A-1**: `uv run python src/a_render.py specs/spec_sample.pdf` でPNG化 → Claude Code内で転記 →
   `out/1a_extract/raw_extract.md` を目視レビュー（**誤読・取りこぼしが無いか**）。
1b. **A-2**: `raw_extract.md` から推論 → `parameters.yaml` 生成 → `uv run python src/a2_lint.py out/1b_parameters/parameters.yaml`
   で **全DSL式がパースでき・構造が正しく・oracleが網羅/無矛盾** であることを機械検査（失敗は赤表示で差し戻し）。
   通過後、`out/1b_parameters/parameters.yaml` を目視レビュー（DSL式の可読性・因果の妥当性）。
   サンプルでは 7軸＋channels/file_size(派生)＋geometry(連動)＋可否オラクルが出ることを確認。
2. **B**: `uv run python src/b_table.py` → `out/2_decision_table/` の分割ファイルを**段階的に**レビュー（各冒頭の凡例だけで読める）:
   ① `independent_factors.md`（軸/値）→ ② `interaction_strength.md`（full/pairwise の割当）→
   ③ `constraints.md`（制約と除外例）→ ④ `derived_partitions.md`（同値/境界と観点）→ ⑤ `decision_table.md`（統合・`—`畳み込み）。
   強相互作用ペア(channels×bit_depth 等)が全網羅、連動が境界値プロファイル、派生(file_size)が計算で扱われ、
   代表ルール（JPEG-RGB-8=usable, *-CMYK=unusable）が出ることを確認。
3. **C**: `uv run python src/c_generate.py` → `out/3_images/` に画像生成、`verify_report.md` で意図↔実測が全件一致、
   `exiftool out/3_images/TC0001_*.tif` で BitsPerSample/Compression/ICC 等が意図どおりか手元確認。
4. 1枚を実アプリに読み込ませ、manifest の expected と挙動（受理/拒否）が一致するかスポット確認。

## 段階導入（最初の一歩）
- まず A-1 `raw_extract.md` → A-2 `parameters.yaml` を本サンプルで確定（2段それぞれレビュー）
  → B の最小ディシジョンテーブルをレビュー
  → C は usable/unusable 境界の代表数件だけ生成して検証ループを回し、その後フル網羅に広げる。
