#!/usr/bin/env python3
"""B: parameters.yaml → ディシジョンテーブル（因果を尊重した層別組合せ）。

レビュー負荷を下げるため、出力を関心ごとに分割し各ファイルを自己文書化する:
  ① independent_factors.md   独立因子と値
  ② interaction_strength.md  組合せ強度ペア（full / pairwise）
  ③ constraints.md           制約と除外例
  ④ derived_partitions.md    派生/連動の同値・境界＋観点
  ⑤ decision_table.md/.csv   全有効空間を don't-care 圧縮した最小ルール（C の入力）
  ＋ profiles.csv            連動グループ(geometry)の代表プロファイル実値
  ＋ pairwise.csv            PICT による covering set（pairwise＋強相互作用フル）

使い方:
    uv run python src/b_table.py [parameters.yaml] [--outdir out/2_decision_table]
"""
from __future__ import annotations

import argparse
import csv
import itertools
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dsl import referenced_names, to_pict  # noqa: E402
from derive import (  # noqa: E402
    compile_constraints,
    compile_oracle,
    compute_derived,
    constraints_satisfied,
    oracle_verdict,
)
from schema.models import ParametersModel, load_parameters  # noqa: E402

DC = "*"  # don't-care マーカー（CSV）。MD では — で表示。


