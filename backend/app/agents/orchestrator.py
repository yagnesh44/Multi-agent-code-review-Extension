"""Orchestrator — coordinates multiple review agents and merges results.

Pipeline:
1. Detect language
2. Run AST-based static analysis (deterministic, instant)
3. Compute complexity metrics
4. Retrieve RAG context for the code patterns
5. Fan-out to all LLM agents concurrently
6. Merge findings: deduplicate, boost confidence on consensus, calibrate severity
7. Compute summary and quality score
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from difflib import SequenceMatcher
from typing import Optional

from app.agents.base import BaseReviewAgent
from app.agents.bug_detector import BugDetectorAgent
from app.agents.performance_reviewer import PerformanceReviewerAgent
from app.agents.security_analyzer import SecurityAnalyzerAgent
from app.agents.style_checker import StyleCheckerAgent
from app.analysis.ast_analyzer import ASTIssue, get_analyzer
from app.analysis.complexity import compute_complexity
from app.api.schemas import (
    Category,
    CodeMetrics,
    ReviewFinding,
    ReviewRequest,
    ReviewResponse,
    ReviewSummary,
    Severity,
)
from app.config import settings
from app.llm.hf_client import HuggingFaceClient
from app.llm.prompts import VERIFICATION_SYSTEM, build_verification_prompt

logger = logging.getLogger(__name__)

# Language detection by file extension
_EXT_MAP = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java", ".kt": "kotlin",
    ".go": "go", ".rs": "rust",
    ".c": "c", ".cpp": "cpp", ".h": "cpp",
    ".cs": "csharp", ".rb": "ruby", ".php": "php",
    ".swift": "swift", ".scala": "scala",
    ".sh": "bash", ".bash": "bash",
}

# Estimated human review speed: ~150 lines per hour for thorough review
_HUMAN_LINES_PER_MINUTE = 2.5


class Orchestrator:
    """Central coordinator for the code review pipeline."""

    def __init__(self, llm: Optional[HuggingFaceClient] = None):
        self.llm = llm or HuggingFaceClient()
        self._agents: list[BaseReviewAgent] = [
            BugDetectorAgent(self.llm),
            SecurityAnalyzerAgent(self.llm),
            PerformanceReviewerAgent(self.llm),
            StyleCheckerAgent(self.llm),
        ]
        self._rag_retriever = None  # Lazy-loaded

    async def set_rag_retriever(self, retriever):
        self._rag_retriever = retriever

    def detect_language(self, filename: str, hint: Optional[str] = None) -> str:
        if hint:
            return hint
        _, ext = os.path.splitext(filename)
        return _EXT_MAP.get(ext.lower(), "unknown")

    async def review(self, request: ReviewRequest) -> ReviewResponse:
        start = time.monotonic()
        language = self.detect_language(request.filename, request.language)
        code = request.code
        lines = code.split("\n")
        loc = len(lines)
        failed_agents: list[str] = []

        # ── 1. AST-based static analysis ──────────────────────────────────
        ast_findings: list[ReviewFinding] = []
        ast_analyzer = get_analyzer(language)
        ast_metrics = None
        if ast_analyzer:
            ast_issues, ast_metrics = ast_analyzer.analyze(code, request.filename)
            ast_findings = [self._ast_to_finding(issue) for issue in ast_issues]
            logger.info("AST analysis: %d findings", len(ast_findings))

        # ── 2. Complexity metrics ─────────────────────────────────────────
        complexity = None
        if language == "python":
            try:
                complexity = compute_complexity(code)
            except Exception as exc:
                logger.warning("Complexity analysis failed: %s", exc)

        # ── 3. RAG context retrieval ──────────────────────────────────────
        rag_context = ""
        if self._rag_retriever:
            try:
                rag_context = await self._rag_retriever.retrieve_context(code, language)
            except Exception as exc:
                logger.warning("RAG retrieval failed: %s", exc)

        # ── 4. Select agents to run ───────────────────────────────────────
        agents = self._agents
        if request.agents:
            agent_names = set(request.agents)
            agents = [a for a in self._agents if a.name in agent_names]

        # ── 5. Run LLM agents (staggered to respect rate limits) ─────────
        sem = asyncio.Semaphore(settings.concurrent_agents)
        _rate_delay = 3.0  # seconds between agent starts to avoid 429s

        async def _run_agent(agent: BaseReviewAgent, index: int) -> list[ReviewFinding]:
            if index > 0:
                await asyncio.sleep(index * _rate_delay)
            async with sem:
                return await agent.review(code, request.filename, language, rag_context)

        tasks = [_run_agent(agent, i) for i, agent in enumerate(agents)]
        try:
            agent_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=settings.agent_timeout_seconds + 30,  # overall buffer
            )
        except asyncio.TimeoutError:
            logger.error("Overall agent fan-out timed out")
            agent_results = []
            failed_agents = [a.name for a in agents]

        llm_findings: list[ReviewFinding] = []
        agents_used = []
        for agent, result in zip(agents, agent_results):
            if isinstance(result, Exception):
                logger.error("Agent %s raised: %s", agent.name, result)
                failed_agents.append(agent.name)
                continue
            llm_findings.extend(result)
            agents_used.append(agent.name)

        # ── 6. Validate, merge, and deduplicate ─────────────────────────
        all_findings = ast_findings + llm_findings
        # Validate line numbers are within file bounds
        all_findings = [
            f for f in all_findings
            if 1 <= f.line_start <= loc and f.line_end <= loc + 5
        ]
        merged = self._deduplicate(all_findings)
        merged = self._boost_consensus(merged)
        # Filter out low-confidence LLM findings (keep all AST findings)
        merged = [
            f for f in merged
            if f.agent == "ast_analyzer" or f.confidence >= 0.5
        ]
        # Remove findings where a non-specialist reported another domain's issue
        merged = self._filter_cross_domain(merged)
        # ── 6b. Verify findings with LLM (filter false positives) ────────
        llm_to_verify = [f for f in merged if f.agent != "ast_analyzer"]
        ast_only = [f for f in merged if f.agent == "ast_analyzer"]
        if llm_to_verify:
            # Brief pause to avoid rate limits after agent fan-out
            await asyncio.sleep(2.0)
            verified_llm = await self._verify_findings(
                code, request.language or "python", llm_to_verify
            )
            merged = ast_only + verified_llm
        merged.sort(key=lambda f: self._severity_rank(f.severity))

        # ── 7. Compute summary ────────────────────────────────────────────
        elapsed = time.monotonic() - start
        estimated_human_min = loc / _HUMAN_LINES_PER_MINUTE
        savings = max(0.0, (1 - elapsed / 60 / estimated_human_min) * 100) if estimated_human_min > 0 else 0

        sev_counts = {s: 0 for s in Severity}
        for f in merged:
            sev_counts[f.severity] += 1

        quality_score = self._compute_quality_score(merged, loc)

        summary = ReviewSummary(
            total_issues=len(merged),
            critical=sev_counts[Severity.CRITICAL],
            high=sev_counts[Severity.HIGH],
            medium=sev_counts[Severity.MEDIUM],
            low=sev_counts[Severity.LOW],
            info=sev_counts[Severity.INFO],
            overall_quality_score=round(quality_score, 1),
            review_time_seconds=round(elapsed, 2),
            estimated_human_review_minutes=round(estimated_human_min, 1),
            time_savings_percent=round(savings, 1),
        )

        metrics = CodeMetrics(
            lines_of_code=loc,
            lines_analyzed=loc,
            cyclomatic_complexity=complexity.cyclomatic if complexity else None,
            cognitive_complexity=complexity.cognitive if complexity else None,
            maintainability_index=complexity.maintainability_index if complexity else None,
            halstead_volume=complexity.halstead_volume if complexity else None,
            function_count=ast_metrics.function_count if ast_metrics else 0,
            class_count=ast_metrics.class_count if ast_metrics else 0,
            max_nesting_depth=ast_metrics.max_nesting if ast_metrics else 0,
        )

        return ReviewResponse(
            findings=merged,
            summary=summary,
            metrics=metrics,
            agents_used=["ast_analyzer"] + agents_used,
            failed_agents=failed_agents if failed_agents else None,
            partial_review=len(failed_agents) > 0,
            model_used=self.llm.active_model,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _ast_to_finding(issue: ASTIssue) -> ReviewFinding:
        return ReviewFinding(
            line_start=issue.line_start,
            line_end=issue.line_end,
            severity=Severity(issue.severity),
            category=Category(issue.category),
            title=issue.title,
            description=issue.description,
            suggestion=issue.suggestion,
            suggested_code=None,
            confidence=issue.confidence,
            agent="ast_analyzer",
            rule_id=issue.rule_id,
        )

    # ── Agent priority for deduplication ──────────────────────────────────
    # When the same issue is found by multiple agents, prefer the specialist.
    _AGENT_PRIORITY: dict[str, int] = {
        "ast_analyzer": 10,       # Deterministic, always highest priority
        "security_analyzer": 8,   # Best for security findings
        "bug_detector": 7,        # Best for logic/correctness bugs
        "performance_reviewer": 6, # Best for perf issues
        "style_checker": 5,       # Best for style/readability
    }

    # Keywords that identify a finding as belonging to a specific category,
    # regardless of what category the LLM assigned.
    _SECURITY_KEYWORDS = {
        "sql injection", "sqli", "xss", "command injection", "path traversal",
        "deserialization", "hardcoded", "credential", "secret", "cwe-",
        "csrf", "ssrf", "injection", "eval()", "pickle", "md5", "cryptographic",
    }
    _PERF_KEYWORDS = {
        "o(n²)", "o(n³)", "o(n^2)", "o(n^3)", "n+1", "complexity",
        "string concatenation in loop", "inefficient", "slow", "pagination",
        "caching", "memory",
    }

    @classmethod
    def _true_domain(cls, f: ReviewFinding) -> str:
        """Determine the true domain of a finding based on its content."""
        title_lower = f.title.lower()
        desc_lower = f.description.lower()
        combined = title_lower + " " + desc_lower

        if any(kw in combined for kw in cls._SECURITY_KEYWORDS):
            return "security"
        if any(kw in combined for kw in cls._PERF_KEYWORDS):
            return "performance"
        return f.category.value

    @classmethod
    def _filter_cross_domain(cls, findings: list[ReviewFinding]) -> list[ReviewFinding]:
        """Drop findings where a non-specialist agent wandered into another domain.

        e.g. performance_reviewer reporting SQL injection, bug_detector reporting XSS.
        Only removes when a specialist already covers that line.
        """
        _DOMAIN_AGENT = {
            "security": "security_analyzer",
            "performance": "performance_reviewer",
        }
        # Build a set of lines covered by each specialist
        specialist_lines: dict[str, set[int]] = {}
        for f in findings:
            true_d = cls._true_domain(f)
            expected_agent = _DOMAIN_AGENT.get(true_d)
            if expected_agent and f.agent == expected_agent:
                lines = set(range(f.line_start, f.line_end + 1))
                specialist_lines.setdefault(true_d, set()).update(lines)

        kept = []
        for f in findings:
            true_d = cls._true_domain(f)
            expected_agent = _DOMAIN_AGENT.get(true_d)
            if expected_agent and f.agent != expected_agent and f.agent != "ast_analyzer":
                # Non-specialist is reporting in another domain
                # Drop it if the specialist already covers nearby lines
                covered = specialist_lines.get(true_d, set())
                if any(ln in covered for ln in range(f.line_start, f.line_end + 1)):
                    logger.debug(
                        "Dropping cross-domain finding from %s: %s (should be %s)",
                        f.agent, f.title, expected_agent,
                    )
                    continue
            kept.append(f)
        return kept

    @classmethod
    def _deduplicate(cls, findings: list[ReviewFinding]) -> list[ReviewFinding]:
        """Remove duplicate findings using line overlap + content similarity.
        
        When the same issue is found by multiple agents, keeps the one from
        the most appropriate specialist agent.
        """
        if not findings:
            return findings

        kept: list[ReviewFinding] = []
        for f in findings:
            is_dup = False
            true_domain = cls._true_domain(f)

            for i, existing in enumerate(kept):
                # Check line overlap (within 3 lines)
                overlap = (
                    f.line_start <= existing.line_end + 3
                    and f.line_end >= existing.line_start - 3
                )
                if not overlap:
                    continue

                # Check title/content similarity
                similarity = SequenceMatcher(
                    None, f.title.lower(), existing.title.lower()
                ).ratio()

                # Same domain findings on overlapping lines
                same_domain = cls._true_domain(existing) == true_domain
                same_category = f.category == existing.category

                is_similar = (
                    similarity > 0.5
                    or (same_domain and abs(f.line_start - existing.line_start) <= 2)
                    or (same_category and abs(f.line_start - existing.line_start) <= 1)
                )

                if is_similar:
                    # Keep the better one: prefer specialist agent, then confidence
                    f_priority = cls._AGENT_PRIORITY.get(f.agent, 0)
                    ex_priority = cls._AGENT_PRIORITY.get(existing.agent, 0)

                    # Prefer the agent whose domain matches the finding's true domain
                    f_domain_match = (f.agent == "security_analyzer" and true_domain == "security") or \
                                     (f.agent == "bug_detector" and true_domain not in ("security", "performance")) or \
                                     (f.agent == "performance_reviewer" and true_domain == "performance") or \
                                     (f.agent == "ast_analyzer")
                    ex_domain_match = (existing.agent == "security_analyzer" and true_domain == "security") or \
                                      (existing.agent == "bug_detector" and true_domain not in ("security", "performance")) or \
                                      (existing.agent == "performance_reviewer" and true_domain == "performance") or \
                                      (existing.agent == "ast_analyzer")

                    replace = False
                    if f_domain_match and not ex_domain_match:
                        replace = True
                    elif ex_domain_match and not f_domain_match:
                        replace = False
                    elif f_priority > ex_priority:
                        replace = True
                    elif f_priority == ex_priority and f.confidence > existing.confidence:
                        replace = True

                    if replace:
                        kept[i] = f
                    is_dup = True
                    break

            if not is_dup:
                kept.append(f)
        return kept

    @staticmethod
    def _boost_consensus(findings: list[ReviewFinding]) -> list[ReviewFinding]:
        """If multiple agents flagged overlapping line ranges, boost confidence."""
        line_agents: dict[int, set[str]] = {}
        for f in findings:
            for ln in range(f.line_start, f.line_end + 1):
                line_agents.setdefault(ln, set()).add(f.agent)

        for f in findings:
            agents_on_lines = set()
            for ln in range(f.line_start, f.line_end + 1):
                agents_on_lines |= line_agents.get(ln, set())
            if len(agents_on_lines) > 1:
                boost = min(0.15, 0.05 * (len(agents_on_lines) - 1))
                f.confidence = min(1.0, f.confidence + boost)
        return findings

    @staticmethod
    def _severity_rank(severity: Severity) -> int:
        return {
            Severity.CRITICAL: 0, Severity.HIGH: 1,
            Severity.MEDIUM: 2, Severity.LOW: 3, Severity.INFO: 4,
        }.get(severity, 5)

    @staticmethod
    def _compute_quality_score(findings: list[ReviewFinding], loc: int) -> float:
        """Compute a 0-100 quality score, normalized by code size.

        Calibrated so:
        - Clean code → 100
        - 1 critical in 30 LOC → ~73
        - 1 critical + 1 high + 1 medium in 30 LOC → ~57
        - Heavily buggy code → 0-15
        """
        if not findings:
            return 100.0

        weights = {
            Severity.CRITICAL: 8.0, Severity.HIGH: 4.0,
            Severity.MEDIUM: 1.5, Severity.LOW: 0.3, Severity.INFO: 0.0,
        }

        weighted_issues = sum(
            weights.get(f.severity, 1.0) * f.confidence for f in findings
        )

        effective_loc = max(loc, 30)
        score = 100.0 * (1.0 - weighted_issues / effective_loc)

        return max(0.0, min(100.0, round(score, 1)))

    async def _verify_findings(
        self,
        code: str,
        language: str,
        findings: list[ReviewFinding],
    ) -> list[ReviewFinding]:
        """Use the LLM to verify each finding against the actual code.

        Returns only the findings the LLM confirms as true positives.
        Falls back to returning all findings if verification fails.
        """
        if not findings:
            return findings

        findings_dicts = [
            {
                "line_start": f.line_start,
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
            }
            for f in findings
        ]

        prompt = build_verification_prompt(code, language, findings_dicts)

        try:
            result = await asyncio.wait_for(
                self.llm.generate_json(
                    prompt=prompt,
                    system=VERIFICATION_SYSTEM,
                ),
                timeout=30,
            )

            # Parse the verified indices
            if isinstance(result, dict):
                verified_indices = result.get("verified", [])
            elif isinstance(result, list):
                verified_indices = result
            else:
                logger.warning("Verification returned unexpected type: %s", type(result))
                return findings

            # Validate indices
            verified = []
            for idx in verified_indices:
                try:
                    i = int(idx)
                    if 0 <= i < len(findings):
                        verified.append(findings[i])
                except (ValueError, TypeError):
                    continue

            removed = len(findings) - len(verified)
            if removed > 0:
                logger.info(
                    "Verification removed %d/%d false-positive findings",
                    removed, len(findings),
                )
            return verified

        except asyncio.TimeoutError:
            logger.warning("Verification timed out — keeping all findings")
            return findings
        except Exception as exc:
            logger.warning("Verification failed (%s) — keeping all findings", exc)
            return findings
