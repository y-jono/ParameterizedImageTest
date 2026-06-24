#!/usr/bin/env python3
"""C: ディシジョンテーブル → 入力画像（3次出力）＋検証。

decision_table.csv の各圧縮ルールを具体値にインスタンス化し、ImageMagick で
テスト画像を生成、exiftool/identify で読み戻して intended と突合する。
PSD は自動生成対象外（manifest に generation=manual で記録）。

出力:
  out/3_images/TC####_*.jpg|tif   生成画像
  out/3_images/manifest.csv       intended/actual/match/expected/由来ルール
  out/3_images/verify_report.md   意図↔実測の一致/不一致サマリ

使い方:
    uv run python src/c_generate.py
"""
from __future__ import annotations

import argparse
import csv
import itertools
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import image_spec  # noqa: E402
from derive import (  # noqa: E402
    compile_constraints,
    compile_oracle,
    compute_derived,
    constraints_satisfied,
    oracle_verdict,
)
from schema.models import ParametersModel, load_parameters  # noqa: E402

FIELDS = ["format", "color_mode", "bit_depth", "compression", "alpha", "icc_profile"]
DC = "*"


def load_rules(path: Path, names: List[str]) -> List[Dict]:
    """decision_table.csv（don't-care 圧縮）/ pairwise.csv（具体）どちらも読める。

    FIELDS 列と action 列を名前で拾う。rule 列があれば ID に使い、無ければ連番。
    """
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    reader = csv.DictReader(lines)
    rules = []
    for i, row in enumerate(reader, 1):
        cube = {f: row[f] for f in FIELDS}
        rid = row.get("rule") or f"C{i}"
        rules.append({"id": rid, "cube": cube, "action": row.get("action", "")})
    return rules


def valid_combos(model: ParametersModel) -> List[Dict]:
    cons = compile_constraints(model)
    indep = model.independent()
    names = [p.name for p in indep]
    domains = [list(p.values) for p in indep]
    out = []
    for c in itertools.product(*domains):
        env = dict(zip(names, c))
        if constraints_satisfied(cons, env):
            out.append(env)
    return out


def instantiate(cube: Dict, valids: List[Dict], model: ParametersModel) -> Dict:
    """cube に一致する有効組合せから、決定的な代表（値リスト順で最小）を選ぶ。"""
    order = {p.name: {str(v): i for i, v in enumerate(p.values)} for p in model.independent()}

    def matches(env):
        return all(cube[k] == DC or cube[k] == str(env[k]) for k in cube)

    def pref(env):
        return tuple(order[k].get(str(env[k]), 99) for k in cube)

    cands = [e for e in valids if matches(e)]
    chosen = min(cands, key=pref)
    # decision_table の列は文字列。元の型（bit_depth=int等）に戻す
    return dict(chosen)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ディシジョンテーブル → 入力画像＋検証")
    ap.add_argument("--params", default="out/1b_parameters/parameters.yaml")
    ap.add_argument("--table", type=Path, default=Path("out/2_decision_table/decision_table.csv"))
    ap.add_argument("--outdir", type=Path, default=Path("out/3_images"))
    args = ap.parse_args(argv)

    missing = image_spec.tools_available()
    if missing:
        print(f"ERROR: 必要なツールが見つかりません: {missing}（brew install imagemagick exiftool）", file=sys.stderr)
        return 1

    args.outdir.mkdir(parents=True, exist_ok=True)
    model = load_parameters(args.params)
    oracle_rules = compile_oracle(model)
    names = [p.name for p in model.independent()]
    rules = load_rules(args.table, names)
    valids = valid_combos(model)

    manifest: List[Dict] = []
    n_match = n_mismatch = n_manual = 0
    print(f"== C 画像生成（{len(rules)} ルール）==")

    for r in rules:
        case = instantiate(r["cube"], valids, model)
        intended = {k: case[k] for k in FIELDS}
        # sanity: 具体ケースの判定が由来ルールの action と一致するはず
        env2 = compute_derived(model, case)
        verdict = oracle_verdict(oracle_rules, model.oracle.otherwise, env2)

        cid = f"TC{len(manifest)+1:04d}"
        row = {"case_id": cid, "source_rule": r["id"], "expected": verdict}
        row.update({f"intended_{k}": intended[k] for k in FIELDS})

        if intended["format"] == "PSD":
            n_manual += 1
            fname = image_spec.filename(cid, intended)
            row["file"] = fname
            row["generation"] = "manual"
            row["match"] = "n/a"
            for k in FIELDS:
                row[f"actual_{k}"] = ""
            print(f"  {cid} {fname}  -> MANUAL (PSDは手動作成)")
        else:
            fname = image_spec.filename(cid, intended)
            out_path = args.outdir / fname
            ok, msg = image_spec.generate(intended, out_path)
            row["file"] = fname
            row["generation"] = "auto"
            if not ok:
                row["match"] = "GEN_FAIL"
                for k in FIELDS:
                    row[f"actual_{k}"] = ""
                n_mismatch += 1
                print(f"  {cid} {fname}  -> GEN FAIL: {msg}")
            else:
                v = image_spec.verify(out_path, intended)
                for k in FIELDS:
                    row[f"actual_{k}"] = v["actual"][k]
                row["match"] = "true" if v["match"] else "false"
                row["_checks"] = v["checks"]
                if v["match"]:
                    n_match += 1
                    print(f"  {cid} {fname}  -> OK")
                else:
                    n_mismatch += 1
                    bad = [k for k, ok in v["checks"].items() if not ok]
                    print(f"  {cid} {fname}  -> MISMATCH {bad}")
        manifest.append(row)

    write_manifest(args.outdir / "manifest.csv", manifest)
    write_report(args.outdir / "verify_report.md", manifest,
                 {"match": n_match, "mismatch": n_mismatch, "manual": n_manual})

    print(f"\n生成: auto一致={n_match}, 不一致={n_mismatch}, PSD手動={n_manual}")
    return 1 if n_mismatch else 0


