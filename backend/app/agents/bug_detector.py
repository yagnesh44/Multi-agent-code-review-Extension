"""Bug Detector Agent — finds logical errors, runtime exceptions, and correctness issues."""

from app.agents.base import BaseReviewAgent
from app.api.schemas import Category
from app.llm.prompts import BUG_DETECTOR_FEW_SHOT, BUG_DETECTOR_SYSTEM


class BugDetectorAgent(BaseReviewAgent):
    name = "bug_detector"
    category = Category.BUG
    system_prompt = BUG_DETECTOR_SYSTEM
    few_shot = BUG_DETECTOR_FEW_SHOT
