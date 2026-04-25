"""Benchmark evaluator — runs the review pipeline against annotated datasets
and computes quantified metrics to prove AI review quality vs human review."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from app.agents.orchestrator import Orchestrator
from app.api.schemas import (
    AnnotatedIssue,
    BenchmarkResult,
    BenchmarkSample,
    ReviewRequest,
)
from app.benchmark.metrics import (
    category_accuracy,
    f1_score,
    match_findings,
    per_category_metrics,
    precision,
    recall,
    severity_accuracy,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Estimated human review time: 2.5 lines/minute for thorough review
_HUMAN_LINES_PER_MINUTE = 2.5


class BenchmarkEvaluator:
    """Evaluates the code review system against ground-truth datasets."""

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator
        self.dataset_dir = Path(settings.benchmark_dataset_dir)

    def load_dataset(self, name: str) -> list[BenchmarkSample]:
        """Load a benchmark dataset from JSON."""
        path = self.dataset_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")
        with open(path) as f:
            raw = json.load(f)
        samples = []
        for entry in raw:
            annotations = [AnnotatedIssue(**a) for a in entry["annotations"]]
            samples.append(BenchmarkSample(
                code=entry["code"],
                filename=entry["filename"],
                language=entry["language"],
                annotations=annotations,
            ))
        return samples

    async def evaluate(self, dataset_name: str) -> BenchmarkResult:
        """Run full evaluation on a dataset."""
        samples = self.load_dataset(dataset_name)
        logger.info("Evaluating dataset '%s' with %d samples", dataset_name, len(samples))

        all_tp, all_fp, all_fn = 0, 0, 0
        all_confidences: list[float] = []
        all_review_times: list[float] = []
        all_human_times: list[float] = []
        all_details: list[dict] = []
        all_sev_correct, all_sev_total = 0, 0
        all_cat_correct, all_cat_total = 0, 0
        all_per_cat: dict[str, dict[str, list[float]]] = {}

        for i, sample in enumerate(samples):
            logger.info("  Sample %d/%d: %s", i + 1, len(samples), sample.filename)
            start = time.monotonic()

            request = ReviewRequest(
                code=sample.code,
                filename=sample.filename,
                language=sample.language,
            )
            response = await self.orchestrator.review(request)
            review_time = time.monotonic() - start

            # Match predictions to ground truth
            match = match_findings(response.findings, sample.annotations)

            tp = len(match.true_positives)
            fp = len(match.false_positives)
            fn = len(match.false_negatives)

            all_tp += tp
            all_fp += fp
            all_fn += fn
            all_review_times.append(review_time)

            loc = len(sample.code.split("\n"))
            human_time = loc / _HUMAN_LINES_PER_MINUTE * 60  # seconds
            all_human_times.append(human_time)

            # Confidence of matched predictions
            for pred, _ in match.true_positives:
                all_confidences.append(pred.confidence)

            # Severity accuracy
            sev_correct = sum(
                1 for pred, gt in match.true_positives
                if pred.severity.value == gt.severity.value
            )
            all_sev_correct += sev_correct
            all_sev_total += tp

            # Category accuracy (should be 100% since match requires category match)
            cat_correct = sum(
                1 for pred, gt in match.true_positives
                if pred.category.value == gt.category.value
            )
            all_cat_correct += cat_correct
            all_cat_total += tp

            # Per-category metrics
            pcat = per_category_metrics(match)
            for cat, m in pcat.items():
                if cat not in all_per_cat:
                    all_per_cat[cat] = {"precision": [], "recall": [], "f1": []}
                for k in ("precision", "recall", "f1"):
                    all_per_cat[cat][k].append(m[k])

            all_details.append({
                "filename": sample.filename,
                "tp": tp, "fp": fp, "fn": fn,
                "precision": round(tp / (tp + fp), 4) if (tp + fp) > 0 else 1.0,
                "recall": round(tp / (tp + fn), 4) if (tp + fn) > 0 else 1.0,
                "review_time_seconds": round(review_time, 2),
                "quality_score": response.summary.overall_quality_score,
            })

        # Aggregate
        total_p = all_tp / (all_tp + all_fp) if (all_tp + all_fp) > 0 else 1.0
        total_r = all_tp / (all_tp + all_fn) if (all_tp + all_fn) > 0 else 1.0
        total_f1 = 2 * total_p * total_r / (total_p + total_r) if (total_p + total_r) > 0 else 0.0

        avg_review = sum(all_review_times) / len(all_review_times) if all_review_times else 0
        avg_human = sum(all_human_times) / len(all_human_times) if all_human_times else 0
        savings = (1 - avg_review / avg_human) * 100 if avg_human > 0 else 0

        sev_acc = all_sev_correct / all_sev_total if all_sev_total > 0 else 0
        cat_acc = all_cat_correct / all_cat_total if all_cat_total > 0 else 0
        mean_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0

        # Average per-category metrics
        per_cat_avg = {}
        for cat, metrics_lists in all_per_cat.items():
            per_cat_avg[cat] = {
                k: round(sum(v) / len(v), 4) if v else 0.0
                for k, v in metrics_lists.items()
            }

        return BenchmarkResult(
            dataset=dataset_name,
            samples_evaluated=len(samples),
            precision=round(total_p, 4),
            recall=round(total_r, 4),
            f1_score=round(total_f1, 4),
            severity_accuracy=round(sev_acc, 4),
            category_accuracy=round(cat_acc, 4),
            mean_confidence=round(mean_conf, 4),
            true_positives=all_tp,
            false_positives=all_fp,
            false_negatives=all_fn,
            avg_review_time_seconds=round(avg_review, 2),
            estimated_human_time_seconds=round(avg_human, 2),
            time_savings_percent=round(savings, 1),
            per_category=per_cat_avg,
            details=all_details,
        )
