"""Code complexity metrics: cyclomatic, cognitive, maintainability index, Halstead."""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass


@dataclass
class ComplexityResult:
    cyclomatic: float
    cognitive: float
    maintainability_index: float
    halstead_volume: float
    lines_of_code: int
    logical_lines: int
    per_function: list[dict]


# ── Cyclomatic complexity ──────────────────────────────────────────────────────

_BRANCHING_NODES = (
    ast.If, ast.IfExp, ast.For, ast.AsyncFor,
    ast.While, ast.ExceptHandler, ast.With, ast.AsyncWith,
    ast.Assert, ast.BoolOp,
)


def cyclomatic_complexity(tree: ast.AST) -> int:
    """Compute McCabe cyclomatic complexity for an AST."""
    complexity = 1  # base path
    for node in ast.walk(tree):
        if isinstance(node, _BRANCHING_NODES):
            if isinstance(node, ast.BoolOp):
                # Each `and`/`or` adds a branch
                complexity += len(node.values) - 1
            else:
                complexity += 1
    return complexity


# ── Cognitive complexity ───────────────────────────────────────────────────────

def cognitive_complexity(tree: ast.AST) -> int:
    """Compute cognitive complexity (Sonar-style) measuring how hard code is to understand."""
    return _cognitive_walk(tree, nesting=0)


def _cognitive_walk(node: ast.AST, nesting: int) -> int:
    total = 0
    increments_nesting = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                          ast.AsyncWith, ast.ExceptHandler)
    structural = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)
    for child in ast.iter_child_nodes(node):
        if isinstance(child, structural):
            # Structural increment + nesting penalty
            total += 1 + nesting
            total += _cognitive_walk(child, nesting + 1)
        elif isinstance(child, (ast.With, ast.AsyncWith)):
            total += _cognitive_walk(child, nesting + 1)
        elif isinstance(child, ast.BoolOp):
            total += 1  # Each boolean sequence
            total += _cognitive_walk(child, nesting)
        elif isinstance(child, ast.IfExp):
            total += 1  # Ternary
            total += _cognitive_walk(child, nesting)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Nested function: increase nesting
            total += _cognitive_walk(child, nesting + 1)
        elif isinstance(child, ast.Lambda):
            total += _cognitive_walk(child, nesting + 1)
        else:
            total += _cognitive_walk(child, nesting)
    return total


# ── Halstead metrics ───────────────────────────────────────────────────────────

def _halstead_counts(tree: ast.AST) -> tuple[int, int, int, int]:
    """Return (unique_operators, unique_operands, total_operators, total_operands)."""
    operators: dict[str, int] = {}
    operands: dict[str, int] = {}

    for node in ast.walk(tree):
        # Operators
        if isinstance(node, ast.BinOp):
            op = type(node.op).__name__
            operators[op] = operators.get(op, 0) + 1
        elif isinstance(node, ast.UnaryOp):
            op = type(node.op).__name__
            operators[op] = operators.get(op, 0) + 1
        elif isinstance(node, ast.BoolOp):
            op = type(node.op).__name__
            operators[op] = operators.get(op, 0) + len(node.values) - 1
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                op_name = type(op).__name__
                operators[op_name] = operators.get(op_name, 0) + 1
        elif isinstance(node, ast.Assign):
            operators["Assign"] = operators.get("Assign", 0) + 1
        elif isinstance(node, ast.Call):
            operators["Call"] = operators.get("Call", 0) + 1
        # Operands
        elif isinstance(node, ast.Name):
            operands[node.id] = operands.get(node.id, 0) + 1
        elif isinstance(node, ast.Constant):
            key = repr(node.value)
            operands[key] = operands.get(key, 0) + 1

    n1 = len(operators)
    n2 = len(operands)
    N1 = sum(operators.values())
    N2 = sum(operands.values())
    return n1, n2, N1, N2


def halstead_volume(tree: ast.AST) -> float:
    n1, n2, N1, N2 = _halstead_counts(tree)
    n = n1 + n2
    N = N1 + N2
    if n == 0:
        return 0.0
    return N * math.log2(n) if n > 0 else 0.0


# ── Maintainability Index ──────────────────────────────────────────────────────

def maintainability_index(
    halstead_vol: float, cyclo: float, loc: int
) -> float:
    """Compute the Maintainability Index (Microsoft variant, 0-100 scale)."""
    if loc == 0:
        return 100.0
    ln_vol = math.log(halstead_vol) if halstead_vol > 0 else 0
    ln_loc = math.log(loc) if loc > 0 else 0
    mi = 171 - 5.2 * ln_vol - 0.23 * cyclo - 16.2 * ln_loc
    # Normalize to 0-100
    return max(0.0, min(100.0, mi * 100 / 171))


# ── Per-function breakdown ─────────────────────────────────────────────────────

def per_function_complexity(tree: ast.AST) -> list[dict]:
    results = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = cyclomatic_complexity(node)
            cog = cognitive_complexity(node)
            results.append({
                "name": node.name,
                "line": node.lineno,
                "cyclomatic": cc,
                "cognitive": cog,
                "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
            })
    return results


# ── Unified entry point ───────────────────────────────────────────────────────

def compute_complexity(code: str) -> ComplexityResult:
    """Compute all complexity metrics for a Python source string."""
    tree = ast.parse(code)
    lines = code.split("\n")
    loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])
    logical = len([l for l in lines if l.strip()])

    cc = cyclomatic_complexity(tree)
    cog = cognitive_complexity(tree)
    hv = halstead_volume(tree)
    mi = maintainability_index(hv, cc, loc)
    pf = per_function_complexity(tree)

    return ComplexityResult(
        cyclomatic=cc,
        cognitive=cog,
        maintainability_index=round(mi, 2),
        halstead_volume=round(hv, 2),
        lines_of_code=loc,
        logical_lines=logical,
        per_function=pf,
    )
