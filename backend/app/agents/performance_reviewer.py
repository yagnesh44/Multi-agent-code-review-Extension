"""Performance Reviewer Agent — finds bottlenecks and inefficient patterns."""

from app.agents.base import BaseReviewAgent
from app.api.schemas import Category
from app.llm.prompts import PERFORMANCE_REVIEWER_FEW_SHOT, PERFORMANCE_REVIEWER_SYSTEM


class PerformanceReviewerAgent(BaseReviewAgent):
    name = "performance_reviewer"
    category = Category.PERFORMANCE
    system_prompt = PERFORMANCE_REVIEWER_SYSTEM
    few_shot = PERFORMANCE_REVIEWER_FEW_SHOT
