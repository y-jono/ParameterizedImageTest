# 新人プログラマ向けハンドブック

画像フォーマットもテスト技法もアルゴリズムも「これから学ぶ」人向けに、
このツールが**何をするか**と**自分の手で動かす方法**を、できるだけやさしく説明します。
（コーディングエージェントは不要です。ターミナルだけで動きます。）

---

## 0. ひとことで言うと

> 「この画像レイアウトアプリは、どんな画像なら読み込めて、どんな画像だと弾くか」を仕様書から読み取り、
> **その境目をくまなく突くテスト用画像を、もれなく・少なく・自動で**作る道具です。

手で全部の組合せを作ろうとすると数が爆発します。そこを機械的に圧縮し、
**人がレビューできるサイズの表**にしてから、画像を作ります。

---

## 1. 全体像（3ステップ）

```
 仕様書(PDF)
    │
    ▼  A: 読み取って「テストの条件と正解」を書き出す
 parameters.yaml   ← 人がレビュー＆編集できるテキスト
    │
    ▼  B: 条件を組み合わせて「表」にする（ムダを削って小さく）
 decision_table など（表）   ← 人がレビュー
    │
    ▼  C: 表のとおりに「テスト画像」を作り、ちゃんと作れたか検証
 画像ファイル + 検証レポート
```

- **A** は「考える」工程なので、新人はまず **手で** `parameters.yaml` を書きます（サンプル同梱）。
  エージェント（Claude Code）が使えるなら、スキルで自動化もできます（手順4-A の「楽な道」）。
- **B / C** は **計算だけ**なので、スクリプト一発で動きます（LLMもエージェントも不要）。

---

## 2. まず動かす（5分）

```bash
bash scripts/setup.sh     # 初回だけ（brew と uv で必要なものを入れる）
make all                  # lint → B → C → C(広域) を一括実行
```

終わったら、まず次の2つを開いてください:
- `out/2_decision_table/decision_table.md` … テストの最終表（条件→正解）
- `out/3_images/verify_report.md` … 作った画像が意図どおりかの検証結果

`make help` で使えるコマンド一覧が出ます。

---

## 3. 用語をやさしく

### 画像まわり（アプリが受け付ける/弾く条件になる）
| 用語 | やさしい説明 | 例 |
|---|---|---|
| フォーマット | 画像ファイルの種類 | JPEG / TIFF / PSD |
| カラーモード | 色の表し方 | RGB（画面向き）/ CMYK（印刷向き）/ グレースケール（白黒） |
| ビット深度 | 1色あたりの細かさ | 8bit / 16bit（大きいほど高精細・重い） |
| 圧縮 | ファイルを小さくする方式 | none（圧縮なし）/ LZW（TIFFの可逆圧縮） |
| αチャンネル | 透明度の情報 | あり(present)/なし(absent) |
| ICCプロファイル | 色を正しく見せる「色の定規」 | 埋め込み(embedded)/なし(absent) |

### テスト技法（このツールの心臓部）
| 用語 | やさしい説明 |
|---|---|
| テストパラメータ（軸）と値 | テストで変える項目と、その選択肢。例: 軸=フォーマット、値=JPEG/TIFF/PSD |
| 期待結果（オラクル） | 「この入力なら正解はこう」という判定。ここでは `usable`(読める) / `unusable`(弾く) |
| ディシジョンテーブル | 「条件の組合せ → 動作（正解）」を並べた表 |
| 直積 / 組合せ爆発 | 全軸の全値を掛け合わせた総数。すぐ膨大になる（本サンプルは 288 通り） |
| 制約(constraints) | 物理的にあり得ない組合せ。例: JPEGに16bitは無い → 最初から除外 |
| ペアワイズ | 「どの2項目の組合せも1回は試す」最小セット。全部試すより激減する |
| 等価分割・境界値 | 似た値はまとめ（等価分割）、変化が起きる“境目”を狙う（境界値）。例: 幅 1 / 標準 / 最大 |
| don't-care（`—`） | 「その項目はどの値でも結果が同じ」を `—` でまとめる。**全ケースを表したまま行数を減らす（ロスレス圧縮）** |

### 実装まわり
| 用語 | やさしい説明 |
|---|---|
| DSL | このツール専用の小さな書き方。`when 条件 then 結果` のような英語風（手順4-A 参照） |
| パーサ | 文法どおりに機械が式を読む部品。人の解釈ブレを排除する |
| 派生(derived) | 他から**計算で決まる**値。例: チャンネル数＝カラーモードから決まる |
| 連動(coupled) | 式で互いに縛られる値の組。例: 幅・高さ・解像度（物理サイズ = 画素 ÷ 解像度） |
| PICT | 組合せ（ペアワイズ等）を作ってくれる外部ツール |

---

## 4. 手で動かす（ステップ詳細）

### 手順4-A: テストの条件を用意する（A）

成果物は `out/1b_parameters/parameters.yaml`。**サンプルは既に入っています**。
新しい仕様で使うときだけ、このファイルを作り直します。

