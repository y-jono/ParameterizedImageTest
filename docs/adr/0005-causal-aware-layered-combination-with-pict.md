# ADR-0005: 因果を尊重した層別組合せ（エンジンは PICT）

- Status: Accepted
- Date: 2026-06-24

## Context
画像メタデータは独立な軸ではなく強い因果（従属・連動）を持つ。例: チャンネル数はカラーモードと
αから決まる、ファイルサイズは幅×高さ×チャンネル×ビット深度から決まる、幅・高さ・解像度・物理寸法は
方程式で連動。全因子を独立扱いする素のペアワイズは (1) あり得ない組合せを作り、(2) 派生値を無駄に
増やし、(3) 強相互作用ペアを取りこぼす。

## Decision
パラメータを **3種に分類**して手法を当てる（`kind`）:
- **独立因子**: 組合せ対象。
- **派生 (derived)**: 他から計算で決定（`channels`=lookup+α, `file_size`=expr 等）。**軸にせず計算**。
- **連動 (coupled)**: 方程式で拘束（geometry: width/height/resolution）。**EP+BVA で代表プロファイル化**し1軸として投入。

組合せは **因果の強さで強度を変える**:
- `interactions` の強相互作用ペアは **フル網羅**、残りの独立因子は **pairwise**、`constraints` で不可能組合せ除去。
- これを **Microsoft PICT** の sub-model / constraints で表現（エンジンに採用）。派生メンバは決定要因へ写像
  （例 `channels`→`{color_mode, alpha}`）。

## Alternatives considered
- 素のペアワイズのみ: 因果を無視し上記3問題が発生。却下。
- 全直積: 網羅は完全だが爆発し非現実的（本サンプルでも 288→有効78）。Bでは圧縮表現で対応（ADR-0006）。
- 自前の貪欲covering実装: PICTで足りるため不要。

## Consequences
- 強相互作用（channels×bit_depth 等）の取りこぼしを防ぎつつ、規模を抑えられる。
- PICT 外部依存（`brew install pict`）が増える。
- 派生/連動の扱いを B が一貫処理（`src/derive.py` 共有エンジン）。

## 実装メモ（as-built）
- relations は当初 sympy による代数的解法を想定したが、実際の用途は派生値の一方向計算だけだったため、
  **DSL の「左辺 = 右辺」を一方向に評価する代入**として実装（`src/derive.py` compute_derived pass2）。
  逆算（任意の変数について解く）は行わず、未使用の sympy 依存は削除した。必要になれば再検討する。
