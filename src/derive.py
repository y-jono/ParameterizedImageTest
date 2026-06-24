"""共有評価エンジン: 制約判定・派生値計算・オラクル評価・独立空間の列挙。

a2_lint.py（検証）と b_table.py（組合せ生成）の両方が使う。DSL 式のパースは
キャッシュし、評価はすべて決定的（env に対して一意）。
"""
from __future__ import annotations

import itertools
from functools import lru_cache
from typing import Dict, Iterator, List

from dsl import (
    Constraint,
    VerdictRule,
    eval_arith,
    eval_condition,
    parse_arith,
    parse_assignment,
    parse_condition,
    parse_rule,
)
from schema.models import ParametersModel


# --- パース結果のキャッシュ（同じ式を何度も評価するため） ---
@lru_cache(maxsize=None)
def _rule(text: str):
    return parse_rule(text)


@lru_cache(maxsize=None)
def _cond(text: str):
    return parse_condition(text)


@lru_cache(maxsize=None)
def _assign(text: str):
    return parse_assignment(text)


@lru_cache(maxsize=None)
def _arith(text: str):
    return parse_arith(text)


# --------------------------------------------------------------------------- #
# 制約
# --------------------------------------------------------------------------- #
def compile_constraints(model: ParametersModel) -> List[Constraint]:
    out = []
    for c in model.constraints:
        r = _rule(c)
        if not isinstance(r, Constraint):
            raise ValueError(f"constraints は 'when A then B'（含意）である必要があります: {c!r}")
        out.append(r)
    return out


def constraints_satisfied(constraints: List[Constraint], env: Dict) -> bool:
    """すべての含意 (A->B) が満たされる組合せか。"""
    for c in constraints:
        if eval_condition(c.antecedent, env) and not eval_condition(c.consequent, env):
            return False
    return True


# --------------------------------------------------------------------------- #
# 派生値
# --------------------------------------------------------------------------- #
def compute_derived(model: ParametersModel, env: Dict) -> Dict:
    """env に派生値（lookup→relations→expr の順）を加えた新しい dict を返す。

    参照変数が env に無い派生は計算をスキップ（None にせず未設定のまま）。
    """
    env = dict(env)
    # pass 1: lookup 系（channels, compression_ratio ...）
    for p in model.derived():
        if p.lookup:
            key = env.get(p.lookup.from_)
            if key is None:
                continue
            val = p.lookup.map.get(str(key))
            if val is None:
                continue
            if p.plus_if and eval_condition(_cond(p.plus_if.when), env):
                val = val + p.plus_if.add
            env[p.name] = val
    # pass 2: relations（physical_* など）
    for r in model.relations:
        a = _assign(r)
        try:
            env[a.name] = eval_arith(a.expr, env)
        except KeyError:
            pass
    # pass 3: expr 系（file_size ...）
    for p in model.derived():
        if p.expr:
            try:
                env[p.name] = eval_arith(_arith(p.expr), env)
            except KeyError:
                pass
    return env


# --------------------------------------------------------------------------- #
# オラクル
# --------------------------------------------------------------------------- #
def compile_oracle(model: ParametersModel) -> List[VerdictRule]:
    out = []
    for s in model.oracle.rules:
        r = _rule(s)
        if not isinstance(r, VerdictRule):
            raise ValueError(f"oracle.rules は 'when 条件 then usable|unusable' である必要があります: {s!r}")
        out.append(r)
    return out


def oracle_verdict(rules: List[VerdictRule], otherwise: str, env: Dict) -> str:
    for vr in rules:
        if eval_condition(vr.condition, env):
            return vr.verdict
    return otherwise


def oracle_matched_index(rules: List[VerdictRule], env: Dict) -> int:
    """先頭から最初に一致したルールの index。どれも一致しなければ -1（=otherwise）。"""
    for i, vr in enumerate(rules):
        if eval_condition(vr.condition, env):
            return i
    return -1


# --------------------------------------------------------------------------- #
# 独立因子の空間
# --------------------------------------------------------------------------- #
def independent_space(model: ParametersModel) -> Iterator[Dict]:
    """独立因子の全直積（制約適用前）。"""
    factors = model.independent()
    names = [f.name for f in factors]
    for combo in itertools.product(*[f.values for f in factors]):
        yield dict(zip(names, combo))


def valid_independent_space(model: ParametersModel, constraints: List[Constraint]) -> List[Dict]:
    """制約を満たす独立因子の組合せ一覧。"""
    return [env for env in independent_space(model) if constraints_satisfied(constraints, env)]


def representative_geometry(model: ParametersModel) -> Dict:
    """連動グループの代表値（各 partition の中央値）。lint の派生評価などに使う。"""
    geo: Dict = {}
    for p in model.coupled():
        parts = p.partitions
        geo[p.name] = parts[len(parts) // 2]
    return geo