**書き方（最小例）** — テキストエディタで編集します。
```yaml
parameters:
  - {name: format, kind: independent, values: [JPEG, TIFF, PSD]}   # 自由に選べる軸
  - {name: color_mode, kind: independent, values: [RGB, CMYK, Grayscale]}
constraints:                                # あり得ない組合せ（DSLで書く）
  - "when format is JPEG then bit_depth is 8"
oracle:                                     # 正解（上から最初に当たったものを採用）
  rules:
    - "when color_mode is CMYK then unusable"
    - "when format is JPEG and color_mode is RGB then usable"
  otherwise: unusable                       # どれにも当たらなければ
```
`kind` は3種類: `independent`(自由な軸) / `derived`(計算で決まる) / `coupled`(連動グループ)。
詳しい凡例は同梱の `out/1b_parameters/parameters.yaml` の冒頭コメントが一番わかりやすいです。

**書いたら必ず機械チェック**:
```bash
make lint
```
- 緑の `PASS` なら次へ。
- 赤の `ERROR` は要修正（綴り間違い・文法エラー・正解の抜け漏れ等を指摘してくれます）。
- 黄の `WARN` は「念のため確認して」（例: 例外を先に置いたルールの重複）。止まりはしません。

> 楽な道（エージェントがある場合）: Claude Code で **スキル `parameterized-image-test`** を使うと、
> 仕様ページの画像を読んで A-1（転記）→A-2（parameters.yaml）まで下書きしてくれます。
> その後は同じく `make lint` で確認します。

### 手順4-B: 表を作る（B）
```bash
make build
```
`out/2_decision_table/` に5つのファイルが出ます。**①→⑤の順**に軽く見るのがコツ（一度に全部見ない）:
1. `independent_factors.md` … 軸と値の一覧（過不足ない？）
2. `interaction_strength.md` … どの組合せを「全部」試し、どこを「ペアワイズ」にするか
3. `constraints.md` … 除外される組合せ（除いてよい？）
4. `derived_partitions.md` … 計算で決まる値と、境界値の選び方
5. `decision_table.md` … 圧縮済みの最終表（`—`＝don't-care、`action`＝正解）

### 手順4-C: 画像を作って検証する（C）
```bash
make images           # 最小スイート → out/3_images/
make images-pairwise  # 広域スイート → out/3_images_pairwise/（16bit/LZW なども網羅）
```
- ImageMagick で画像を作り、`exiftool`/`identify` で**作った画像を読み戻して**、
  指定どおりのメタデータになっているか1つずつ照合します（ツールが勝手に変換することがあるため）。
- **PSD は自動生成しません**（手動対象）。レポートに作成手順が出ます。

---

## 5. 出力の読み方（チートシート）

| ファイル | 何が書いてある | OKの形 | 注意 |
|---|---|---|---|
| `out/3_images/verify_report.md` | 各画像の「意図(intended) ↔ 実測(actual)」 | 全部 ✓、`match=true` | `consistent` 列＝由来ルールの正解と再評価が一致 |
| `out/3_images/manifest.csv` | 1画像=1行の台帳 | `match=true`, `rule_consistent=true` | `platform_quicktime` は環境条件で画像に出ないため非検証 |
| `decision_table.md` | 圧縮済みの最終表 | `—` が多く行数が少ない | 末尾の「前提・仮定」も確認（正解はそれに依存） |
| `constraints.md` | 除外される組合せ | `valid` の数が妥当 | `prunes` は**単体カウント。足し算しない**（正味は別記） |

**intended と actual**: intended＝「こう作って」と指定した値。actual＝「実際にできた」値。
この2つがズレた画像はテストとして無効なので、必ず突合します。

---

## 6. よくあるエラーと対処

| 症状 | 原因 | 対処 |
|---|---|---|
| `command not found: pict / magick / exiftool` | 外部ツール未導入 | `bash scripts/setup.sh` |
| `make lint` が赤 ERROR | parameters.yaml の文法・構造・正解の問題 | メッセージの行を修正して再実行 |
| `verify_report` に ✗ や mismatch | ImageMagick が指定どおり作れなかった | 該当の `intended → actual` を見て生成オプションを調整 |
| `make: *** missing separator` | Makefile をタブでなく空白で編集した | 行頭をタブに戻す |
| YAMLで `none/yes/no/true` が変な値になる | YAMLが勝手に型変換 | クォートする（`"none"`）か別語（`present/absent`）を使う |

---

## 7. 自分の別の仕様で試すには

1. 仕様PDFを `specs/` に置き、`make render SPEC=specs/あなたの.pdf` で画像化（A-1 の下準備）。
2. その内容を見て `out/1b_parameters/parameters.yaml` を書き換える（手順4-A）。
3. `make all`。**B と C は一切変えなくてよい**（A の出力さえ正しければ後段は共通）。

---

## 8. もっと知るには
- まとめ: [README.md](../README.md)
- 設計の理由(ADR): [docs/adr/](adr/README.md)
- 設計プラン全文: [docs/plan.md](plan.md)
- コードの場所: `src/`（`dsl/`＝DSL、`schema/`＝検証、`derive.py`＝共通計算、`a2_lint.py`/`b_table.py`/`c_generate.py`＝各段）
