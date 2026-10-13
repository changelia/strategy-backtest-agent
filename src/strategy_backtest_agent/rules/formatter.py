"""Deterministic, parenthesized strategy summaries."""

from strategy_backtest_agent.rules.models import Comparison, Indicator, Operand, Price, Rule


def format_operand(operand: Operand) -> str:
    if isinstance(operand, Price):
        return "PRICE"
    if isinstance(operand, Indicator):
        return f"{operand.name.upper()}({operand.period})"
    return f"{operand.value:g}"


def format_rule(rule: Rule) -> str:
    if isinstance(rule, Comparison):
        return f"{format_operand(rule.left)} {rule.operator} {format_operand(rule.right)}"
    return "(" + f" {rule.type.upper()} ".join(map(format_rule, rule.conditions)) + ")"
