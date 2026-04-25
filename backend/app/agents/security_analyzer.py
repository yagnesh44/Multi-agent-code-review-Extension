"""Security Analyzer Agent — finds OWASP/CWE vulnerabilities."""

from app.agents.base import BaseReviewAgent
from app.api.schemas import Category
from app.llm.prompts import SECURITY_ANALYZER_FEW_SHOT, SECURITY_ANALYZER_SYSTEM


class SecurityAnalyzerAgent(BaseReviewAgent):
    name = "security_analyzer"
    category = Category.SECURITY
    system_prompt = SECURITY_ANALYZER_SYSTEM
    few_shot = SECURITY_ANALYZER_FEW_SHOT
