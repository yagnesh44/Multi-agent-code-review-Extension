"""AST-based static analysis for Python (and extensible to other languages).

Extracts structural information and detects rule-based issues that do not
require an LLM, providing deterministic findings and code metrics.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ASTIssue:
    line_start: int
    line_end: int
    severity: str
    category: str
    title: str
    description: str
    suggestion: str
    rule_id: str
    confidence: float = 1.0


@dataclass
class ASTMetrics:
    functions: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    global_vars: list[str] = field(default_factory=list)
    max_nesting: int = 0
    function_count: int = 0
    class_count: int = 0


class PythonASTAnalyzer:
    """Rule-based analyzer using Python's ast module."""

    def analyze(self, code: str, filename: str = "<unknown>") -> tuple[list[ASTIssue], ASTMetrics]:
        issues: list[ASTIssue] = []
        metrics = ASTMetrics()
        try:
            tree = ast.parse(code, filename=filename)
        except SyntaxError as e:
            issues.append(ASTIssue(
                line_start=e.lineno or 1,
                line_end=e.lineno or 1,
                severity="critical",
                category="bug",
                title="Syntax Error",
                description=f"File cannot be parsed: {e.msg}",
                suggestion="Fix the syntax error before further review.",
                rule_id="AST-SYNTAX",
            ))
            return issues, metrics

        # Collect structural info
        self._collect_metrics(tree, metrics)

        # Run rule checks
        issues.extend(self._check_bare_except(tree))
        issues.extend(self._check_mutable_default_args(tree))
        issues.extend(self._check_unused_imports(tree, code))
        issues.extend(self._check_assert_in_non_test(tree, filename))
        issues.extend(self._check_global_variables(tree))
        issues.extend(self._check_too_many_arguments(tree))
        issues.extend(self._check_nested_depth(tree))
        issues.extend(self._check_eval_exec(tree))
        issues.extend(self._check_hardcoded_passwords(code))
        issues.extend(self._check_broad_exception(tree))

        return issues, metrics

    # ── Metrics collection ─────────────────────────────────────────────────

    def _collect_metrics(self, tree: ast.AST, metrics: ASTMetrics):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                metrics.functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "args": len(node.args.args),
                    "lines": (node.end_lineno or node.lineno) - node.lineno + 1,
                })
                metrics.function_count += 1
            elif isinstance(node, ast.ClassDef):
                metrics.classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "methods": sum(
                        1 for n in node.body
                        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                    ),
                })
                metrics.class_count += 1
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    metrics.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        metrics.imports.append(f"{node.module}.{alias.name}")

        metrics.max_nesting = self._compute_max_nesting(tree)

    def _compute_max_nesting(self, tree: ast.AST, depth: int = 0) -> int:
        max_depth = depth
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                                 ast.AsyncFor, ast.AsyncWith)):
                max_depth = max(max_depth, self._compute_max_nesting(node, depth + 1))
            else:
                max_depth = max(max_depth, self._compute_max_nesting(node, depth))
        return max_depth

    # ── Rule checks ────────────────────────────────────────────────────────

    def _check_bare_except(self, tree: ast.AST) -> list[ASTIssue]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(ASTIssue(
                    line_start=node.lineno, line_end=node.lineno,
                    severity="medium", category="bug",
                    title="Bare except clause",
                    description="Catching all exceptions including SystemExit and KeyboardInterrupt "
                                "can mask real errors and make debugging difficult.",
                    suggestion="Catch specific exceptions, e.g., `except ValueError:`.",
                    rule_id="AST-BARE-EXCEPT",
                ))
        return issues

    def _check_broad_exception(self, tree: ast.AST) -> list[ASTIssue]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                name = ""
                if isinstance(node.type, ast.Name):
                    name = node.type.id
                elif isinstance(node.type, ast.Attribute):
                    name = node.type.attr
                if name == "Exception":
                    issues.append(ASTIssue(
                        line_start=node.lineno, line_end=node.lineno,
                        severity="low", category="best_practice",
                        title="Broad exception handler",
                        description="Catching `Exception` is too broad; catch specific exceptions instead.",
                        suggestion="Narrow to the expected exception types.",
                        rule_id="AST-BROAD-EXCEPT", confidence=0.85,
                    ))
        return issues

    def _check_mutable_default_args(self, tree: ast.AST) -> list[ASTIssue]:
        issues = []
        mutable_types = (ast.List, ast.Dict, ast.Set)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for default in node.args.defaults + node.args.kw_defaults:
                    if isinstance(default, mutable_types):
                        issues.append(ASTIssue(
                            line_start=node.lineno, line_end=node.lineno,
                            severity="high", category="bug",
                            title="Mutable default argument",
                            description=f"Function `{node.name}` uses a mutable default argument. "
                                        "This is shared across calls and causes subtle bugs.",
                            suggestion="Use `None` as default and create a new object inside the function.",
                            rule_id="AST-MUTABLE-DEFAULT",
                        ))
        return issues

    def _check_unused_imports(self, tree: ast.AST, code: str) -> list[ASTIssue]:
        issues = []
        imported_names: list[tuple[str, str, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    imported_names.append((local, alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    local = alias.asname or alias.name
                    imported_names.append((local, f"{node.module}.{alias.name}", node.lineno))

        # Simple usage check: see if the local name appears anywhere else in code
        lines = code.split("\n")
        for local_name, full_name, lineno in imported_names:
            if local_name == "*":
                continue
            usage_count = 0
            for i, line in enumerate(lines, 1):
                if i == lineno:
                    continue
                if re.search(rf"\b{re.escape(local_name)}\b", line):
                    usage_count += 1
                    break
            if usage_count == 0:
                issues.append(ASTIssue(
                    line_start=lineno, line_end=lineno,
                    severity="info", category="style",
                    title=f"Unused import: {local_name}",
                    description=f"`{full_name}` is imported but never used.",
                    suggestion="Remove the unused import.",
                    rule_id="AST-UNUSED-IMPORT", confidence=0.90,
                ))
        return issues

    def _check_assert_in_non_test(self, tree: ast.AST, filename: str) -> list[ASTIssue]:
        if "test" in filename.lower():
            return []
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                issues.append(ASTIssue(
                    line_start=node.lineno, line_end=node.lineno,
                    severity="medium", category="bug",
                    title="Assert in production code",
                    description="Assert statements are removed when Python runs with -O flag, "
                                "making this check silently disappear in production.",
                    suggestion="Replace with an explicit if-check and raise an appropriate exception.",
                    rule_id="AST-ASSERT-PROD", confidence=0.80,
                ))
        return issues

    def _check_global_variables(self, tree: ast.AST) -> list[ASTIssue]:
        issues = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_") and target.id.upper() != target.id:
                        issues.append(ASTIssue(
                            line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                            severity="low", category="style",
                            title=f"Module-level mutable variable: {target.id}",
                            description="Mutable module-level variables make code harder to reason about "
                                        "and can cause issues in multi-threaded contexts.",
                            suggestion="Consider encapsulating in a class or using a constant (UPPER_CASE).",
                            rule_id="AST-GLOBAL-MUTABLE", confidence=0.60,
                        ))
        return issues

    def _check_too_many_arguments(self, tree: ast.AST, threshold: int = 6) -> list[ASTIssue]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = node.args
                count = len(args.args) + len(args.kwonlyargs)
                # Subtract 'self'/'cls'
                if args.args and args.args[0].arg in ("self", "cls"):
                    count -= 1
                if count > threshold:
                    issues.append(ASTIssue(
                        line_start=node.lineno, line_end=node.lineno,
                        severity="medium", category="style",
                        title=f"Too many parameters ({count}) in `{node.name}`",
                        description=f"Function has {count} parameters (threshold: {threshold}). "
                                    "This indicates the function may be doing too much.",
                        suggestion="Group related parameters into a data class or split the function.",
                        rule_id="AST-TOO-MANY-ARGS", confidence=0.85,
                    ))
        return issues

    def _check_nested_depth(self, tree: ast.AST, threshold: int = 4) -> list[ASTIssue]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                depth = self._compute_max_nesting(node)
                if depth > threshold:
                    issues.append(ASTIssue(
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        severity="medium", category="style",
                        title=f"Deep nesting ({depth} levels) in `{node.name}`",
                        description=f"Maximum nesting depth is {depth} (threshold: {threshold}). "
                                    "Deep nesting reduces readability.",
                        suggestion="Use early returns, guard clauses, or extract helper functions.",
                        rule_id="AST-DEEP-NESTING", confidence=0.90,
                    ))
        return issues

    def _check_eval_exec(self, tree: ast.AST) -> list[ASTIssue]:
        issues = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name in ("eval", "exec"):
                    issues.append(ASTIssue(
                        line_start=node.lineno, line_end=node.lineno,
                        severity="critical", category="security",
                        title=f"Use of `{func_name}()` — code injection risk",
                        description=f"`{func_name}()` executes arbitrary code and is a severe security risk "
                                    "if any part of the input comes from untrusted sources.",
                        suggestion=f"Avoid `{func_name}()`. Use `ast.literal_eval()` for data parsing "
                                   "or a proper parser for expressions.",
                        rule_id="AST-EVAL-EXEC",
                    ))
        return issues

    def _check_hardcoded_passwords(self, code: str) -> list[ASTIssue]:
        issues = []
        patterns = [
            (r'(?i)(password|passwd|pwd|secret|api_key|apikey|token|auth)\s*=\s*["\'][^"\']{4,}["\']',
             "Hardcoded secret/credential"),
        ]
        for i, line in enumerate(code.split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue
            for pattern, title in patterns:
                if re.search(pattern, line):
                    issues.append(ASTIssue(
                        line_start=i, line_end=i,
                        severity="critical", category="security",
                        title=title,
                        description="Credentials or secrets are hardcoded in source code. "
                                    "This is a major security risk if the code is committed to version control.",
                        suggestion="Use environment variables or a secrets manager.",
                        rule_id="AST-HARDCODED-SECRET",
                    ))
        return issues


def get_analyzer(language: str) -> Optional[PythonASTAnalyzer]:
    """Return the appropriate AST analyzer for the given language."""
    if language in ("python", "py"):
        return PythonASTAnalyzer()
    # Extensible: add JavaScriptASTAnalyzer, etc.
    return None
