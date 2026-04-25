from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Category(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BEST_PRACTICE = "best_practice"


# ── Core Review Models ─────────────────────────────────────────────────────────

class ReviewFinding(BaseModel):
    line_start: int
    line_end: int
    severity: Severity
    category: Category
    title: str
    description: str
    suggestion: str
    suggested_code: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, description="Calibrated confidence 0-1")
    agent: str
    cwe_id: Optional[str] = None
    rule_id: Optional[str] = None


class ReviewSummary(BaseModel):
    total_issues: int
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0
    overall_quality_score: float = Field(ge=0.0, le=100.0)
    review_time_seconds: float
    estimated_human_review_minutes: float
    time_savings_percent: float


class CodeMetrics(BaseModel):
    lines_of_code: int
    lines_analyzed: int
    cyclomatic_complexity: Optional[float] = None
    cognitive_complexity: Optional[float] = None
    maintainability_index: Optional[float] = None
    halstead_volume: Optional[float] = None
    function_count: int = 0
    class_count: int = 0
    max_nesting_depth: int = 0


class ReviewRequest(BaseModel):
    code: str
    filename: str
    language: Optional[str] = None
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    diff_mode: bool = False
    agents: Optional[list[str]] = None  # Subset of agents to run


class ReviewResponse(BaseModel):
    findings: list[ReviewFinding]
    summary: ReviewSummary
    metrics: CodeMetrics
    agents_used: list[str]
    failed_agents: Optional[list[str]] = None
    partial_review: bool = False
    model_used: str


# ── Benchmark Models ───────────────────────────────────────────────────────────

class AnnotatedIssue(BaseModel):
    """Ground-truth issue for benchmarking."""
    line_start: int
    line_end: int
    severity: Severity
    category: Category
    title: str
    cwe_id: Optional[str] = None


class BenchmarkSample(BaseModel):
    code: str
    filename: str
    language: str
    annotations: list[AnnotatedIssue]


class BenchmarkRequest(BaseModel):
    dataset: str  # name or path


class BenchmarkResult(BaseModel):
    dataset: str
    samples_evaluated: int
    precision: float
    recall: float
    f1_score: float
    severity_accuracy: float
    category_accuracy: float
    mean_confidence: float
    true_positives: int
    false_positives: int
    false_negatives: int
    avg_review_time_seconds: float
    estimated_human_time_seconds: float
    time_savings_percent: float
    per_category: dict[str, dict[str, float]]
    details: list[dict]


# ── Health / Misc ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    llm_connected: bool
    models_available: list[str]
    active_model: str
