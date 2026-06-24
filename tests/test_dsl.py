"""imgspec DSL の回帰テスト。  実行: uv run python tests/test_dsl.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dsl import (  # noqa: E402
    Constraint,
    VerdictRule,
    eval_arith,
    eval_condition,
    parse_arith,
    parse_assignment,
    parse_condition,
    parse_rule,
    referenced_names,
    to_pict,
)

PARAMS = {"format", "color_mode", "bit_depth", "compression", "alpha", "icc_profile", "platform_quicktime"}


def test_constraint_and_pict():
    c = parse_rule("when format is JPEG then compression is none and bit_depth is 8")
    assert isinstance(c, Constraint)
    assert to_pict(c, PARAMS) == 'IF [format] = "JPEG" THEN ([compression] = "none" AND [bit_depth] = 8);'


def test_verdict_rule():
    v = parse_rule("when color_mode in [CMYK, Grayscale] then unusable")
    assert isinstance(v, VerdictRule) and v.verdict == "unusable"
    assert eval_condition(v.condition, {"color_mode": "CMYK"}) is True
    assert eval_condition(v.condition, {"color_mode": "RGB"}) is False


def test_arith():
    e = parse_arith("width * height * channels * (bit_depth / 8) / compression_ratio")
    env = {"width": 4000, "height": 3000, "channels": 3, "bit_depth": 8, "compression_ratio": 1}
    assert eval_arith(e, env) == 36000000.0


def test_assignment():
    a = parse_assignment("physical_w_inch = width / resolution")
    assert a.name == "physical_w_inch"
    assert eval_arith(a.expr, {"width": 3600, "resolution": 720}) == 5.0


def test_numeric_compare():
    g = parse_condition("bit_depth >= 16")
    assert eval_condition(g, {"bit_depth": 16}) is True
    assert eval_condition(g, {"bit_depth": 8}) is False


def test_referenced_names():
    v = parse_rule("when file_size > max_file_size then unusable")
    assert referenced_names(v) == {"file_size", "max_file_size"}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nALL {len(fns)} DSL TESTS PASSED")
