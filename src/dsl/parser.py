"""imgspec DSL — パーサ・評価器・PICTトランスパイラ。

LLM が起草した式（constraints / oracle / formula / relations）を、この文法で
決定的にパース・評価する。曖昧さはゼロ。評価結果は env（パラメータ名→値の辞書）に
対して一意に定まる。

公開API:
    parse_rule(text)        -> Constraint | VerdictRule
    parse_condition(text)   -> Cond ノード
    parse_arith(text)       -> Expr ノード
    parse_assignment(text)  -> Assignment
    eval_condition(node, env) -> bool
    eval_arith(node, env)     -> int|float
    to_pict(constraint, params) -> str   # 制約を PICT 文法へ
    referenced_names(node)  -> set[str]  # lint 用：式が参照する識別子
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

from lark import Lark, Transformer, Token

_GRAMMAR_PATH = Path(__file__).with_name("imgspec.lark")
_STARTS = ["start_rule", "start_condition", "start_assignment", "start_arith"]


# --------------------------------------------------------------------------- #
# AST ノード
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Num:
    value: Union[int, float]


@dataclass(frozen=True)
class Str:
    value: str


@dataclass(frozen=True)
class Name:
    id: str


Operand = Union[Num, Str, Name]


@dataclass(frozen=True)
class Compare:
    op: str  # eq ne gt ge lt le in
    left: Operand
    right: Union[Operand, tuple]  # in の場合は tuple(Operand,...)


@dataclass(frozen=True)
class And:
    left: "Cond"
    right: "Cond"


@dataclass(frozen=True)
class Or:
    left: "Cond"
    right: "Cond"


@dataclass(frozen=True)
class Not:
    item: "Cond"


Cond = Union[Compare, And, Or, Not]


@dataclass(frozen=True)
class BinOp:
    op: str  # + - * /
    left: "Expr"
    right: "Expr"


Expr = Union[Num, Name, BinOp]


@dataclass(frozen=True)
class Verdict:
    value: str  # "usable" | "unusable"


@dataclass(frozen=True)
class Constraint:
    """when <antecedent> then <consequent>  （含意：両方成立する組合せのみ有効）"""
    antecedent: Cond
    consequent: Cond


@dataclass(frozen=True)
class VerdictRule:
    """when <condition> then usable|unusable  （オラクルの1ルール）"""
    condition: Cond
    verdict: str


@dataclass(frozen=True)
class Assignment:
    name: str
    expr: Expr


# --------------------------------------------------------------------------- #
# Transformer: 構文木 -> AST
# --------------------------------------------------------------------------- #
class _ToAst(Transformer):
    def number(self, c):
        t = c[0].value
        return Num(int(t) if "." not in t and "e" not in t.lower() else float(t))

    def string(self, c):
        return Str(c[0].value[1:-1])  # 両端のクォートを除去

    def name(self, c):
        return Name(c[0].value)

    # 比較
    def eq(self, c):
        return Compare("eq", c[0], c[1])

    def ne(self, c):
        return Compare("ne", c[0], c[1])

    def gt(self, c):
        return Compare("gt", c[0], c[1])

    def ge(self, c):
        return Compare("ge", c[0], c[1])

    def lt(self, c):
        return Compare("lt", c[0], c[1])

    def le(self, c):
        return Compare("le", c[0], c[1])

    def in_op(self, c):
        return Compare("in", c[0], tuple(c[1]))

    def arglist(self, c):
        return list(c)

    # 論理
    def or_op(self, c):
        return Or(c[0], c[1])

    def and_op(self, c):
        return And(c[0], c[1])

    def not_op(self, c):
        return Not(c[0])

    # 算術
    def add(self, c):
        return BinOp("+", c[0], c[1])

    def sub(self, c):
        return BinOp("-", c[0], c[1])

    def mul(self, c):
        return BinOp("*", c[0], c[1])

    def div(self, c):
        return BinOp("/", c[0], c[1])

    # 判定語
    def usable(self, c):
        return Verdict("usable")

    def unusable(self, c):
        return Verdict("unusable")

    # エントリポイント
    def start_rule(self, c):
        cond, then = c[0], c[1]
        if isinstance(then, Verdict):
            return VerdictRule(cond, then.value)
        return Constraint(cond, then)

    def start_condition(self, c):
        return c[0]

    def start_arith(self, c):
        return c[0]

    def start_assignment(self, c):
        return Assignment(c[0].value, c[1])


# --------------------------------------------------------------------------- #
# パーサのファクトリ（grammar は一度だけコンパイル）
# --------------------------------------------------------------------------- #
_parser = Lark(_GRAMMAR_PATH.read_text(encoding="utf-8"), start=_STARTS, maybe_placeholders=False)
_transformer = _ToAst()


def _parse(text: str, start: str):
    tree = _parser.parse(text.strip(), start=start)
    return _transformer.transform(tree)


def parse_rule(text: str):
    return _parse(text, "start_rule")


def parse_condition(text: str) -> Cond:
    return _parse(text, "start_condition")


def parse_arith(text: str) -> Expr:
    return _parse(text, "start_arith")


def parse_assignment(text: str) -> Assignment:
    return _parse(text, "start_assignment")


# --------------------------------------------------------------------------- #
# 評価
# --------------------------------------------------------------------------- #
def _resolve(op: Operand, env: dict):
    """operand を値に解決。Name は env にあれば値、無ければ文字列リテラル。"""
    if isinstance(op, Num):
        return op.value
    if isinstance(op, Str):
        return op.value
    if isinstance(op, Name):
        return env[op.id] if op.id in env else op.id
    raise TypeError(f"unknown operand: {op!r}")


def _as_number(v):
    if isinstance(v, bool):  # bool は数値比較から除外（明示エラー）
        raise TypeError("boolean は数値比較に使えません")
    return float(v)


def eval_condition(node: Cond, env: dict) -> bool:
    if isinstance(node, And):
        return eval_condition(node.left, env) and eval_condition(node.right, env)
    if isinstance(node, Or):
        return eval_condition(node.left, env) or eval_condition(node.right, env)
    if isinstance(node, Not):
        return not eval_condition(node.item, env)
    if isinstance(node, Compare):
        op = node.op
        if op == "in":
            left = _resolve(node.left, env)
            members = [_resolve(o, env) for o in node.right]
            return any(_loose_eq(left, m) for m in members)
        left = _resolve(node.left, env)
        right = _resolve(node.right, env)
        if op == "eq":
            return _loose_eq(left, right)
        if op == "ne":
            return not _loose_eq(left, right)
        if op == "gt":
            return _as_number(left) > _as_number(right)
        if op == "ge":
            return _as_number(left) >= _as_number(right)
        if op == "lt":
            return _as_number(left) < _as_number(right)
        if op == "le":
            return _as_number(left) <= _as_number(right)
    raise TypeError(f"cannot evaluate condition node: {node!r}")


def _loose_eq(a, b) -> bool:
    """数値同士は数値比較、それ以外は文字列化して比較（型ゆらぎを吸収）。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return str(a) == str(b)


