"""
Dazzle typed expression language.

Tokenizer, parser, evaluator, and type checker for the unified
expression system described in #275.

Usage:
    from dazzle.core.expression_lang import parse_expr, evaluate

    expr = parse_expr("box1 + box2")
    result = evaluate(expr, {"box1": 100, "box2": 50})
    # result == 150
"""

from dazzle.core.expression_lang.evaluator import evaluate
from dazzle.core.expression_lang.parser import parse_expr
from dazzle.core.expression_lang.type_checker import infer_type

__all__ = ["evaluate", "infer_type", "parse_expr"]