# --------------------------------------------------------------------------- #
# geometry プロファイル（EP+BVA）
# --------------------------------------------------------------------------- #
def build_profiles(model: ParametersModel) -> List[Dict]:
    """連動グループ geometry を min/標準/max の代表プロファイルに畳む。"""
    coupled = model.coupled()
    if not coupled:
        return []
    levels = ["min", "typ", "max"]
    profiles = []
    for i, level in enumerate(levels):
        prof = {"profile": f"P_{level}", "level": level}
        for p in coupled:
            parts = p.partitions
            idx = {"min": 0, "typ": len(parts) // 2, "max": len(parts) - 1}[level]
            prof[p.name] = parts[idx]
        profiles.append(prof)
    return profiles


# --------------------------------------------------------------------------- #
# オラクル判定（verdict は独立因子＋派生で決まる前提を検証）
# --------------------------------------------------------------------------- #
def _assert_verdict_independent_of_geometry(model, oracle_rules):
    geo_names = {p.name for p in model.coupled()} | {
        p.name for p in model.derived() if p.expr and "width" in (p.expr or "")
    }
    used = set()
    for vr in oracle_rules:
        used |= referenced_names(vr.condition)
    overlap = used & geo_names
    if overlap:
        raise SystemExit(
            f"ERROR: オラクルが geometry 依存の変数 {sorted(overlap)} を参照しています。"
            "decision_table の条件列に geometry を含める拡張が必要です。"
        )


def verdict_of(model, oracle_rules, env: Dict) -> str:
    env2 = compute_derived(model, env)
    return oracle_verdict(oracle_rules, model.oracle.otherwise, env2)


# --------------------------------------------------------------------------- #
# don't-care 圧縮（QM 風 greedy）
# --------------------------------------------------------------------------- #
def _matches(cube: Tuple, combo: Tuple) -> bool:
    return all(c == DC or c == v for c, v in zip(cube, combo))


def _expansions(cube: Tuple, domains: List[List]) -> List[Tuple]:
    choices = [[c] if c != DC else dom for c, dom in zip(cube, domains)]
    return [tuple(t) for t in itertools.product(*choices)]


def compress(valid_combos: List[Tuple], verdicts: Dict[Tuple, str],
             domains: List[List], order: List[int]) -> List[Tuple]:
    """各 verdict グループを don't-care キューブに最小化（ロスレス・有効空間内）。"""
    rules: List[Tuple] = []
    for target in sorted(set(verdicts.values())):
        group = {c for c in valid_combos if verdicts[c] == target}
        allowed = group  # 同 verdict の有効組合せのみを覆える
        # 各 combo を貪欲に一般化して prime cube 候補を作る
        primes = set()
        for combo in group:
            cube = list(combo)
            for f in order:
                trial = list(cube)
                trial[f] = DC
                if all(e in allowed for e in _expansions(tuple(trial), domains)):
                    cube = trial
            primes.add(tuple(cube))
        # set cover（最大被覆を貪欲選択）
        uncovered = set(group)
        chosen: List[Tuple] = []
        primes_list = sorted(primes, key=lambda c: -sum(1 for x in c if x == DC))
        while uncovered:
            best, best_cov = None, set()
            for cube in primes_list:
                cov = {e for e in _expansions(cube, domains) if e in uncovered}
                if len(cov) > len(best_cov):
                    best, best_cov = cube, cov
            if not best:
                break
            chosen.append((best, target))
            uncovered -= best_cov
        rules.extend(chosen)
    return rules


# --------------------------------------------------------------------------- #
# PICT covering set
# --------------------------------------------------------------------------- #
def _member_to_factors(name: str, model: ParametersModel) -> List[str]:
    """interaction メンバを PICT の因子名に写像（派生→決定要因、連動→group名）。"""
    by = model.by_name()
    p = by.get(name)
    if p is None:
        return [name]
    if p.kind == "independent":
        return [name]
    if p.kind == "coupled":
        return [p.group]
    # derived: lookup の from / plus_if 条件の参照を決定要因とする
    factors: List[str] = []
    if p.lookup:
        factors.append(p.lookup.from_)
        if p.plus_if:
            for n in referenced_names_cond(p.plus_if.when):
                if n in by and by[n].kind == "independent":
                    factors.append(n)
    return factors or [name]


def referenced_names_cond(text: str):
    from dsl import parse_condition
    return referenced_names(parse_condition(text))


def run_pict(model: ParametersModel, profiles: List[Dict], model_path: Path) -> Tuple[List[str], List[Dict]]:
    params = model.all_names()
    lines: List[str] = []
    # 因子（独立 + geometry）
    for p in model.independent():
        lines.append(f"{p.name}: " + ", ".join(str(v) for v in p.values))
    if profiles:
        lines.append("geometry: " + ", ".join(pr["profile"] for pr in profiles))
    lines.append("")
    # サブモデル（強相互作用 = フル網羅）。PICT では制約より前に置く。
    for pair in model.interactions:
        facs: List[str] = []
        for m in pair:
            for f in _member_to_factors(m, model):
                if f not in facs:
                    facs.append(f)
        if len(facs) >= 2:
            lines.append("{ " + ", ".join(facs) + " } @ " + str(len(facs)))
    lines.append("")
    # 制約
    for c in compile_constraints(model):
        lines.append(to_pict(c, params))
    model_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = subprocess.run(["pict", str(model_path)], check=True, capture_output=True, text=True).stdout
    rows = [r for r in out.splitlines() if r.strip()]
    header = rows[0].split("\t")
    data = [dict(zip(header, r.split("\t"))) for r in rows[1:]]
    return header, data


def _cast(model: ParametersModel):
    """PICT が返す文字列を、元の型（int など）にキャストする関数を作る。"""
    types = {}
    for p in model.independent():
        types[p.name] = int if all(isinstance(v, int) for v in p.values) else str
    def cast(name, value):
        t = types.get(name, str)
        try:
            return t(value)
        except (ValueError, TypeError):
            return value
    return cast


# --------------------------------------------------------------------------- #
# 出力書き出し
# --------------------------------------------------------------------------- #
def w(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    print(f"  wrote {path}")


def md_table(headers: List[str], rows: List[List[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def write_independent_factors(model, outdir):
    rows = [[p.name, ", ".join(str(v) for v in p.values), len(p.values)] for p in model.independent()]
    body = (
        "# ① 独立因子（自由に選べる軸）\n"
        "# 凡例: factor=軸名 / values=取りうる値 / n=値の数。レビュー: 軸・値の過不足。\n\n"
        + md_table(["factor", "values", "n"], rows) + "\n"
    )
    w(outdir / "independent_factors.md", body)


def write_interaction_strength(model, outdir):
    strong_rows = []
    for pair in model.interactions:
        facs = []
        for m in pair:
            for f in _member_to_factors(m, model):
                if f not in facs:
                    facs.append(f)
        strong_rows.append([" × ".join(pair), "full", "{ " + ", ".join(facs) + " } @ " + str(len(facs))])
    body = (
        "# ② 組合せ強度の割当\n"
        "# 凡例: members=対象ペア / strength=full(全網羅)|pairwise / pict_submodel=PICTでの表現。\n"
        "# 方針: 強相互作用ペアは full（取りこぼし防止）、それ以外の独立因子ペアは pairwise。\n\n"
        "## 強相互作用（full = 全網羅）\n"
        + md_table(["members", "strength", "pict_submodel"], strong_rows) + "\n\n"
        "## 弱相互作用\n"
        "上記 interactions に含まれない独立因子の全ペア → **pairwise**（PICT 既定の2因子網羅）。\n"
    )
    w(outdir / "interaction_strength.md", body)


def write_constraints(model, outdir):
    constraints = compile_constraints(model)
    # 各制約が独立空間から落とす組合せ数と例
    indep = model.independent()
    names = [p.name for p in indep]
    domains = [p.values for p in indep]
    all_combos = [dict(zip(names, c)) for c in itertools.product(*domains)]
    rows = []
    from dsl import eval_condition
    removed_any = set()  # 全制約のいずれかで落ちた組合せ（重複排除した正味）
    for dsl_text, c in zip(model.constraints, constraints):
        pruned = [e for e in all_combos
                  if eval_condition(c.antecedent, e) and not eval_condition(c.consequent, e)]
        for e in pruned:
            removed_any.add(tuple(e[k] for k in names))
        ex = pruned[0] if pruned else None
        ex_s = ", ".join(f"{k}={ex[k]}" for k in names if k in ex) if ex else "—"
        rows.append([f"`{dsl_text}`", len(pruned), ex_s])
    full = len(all_combos)
    net_removed = len(removed_any)
    body = (
        "# ③ 制約（不可能組合せの除去）\n"
        "# 凡例: dsl=制約式 / prunes=その制約**単体**が全独立空間から落とす組合せ数 / example=落ちる組合せの一例。\n"
        "# 注意: prunes は各制約を**独立に**全空間に当てた数です。制約どうしは重複し得るため、\n"
        "#       **合計しても正味の除外数にはなりません**（下の正味で確認してください）。\n"
        "# レビュー: 制約の正しさ（落としてよい組合せか）。\n\n"
        f"- full（全独立空間）= {full} / 正味除外（いずれかの制約で落ちる, 重複排除）= {net_removed} / "
        f"valid（残る有効空間）= {full - net_removed}\n\n"
        + md_table(["dsl", "prunes", "example"], rows) + "\n"
    )
    w(outdir / "constraints.md", body)


def write_derived_partitions(model, profiles, outdir):
    lines = [
        "# ④ 派生値・連動の同値クラス／境界値と観点",
        "# 凡例: variable=対象 / class=同値クラス / value=代表値 / kind=normal(同値)|boundary(境界) / rationale=観点。",
        "# レビュー: 分割が妥当か（なぜその代表値・境界か）。",
        "",
        "## 連動グループ geometry（physical = pixels / resolution で拘束）",
    ]
    for p in model.coupled():
        lines.append(f"\n### {p.name}（単位: {'dpi' if p.name=='resolution' else 'px'}）")
        parts = p.partitions
        rows = []
        for i, v in enumerate(parts):
            if i == 0:
                kind, why = "boundary", "下限境界"
            elif i == len(parts) - 1:
                kind, why = "boundary", "上限境界"
            else:
                kind, why = "normal", "標準（代表値）"
            rows.append([f"L{i}", v, kind, why])
        lines.append(md_table(["class", "value", "kind", "rationale"], rows))
    lines.append("\n## geometry 代表プロファイル（上位組合せに 1 軸として投入）")
    prof_rows = [[pr["profile"]] + [pr[p.name] for p in model.coupled()] + [pr["level"]] for pr in profiles]
    lines.append(md_table(["profile"] + [p.name for p in model.coupled()] + ["level"], prof_rows))
    lines.append("\n## 派生値")
    for p in model.derived():
        how = f"lookup(from={p.lookup.from_})" + (f" +plus_if({p.plus_if.when})" if p.plus_if else "") if p.lookup else f"expr: {p.expr}"
        lines.append(f"- **{p.name}**: {how}")
    if model.limits.max_file_size is None:
        lines.append("\n> 注: 仕様に file_size / 寸法の数値上限が無いため、file_size の境界値試験は N/A。"
                     "上限が判明したら limits に設定し oracle に file_size ルールを追加してください。")
    w(outdir / "derived_partitions.md", "\n".join(lines) + "\n")


def write_profiles_csv(model, profiles, outdir):
    cols = ["profile", "level"] + [p.name for p in model.coupled()]
    path = outdir / "profiles.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write("# geometry 代表プロファイル。level=min/typ/max、以降は連動各次元の実値\n")
        wr = csv.writer(f)
        wr.writerow(cols)
        for pr in profiles:
            wr.writerow([pr["profile"], pr["level"]] + [pr[p.name] for p in model.coupled()])
    print(f"  wrote {path}")


def write_decision_table(model, rules, metrics, outdir):
    names = [p.name for p in model.independent()]
    # CSV
    csv_path = outdir / "decision_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        f.write(f"# 全有効空間({metrics['valid']}件)を don't-care({DC})圧縮した最小ルール。action=oracle判定。\n")
        wr = csv.writer(f)
        wr.writerow(["rule"] + names + ["action"])
        for i, (cube, action) in enumerate(rules, 1):
            wr.writerow([f"R{i}"] + list(cube) + [action])
    print(f"  wrote {csv_path}")
    # MD
    disp = lambda v: "—" if v == DC else v
    rows = [[f"R{i}"] + [disp(v) for v in cube] + [action] for i, (cube, action) in enumerate(rules, 1)]
    body = (
        "# ⑤ ディシジョンテーブル（全有効空間の don't-care 圧縮 / ロスレス）\n"
        f"# 凡例: 各条件列=その値に固定 / —=don't-care(結果に影響しない=どの値でも可) / action=期待結果(usable|unusable)。\n"
        f"#       verdict は独立因子のみで決まる（geometry は判定に非依存=直交、profiles.csv で別管理）。\n"
        f"# metrics: full={metrics['full']} valid={metrics['valid']} compressed={metrics['compressed']} pairwise={metrics['pairwise']}\n\n"
        + md_table(["rule"] + names + ["action"], rows) + "\n"
    )
    if model.notes:
        body += ("\n## 前提・仮定（action はこれらに依存／要レビュー）\n"
                 "action 判定は A-2 `parameters.yaml` の以下の前提に基づきます。"
                 "「要レビュー/推測」を含むものは、この表および生成テストにも伝搬しています:\n"
                 + "\n".join(f"- {n}" for n in model.notes) + "\n")
    w(outdir / "decision_table.md", body)


def write_pairwise_csv(model, header, data, profiles, outdir):
    oracle_rules = compile_oracle(model)
    cast = _cast(model)
    prof_by = {pr["profile"]: pr for pr in profiles}
    coupled = [p.name for p in model.coupled()]
    derived_cols = [p.name for p in model.derived()]
    cols = [p.name for p in model.independent()] + coupled + derived_cols + ["geometry", "action"]
    path = outdir / "pairwise.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write("# PICT covering set: pairwise + 強相互作用フル網羅。geometry は代表プロファイル。action=oracle判定。\n")
        wr = csv.writer(f)
        wr.writerow(cols)
        for row in data:
            env = {p.name: cast(p.name, row[p.name]) for p in model.independent()}
            prof = prof_by.get(row.get("geometry"))
            if prof:
                for c in coupled:
                    env[c] = prof[c]
            env2 = compute_derived(model, env)
            action = oracle_verdict(oracle_rules, model.oracle.otherwise, env2)
            out = [env.get(p.name) for p in model.independent()]
            out += [env.get(c) for c in coupled]
            out += [env2.get(d) for d in derived_cols]
            out += [row.get("geometry", ""), action]
            wr.writerow(out)
    print(f"  wrote {path} ({len(data)} cases)")
    return len(data)


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="parameters.yaml → ディシジョンテーブル")
    ap.add_argument("params", nargs="?", default="out/1b_parameters/parameters.yaml")
    ap.add_argument("--outdir", type=Path, default=Path("out/2_decision_table"))
    args = ap.parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)

    model = load_parameters(args.params)
    constraints = compile_constraints(model)
    oracle_rules = compile_oracle(model)
    _assert_verdict_independent_of_geometry(model, oracle_rules)
    profiles = build_profiles(model)

    # 全有効空間 → verdict → don't-care 圧縮
    indep = model.independent()
    names = [p.name for p in indep]
    domains = [list(p.values) for p in indep]
    full_combos = [dict(zip(names, c)) for c in itertools.product(*domains)]
    valid = [e for e in full_combos if constraints_satisfied(constraints, e)]
    verdicts = {tuple(e[n] for n in names): verdict_of(model, oracle_rules, e) for e in valid}
    valid_tuples = list(verdicts.keys())
    order = list(range(len(names)))
    rules = compress(valid_tuples, verdicts, domains, order)

    # PICT covering set
    header, data = run_pict(model, profiles, args.outdir / "_pict_model.txt")

    metrics = {"full": len(full_combos), "valid": len(valid),
               "compressed": len(rules), "pairwise": len(data)}

    print("== B 出力 ==")
    write_independent_factors(model, args.outdir)
    write_interaction_strength(model, args.outdir)
    write_constraints(model, args.outdir)
    write_derived_partitions(model, profiles, args.outdir)
    write_profiles_csv(model, profiles, args.outdir)
    write_decision_table(model, rules, metrics, args.outdir)
    write_pairwise_csv(model, header, data, profiles, args.outdir)

    print(f"\nmetrics: full={metrics['full']} valid={metrics['valid']} "
          f"compressed={metrics['compressed']} rules / pairwise={metrics['pairwise']} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