def eval_arith(node: Expr, env: dict):
    if isinstance(node, Num):
        return node.value
    if isinstance(node, Name):
        if node.id not in env:
            raise KeyError(f"算術式で未定義の変数: {node.id}")
        return env[node.id]
    if isinstance(node, BinOp):
        l = eval_arith(node.left, env)
        r = eval_arith(node.right, env)
        return {"+": l + r, "-": l - r, "*": l * r, "/": l / r}[node.op]
    raise TypeError(f"cannot evaluate arith node: {node!r}")


# --------------------------------------------------------------------------- #
# lint 用: 参照識別子の収集
# --------------------------------------------------------------------------- #
def referenced_names(node) -> set:
    out: set = set()

    def walk(n):
        if isinstance(n, Name):
            out.add(n.id)
        elif isinstance(n, Compare):
            walk(n.left)
            if n.op == "in":
                for o in n.right:
                    walk(o)
            else:
                walk(n.right)
        elif isinstance(n, (And, Or)):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, Not):
            walk(n.item)
        elif isinstance(n, BinOp):
            walk(n.left)
            walk(n.right)
        elif isinstance(n, Constraint):
            walk(n.antecedent)
            walk(n.consequent)
        elif isinstance(n, VerdictRule):
            walk(n.condition)
        elif isinstance(n, Assignment):
            walk(n.expr)

    walk(node)
    return out


# --------------------------------------------------------------------------- #
# PICT トランスパイル（constraints -> PICT 制約文法）
# --------------------------------------------------------------------------- #
def _pict_operand(op: Operand, params: set) -> str:
    if isinstance(op, Num):
        v = op.value
        return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)
    if isinstance(op, Str):
        return f'"{op.value}"'
    if isinstance(op, Name):
        return f"[{op.id}]" if op.id in params else f'"{op.id}"'
    raise TypeError(op)


def _pict_cond(node: Cond, params: set) -> str:
    if isinstance(node, And):
        return f"({_pict_cond(node.left, params)} AND {_pict_cond(node.right, params)})"
    if isinstance(node, Or):
        return f"({_pict_cond(node.left, params)} OR {_pict_cond(node.right, params)})"
    if isinstance(node, Not):
        return f"NOT ({_pict_cond(node.item, params)})"
    if isinstance(node, Compare):
        if node.op == "in":
            members = ", ".join(_pict_operand(o, params) for o in node.right)
            return f"{_pict_operand(node.left, params)} IN {{{members}}}"
        sym = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}[node.op]
        return f"{_pict_operand(node.left, params)} {sym} {_pict_operand(node.right, params)}"
    raise TypeError(node)


def to_pict(constraint: Constraint, params: set) -> str:
    """Constraint(when A then B) -> 'IF <A> THEN <B>;' (PICT 文法)。"""
    ante = _pict_cond(constraint.antecedent, params)
    cons = _pict_cond(constraint.consequent, params)
    return f"IF {ante} THEN {cons};"
