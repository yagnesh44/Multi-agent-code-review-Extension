"""Base agent class for all review agents."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from app.api.schemas import Category, ReviewFinding, Severity
from app.config import settings
from app.llm.hf_client import HuggingFaceClient
from app.llm.prompts import build_review_prompt

logger = logging.getLogger(__name__)


class BaseReviewAgent(ABC):
    """Abstract base for specialized review agents.

    Each agent has:
    - A system prompt with domain expertise
    - Few-shot examples
    - A category it specialises in
    - Chain-of-thought + JSON output pipeline
    """

    name: str = "base"
    category: Category = Category.BUG
    system_prompt: str = ""
    few_shot: str = ""

    def __init__(self, llm: HuggingFaceClient):
        self.llm = llm

    async def review(
        self,
        code: str,
        filename: str,
        language: str,
        rag_context: str = "",
    ) -> list[ReviewFinding]:
        """Run the agent and return findings, with per-agent timeout."""
        start = time.monotonic()
        prompt = self._build_prompt(code, filename, language, rag_context)
        system = self.system_prompt
        if self.few_shot:
            system = system + "\n\n" + self.few_shot

        try:
            result = await asyncio.wait_for(
                self.llm.generate_json(prompt=prompt, system=system),
                timeout=settings.agent_timeout_seconds,
            )
            findings = self._parse_findings(result)
            elapsed = time.monotonic() - start
            logger.info(
                "Agent %s produced %d findings in %.1fs",
                self.name, len(findings), elapsed,
            )
            return findings
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            logger.error("Agent %s timed out after %.1fs", self.name, elapsed)
            return []
        except Exception as exc:
            logger.error("Agent %s failed: %s", self.name, exc)
            return []

    def _build_prompt(
        self, code: str, filename: str, language: str, rag_context: str
    ) -> str:
        return build_review_prompt(code, filename, language, rag_context)

    def _parse_findings(self, raw: Any) -> list[ReviewFinding]:
        """Parse the JSON output into validated ReviewFinding objects.
        
        Applies strict validation:
        - Rejects findings outside this agent's category domain
        - Rejects findings with confidence below threshold
        - Clamps line numbers to valid range
        """
        findings_raw = raw if isinstance(raw, list) else raw.get("findings", [])
        findings: list[ReviewFinding] = []
        for f in findings_raw:
            try:
                # Skip low-confidence findings
                conf = float(f.get("confidence", 0.5))
                if conf < 0.4:
                    logger.debug(
                        "Agent %s: skipping low-confidence finding (%.2f): %s",
                        self.name, conf, f.get("title", "?")[:60],
                    )
                    continue

                # Enforce category domain — reject out-of-scope findings
                raw_category = f.get("category", self.category.value)
                category = self._normalise_category(raw_category)
                title = f.get("title", "")
                description = f.get("description", "")
                if not self._is_in_domain(category, title, description):
                    logger.debug(
                        "Agent %s: rejecting out-of-domain finding (category=%s): %s",
                        self.name, raw_category, f.get("title", "?")[:60],
                    )
                    continue

                # Validate line numbers
                line_start = max(1, int(f.get("line_start", 1)))
                line_end = max(line_start, int(f.get("line_end", line_start)))

                finding = ReviewFinding(
                    line_start=line_start,
                    line_end=line_end,
                    severity=self._normalise_severity(f.get("severity", "medium")),
                    category=category,
                    title=f.get("title", "Untitled finding"),
                    description=f.get("description", ""),
                    suggestion=f.get("suggestion", ""),
                    suggested_code=f.get("suggested_code"),
                    confidence=max(0.0, min(1.0, conf)),
                    agent=self.name,
                    cwe_id=f.get("cwe_id"),
                    rule_id=f.get("rule_id"),
                )
                findings.append(finding)
            except Exception as exc:
                logger.warning("Skipping malformed finding from %s: %s", self.name, exc)
        return findings

    # Keywords that indicate a finding belongs to a specific domain
    _SECURITY_WORDS = frozenset({
        "sql injection", "sqli", "xss", "cross-site", "command injection",
        "os.system", "subprocess", "path traversal", "directory traversal",
        "deserialization", "pickle", "eval(", "exec(", "hardcoded secret",
        "hardcoded password", "credential", "cwe-", "csrf", "ssrf",
        "injection vulnerability", "rce", "remote code", "cryptographic",
        "md5", "sha1", "insecure hash",
    })
    _PERF_WORDS = frozenset({
        "o(n²)", "o(n³)", "o(n^2)", "o(n^3)", "n+1 query", "n+1 problem",
        "quadratic", "cubic", "exponential complexity",
        "string concatenation in loop", "inefficient algorithm",
    })

    def _is_in_domain(self, category: Category, title: str = "", description: str = "") -> bool:
        """Check if a finding's category and content belong to this agent's domain.
        
        Uses both the declared category AND content keywords to catch
        misclassified findings (e.g. bug_detector reporting SQL injection).
        """
        # Each agent has a primary category and acceptable neighbours
        domain_map: dict[Category, set[Category]] = {
            Category.BUG: {Category.BUG, Category.BEST_PRACTICE},
            Category.SECURITY: {Category.SECURITY},
            Category.PERFORMANCE: {Category.PERFORMANCE},
            Category.STYLE: {Category.STYLE, Category.BEST_PRACTICE},
        }
        allowed = domain_map.get(self.category, {self.category})
        if category not in allowed:
            return False

        # Content-based check: reject if the text clearly belongs elsewhere
        combined = (title + " " + description).lower()
        if self.category != Category.SECURITY:
            if any(kw in combined for kw in self._SECURITY_WORDS):
                logger.debug(
                    "Agent %s: rejecting security-domain finding by content: %s",
                    self.name, title[:60],
                )
                return False
        if self.category != Category.PERFORMANCE:
            if any(kw in combined for kw in self._PERF_WORDS):
                logger.debug(
                    "Agent %s: rejecting perf-domain finding by content: %s",
                    self.name, title[:60],
                )
                return False
        return True

    @staticmethod
    def _normalise_severity(val: str) -> Severity:
        try:
            return Severity(val.lower())
        except ValueError:
            return Severity.MEDIUM

    @staticmethod
    def _normalise_category(val: str) -> Category:
        try:
            return Category(val.lower())
        except ValueError:
            return Category.BUG