def write_manifest(path: Path, manifest: List[Dict]):
    cols = (["case_id", "file", "source_rule", "expected", "generation", "match"]
            + [f"intended_{k}" for k in FIELDS] + [f"actual_{k}" for k in FIELDS])
    with path.open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["# intended=要求値 / actual=読み戻し値 / match=全フィールド一致 / "
                     "expected=oracle判定(usable|unusable) / source_rule=由来ルールID / generation=auto|manual"])
        wr.writerow(cols)
        for r in manifest:
            wr.writerow([r.get(c, "") for c in cols])
    print(f"  wrote {path}")


def write_report(path: Path, manifest: List[Dict], summ: Dict):
    lines = [
        "# C 検証レポート（intended ↔ actual）",
        "",
        "> 凡例: ✓=一致 / ✗=不一致 / –=対象外。各画像は意図したメタデータを実際に持つか読み戻して検証。",
        f"> 注: 画像は 640x480 固定で生成（寸法は本仕様のオラクル対象外＝サイズ上限なし）。",
        "",
        f"**サマリ: 自動生成一致 {summ['match']} / 不一致 {summ['mismatch']} / PSD手動 {summ['manual']}**",
        "",
        "| case | rule | expected | " + " | ".join(FIELDS) + " | match |",
        "|" + "---|" * (4 + len(FIELDS)),
    ]
    for r in manifest:
        cells = []
        checks = r.get("_checks", {})
        if r.get("generation") == "manual":
            cells = ["–"] * len(FIELDS)
            match = "manual"
        else:
            for k in FIELDS:
                mk = checks.get(k)
                mark = "✓" if mk else ("✗" if mk is False else "–")
                cells.append(f'{r.get(f"intended_{k}")}{mark}')
            match = r.get("match")
        lines.append(f'| {r["case_id"]} | {r["source_rule"]} | {r["expected"]} | '
                     + " | ".join(cells) + f" | {match} |")
    # 不一致の詳細
    bad = [r for r in manifest if r.get("match") == "false"]
    if bad:
        lines += ["", "## 不一致の詳細（intended → actual）"]
        for r in bad:
            for k in FIELDS:
                if r.get("_checks", {}).get(k) is False:
                    lines.append(f'- {r["case_id"]} {k}: intended={r[f"intended_{k}"]} → actual={r[f"actual_{k}"]}')
    # PSD 手動作成の手引き
    man = [r for r in manifest if r.get("generation") == "manual"]
    if man:
        lines += ["", "## PSD（手動作成対象）",
                  "Photoshop 等で以下の仕様の PSD を作成し out/3_images/ に配置してください:"]
        for r in man:
            spec = ", ".join(f'{k}={r[f"intended_{k}"]}' for k in FIELDS)
            lines.append(f'- {r["case_id"]} ({r["file"]}): {spec} / expected={r["expected"]}')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path}")


if __name__ == "__main__":
    raise SystemExit(main())
