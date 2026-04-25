"""Style Checker Agent — reviews code style, naming, and best practices."""

from app.agents.base import BaseReviewAgent
from app.api.schemas import Category
from app.llm.prompts import STYLE_CHECKER_FEW_SHOT, STYLE_CHECKER_SYSTEM


class StyleCheckerAgent(BaseReviewAgent):
    name = "style_checker"
    category = Category.STYLE
    system_prompt = STYLE_CHECKER_SYSTEM
    few_shot = STYLE_CHECKER_FEW_SHOT
