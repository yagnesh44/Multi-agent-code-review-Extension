"""Benchmark reporter — generates human-readable and machine-readable reports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.api.schemas import BenchmarkResult


def generate_text_report(result: BenchmarkResult) -> str:
    """Generate a formatted text report for console/log output."""
    lines = [
        "=" * 70,
        "  AI CODE REVIEW AGENT — BENCHMARK REPORT",
        f"  Dataset: {result.dataset}  |  Samples: {result.samples_evaluated}",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        "── OVERALL METRICS ──────────────────────────────────────────────────",
        f"  Precision:          {result.precision:.2%}",
        f"  Recall:             {result.recall:.2%}",
        f"  F1 Score:           {result.f1_score:.2%}",
        f"  Severity Accuracy:  {result.severity_accuracy:.2%}",
        f"  Category Accuracy:  {result.category_accuracy:.2%}",
        f"  Mean Confidence:    {result.mean_confidence:.2%}",
        "",
        "── DETECTION COUNTS ─────────────────────────────────────────────────",
        f"  True Positives:     {result.true_positives}",
        f"  False Positives:    {result.false_positives}",
        f"  False Negatives:    {result.false_negatives}",
        "",
        "── TIME COMPARISON ──────────────────────────────────────────────────",
        f"  Avg AI Review Time:      {result.avg_review_time_seconds:.1f}s",
        f"  Est. Human Review Time:  {result.estimated_human_time_seconds:.0f}s "
        f"({result.estimated_human_time_seconds / 60:.1f} min)",
        f"  Time Savings:            {result.time_savings_percent:.1f}%",
        "",
    ]

    if result.per_category:
        lines.append("── PER-CATEGORY BREAKDOWN ───────────────────────────────────────────")
        lines.append(f"  {'Category':<18} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        lines.append("  " + "-" * 48)
        for cat, m in sorted(result.per_category.items()):
            lines.append(
                f"  {cat:<18} {m['precision']:>10.2%} {m['recall']:>10.2%} {m['f1']:>10.2%}"
            )
        lines.append("")

    if result.details:
        lines.append("── PER-SAMPLE DETAILS ───────────────────────────────────────────────")
        for d in result.details:
            lines.append(
                f"  {d['filename']:<30} TP={d['tp']} FP={d['fp']} FN={d['fn']}  "
                f"P={d['precision']:.0%} R={d['recall']:.0%} "
                f"Score={d['quality_score']:.0f}"
            )
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def save_json_report(result: BenchmarkResult, output_dir: str = "./data/reports"):
    """Save the benchmark result as a timestamped JSON file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path(output_dir) / f"benchmark_{result.dataset}_{ts}.json"
    with open(path, "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    return str(path)
