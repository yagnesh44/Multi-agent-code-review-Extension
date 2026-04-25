"""Benchmark metrics — precision, recall, F1, severity accuracy, and time savings."""

from __future__ import annotations

from dataclasses import dataclass

from app.api.schemas import AnnotatedIssue, Category, ReviewFinding, Severity


@dataclass
class MatchResult:
    true_positives: list[tuple[ReviewFinding, AnnotatedIssue]]
    false_positives: list[ReviewFinding]
    false_negatives: list[AnnotatedIssue]


def match_findings(
    predicted: list[ReviewFinding],
    ground_truth: list[AnnotatedIssue],
    line_tolerance: int = 3,
) -> MatchResult:
    """Match predicted findings to ground-truth annotations.

    A prediction matches a ground-truth if:
    - Their line ranges overlap (within tolerance)
    - Their categories match
    """
    matched_gt: set[int] = set()
    tp: list[tuple[ReviewFinding, AnnotatedIssue]] = []
    fp: list[ReviewFinding] = []

    for pred in predicted:
        best_match = None
        best_overlap = 0
        for i, gt in enumerate(ground_truth):
            if i in matched_gt:
                continue
            # Check category match
            if pred.category.value != gt.category.value:
                continue
            # Check line overlap with tolerance
            pred_range = set(range(pred.line_start - line_tolerance,
                                   pred.line_end + line_tolerance + 1))
            gt_range = set(range(gt.line_start, gt.line_end + 1))
            overlap = len(pred_range & gt_range)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = i

        if best_match is not None and best_overlap > 0:
            tp.append((pred, ground_truth[best_match]))
            matched_gt.add(best_match)
        else:
            fp.append(pred)

    fn = [gt for i, gt in enumerate(ground_truth) if i not in matched_gt]
    return MatchResult(true_positives=tp, false_positives=fp, false_negatives=fn)


def precision(match: MatchResult) -> float:
    tp = len(match.true_positives)
    fp = len(match.false_positives)
    return tp / (tp + fp) if (tp + fp) > 0 else 1.0


def recall(match: MatchResult) -> float:
    tp = len(match.true_positives)
    fn = len(match.false_negatives)
    return tp / (tp + fn) if (tp + fn) > 0 else 1.0


def f1_score(match: MatchResult) -> float:
    p = precision(match)
    r = recall(match)
    return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def severity_accuracy(match: MatchResult) -> float:
    """Fraction of true positives where predicted severity matches ground truth."""
    if not match.true_positives:
        return 0.0
    correct = sum(
        1 for pred, gt in match.true_positives
        if pred.severity.value == gt.severity.value
    )
    return correct / len(match.true_positives)


def category_accuracy(match: MatchResult) -> float:
    """Fraction of true positives where predicted category matches ground truth."""
    if not match.true_positives:
        return 0.0
    correct = sum(
        1 for pred, gt in match.true_positives
        if pred.category.value == gt.category.value
    )
    return correct / len(match.true_positives)


def per_category_metrics(match: MatchResult) -> dict[str, dict[str, float]]:
    """Compute precision/recall/F1 broken down by category."""
    categories = set()
    for _, gt in match.true_positives:
        categories.add(gt.category.value)
    for fp in match.false_positives:
        categories.add(fp.category.value)
    for fn in match.false_negatives:
        categories.add(fn.category.value)

    result = {}
    for cat in categories:
        cat_tp = [(p, g) for p, g in match.true_positives if g.category.value == cat]
        cat_fp = [p for p in match.false_positives if p.category.value == cat]
        cat_fn = [g for g in match.false_negatives if g.category.value == cat]

        tp_count = len(cat_tp)
        fp_count = len(cat_fp)
        fn_count = len(cat_fn)

        p = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 1.0
        r = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 1.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

        result[cat] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}
    return result
