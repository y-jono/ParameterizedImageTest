#!/usr/bin/env python3
"""A-2 検証（lint）: parameters.yaml を機械検査してレビューに差し戻す。

検査項目:
  1. 構造          : pydantic スキーマに適合するか
  2. DSL パース     : すべての式（constraints/oracle/relations/derived/plus_if）が文法に適合するか
  3. 名前解決       : 式が参照する識別子が、既知のパラメータ/値/関係/limits のいずれかか（タイポ検出）
  4. lookup 整合    : derived.lookup の from が実在し、map のキーがその値域に収まるか
  5. interactions   : 参照ペアが実在パラメータか
  6. オラクル網羅/矛盾: 有効空間を列挙し、(a) otherwise で網羅を保証、(b) 到達不能ルールを警告、
                       (c) 同一ケースに複数ルールが一致し判定が割れる「矛盾」を警告（first-match で隠れる重複）

使い方:
    uv run python src/a2_lint.py out/1b_parameters/parameters.yaml
終了コード 0=合格 / 1=要修正。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dsl import (  # noqa: E402
    Constraint,
    VerdictRule,
    parse_arith,
    parse_assignment,
    parse_condition,
    parse_rule,
    referenced_names,
)
from derive import (  # noqa: E402
    compile_constraints,
    compile_oracle,
    compute_derived,
    oracle_all_matches,
    representative_geometry,
    valid_independent_space,
)
from schema.models import ParametersModel, load_parameters

RED = "\033[31m"
GRN = "\033[32m"
YEL = "\033[33m"
RST = "\033[0m"


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.infos: list[str] = []

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warns.append(m)

    def info(self, m):
        self.infos.append(m)

    def dump(self) -> int:
        for m in self.infos:
            print(f"  {m}")
        for m in self.warns:
            print(f"{YEL}  WARN {RST}{m}")
        for m in self.errors:
            print(f"{RED}  ERROR{RST} {m}")
        print()
        if self.errors:
            print(f"{RED}FAIL{RST}: {len(self.errors)} error(s), {len(self.warns)} warning(s) — 修正して再実行してください。")
            return 1
        print(f"{GRN}PASS{RST}: 0 error(s), {len(self.warns)} warning(s)。")
        return 0


def _known_names(model: ParametersModel) -> set:
    names = set(model.all_names())
    for p in model.independent():
        for v in p.values or []:
            if isinstance(v, str):
                names.add(v)
    for r in model.relations:
        try:
            names.add(parse_assignment(r).name)
        except Exception:
            pass
    names |= {"max_dimension", "max_file_size"}
    return names


def _check_names(label: str, node, known: set, rep: Report):
    unknown = referenced_names(node) - known
    if unknown:
        rep.err(f"{label}: 未知の識別子 {sorted(unknown)}（タイポ?／パラメータ・値・relations・limits のいずれかにしてください）")


def lint(path: str) -> int:
    print(f"== a2_lint: {path} ==")
    rep = Report()

    # 1) 構造
    try:
        model = load_parameters(path)
    except Exception as e:
        print(f"{RED}  ERROR{RST} 構造検証に失敗:\n{e}")
        print(f"\n{RED}FAIL{RST}: スキーマ不適合。")
        return 1
    rep.info(f"構造OK: parameters={len(model.parameters)} "
             f"(independent={len(model.independent())}, derived={len(model.derived())}, coupled={len(model.coupled())})")

    known = _known_names(model)

    # 2)+3) DSL パース & 名前解決
    try:
        for c in model.constraints:
            r = parse_rule(c)
            if not isinstance(r, Constraint):
                rep.err(f"constraint は 'when A then B' 形式が必要: {c!r}")
            else:
                _check_names(f"constraint {c!r}", r, known, rep)
        for s in model.oracle.rules:
            r = parse_rule(s)
            if not isinstance(r, VerdictRule):
                rep.err(f"oracle.rule は 'when 条件 then usable|unusable' が必要: {s!r}")
            else:
                _check_names(f"oracle {s!r}", r, known, rep)
        for r in model.relations:
            a = parse_assignment(r)
            _check_names(f"relation {r!r}", a, known, rep)
        for p in model.derived():
            if p.expr:
                _check_names(f"derived[{p.name}].expr", parse_arith(p.expr), known, rep)
            if p.plus_if:
                _check_names(f"derived[{p.name}].plus_if.when", parse_condition(p.plus_if.when), known, rep)
    except Exception as e:
        rep.err(f"DSL パース失敗: {e}")
        return rep.dump()

    # 4) lookup 整合
    by_name = model.by_name()
    for p in model.derived():
        if p.lookup:
            src = by_name.get(p.lookup.from_)
            if src is None or src.kind != "independent":
                rep.err(f"derived[{p.name}].lookup.from='{p.lookup.from_}' は独立パラメータである必要があります")
            else:
                domain = {str(v) for v in (src.values or [])}
                extra = set(p.lookup.map) - domain
                missing = domain - set(p.lookup.map)
                if extra:
                    rep.err(f"derived[{p.name}].lookup.map に '{p.lookup.from_}' の値域外キー {sorted(extra)}")
                if missing:
                    rep.warn(f"derived[{p.name}].lookup.map に未対応の値 {sorted(missing)}（既定なしだと計算スキップ）")

    # 5) interactions
    for pair in model.interactions:
        for n in pair:
            if n not in model.all_names():
                rep.err(f"interactions の '{n}' は実在しないパラメータです")

    # 6) オラクル網羅/矛盾（有効空間を列挙、代表 geometry で派生評価）
    try:
        constraints = compile_constraints(model)
        oracle_rules = compile_oracle(model)
    except Exception as e:
        rep.err(str(e))
        return rep.dump()

    geo = representative_geometry(model)
    valid = valid_independent_space(model, constraints)
    fired = set()
    usable = unusable = otherwise_cnt = 0
    contradictions: dict = {}  # (i, j) -> 競合した最初の例（env）
    for env in valid:
        env2 = compute_derived(model, {**env, **geo})
        matched = oracle_all_matches(oracle_rules, env2)
        # 矛盾検出: 同一ケースに複数ルールが一致し、判定が割れている（first-match で隠れる）
        if matched and len({oracle_rules[m].verdict for m in matched}) > 1:
            first = matched[0]
            for m in matched[1:]:
                if oracle_rules[m].verdict != oracle_rules[first].verdict:
                    contradictions.setdefault((first, m), env)
        idx = matched[0] if matched else -1
        if idx < 0:
            otherwise_cnt += 1
            verdict = model.oracle.otherwise
        else:
            fired.add(idx)
            verdict = oracle_rules[idx].verdict
        if verdict == "usable":
            usable += 1
        else:
            unusable += 1

    full = 1
    for p in model.independent():
        full *= len(p.values)
    rep.info(f"独立空間: full={full}, valid(制約後)={len(valid)}")
    rep.info(f"オラクル判定(代表geometry): usable={usable}, unusable={unusable}, otherwiseに落ちた={otherwise_cnt}")

    for i, vr in enumerate(oracle_rules):
        if i not in fired:
            rep.warn(f"到達不能なoracleルール #{i+1}: {model.oracle.rules[i]!r}（先行ルールに覆われている可能性）")

    # 矛盾（同一ケースに複数ルールが一致し判定が割れる。first-match で隠れるが意図しない可能性）
    for (i, j), env in sorted(contradictions.items()):
        ex = ", ".join(f"{k}={v}" for k, v in env.items())
        rep.warn(
            f"oracle 重複: ルール #{i+1}({oracle_rules[i].verdict}) と #{j+1}({oracle_rules[j].verdict}) が"
            f"同一ケースで一致し判定が割れます（first-match で #{i+1} 採用）。例: {ex}。"
            f"→ 例外を先に置く意図ならOK。意図しない矛盾なら順序か条件を見直してください。"
        )

    if len(valid) == 0:
        rep.err("有効な組合せが0件です（constraints が過剰）")

    return rep.dump()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "out/1b_parameters/parameters.yaml"
    raise SystemExit(lint(target))
