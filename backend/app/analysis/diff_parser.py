"""Git diff parser – extracts changed hunks so the review agent can focus
on modified lines only (incremental review)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class DiffHunk:
    filename: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: list[tuple[int, str]]     # (line_no, content)
    removed_lines: list[tuple[int, str]]
    context_lines: list[tuple[int, str]]
    raw: str


def parse_unified_diff(diff_text: str) -> list[DiffHunk]:
    """Parse a unified diff string into structured hunks."""
    hunks: list[DiffHunk] = []
    current_file = ""
    current_hunk_lines: list[str] = []
    hunk_header = None

    file_re = re.compile(r"^(?:---|\+\+\+)\s+(?:a/|b/)?(.*)")
    hunk_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    def flush_hunk():
        nonlocal current_hunk_lines, hunk_header
        if hunk_header is None:
            return
        m = hunk_header
        added, removed, context = [], [], []
        new_line = int(m.group(3))
        old_line = int(m.group(1))
        for line in current_hunk_lines:
            if line.startswith("+"):
                added.append((new_line, line[1:]))
                new_line += 1
            elif line.startswith("-"):
                removed.append((old_line, line[1:]))
                old_line += 1
            else:
                context.append((new_line, line[1:] if line.startswith(" ") else line))
                new_line += 1
                old_line += 1
        hunks.append(DiffHunk(
            filename=current_file,
            old_start=int(m.group(1)),
            old_count=int(m.group(2) or 1),
            new_start=int(m.group(3)),
            new_count=int(m.group(4) or 1),
            added_lines=added,
            removed_lines=removed,
            context_lines=context,
            raw="\n".join(current_hunk_lines),
        ))
        current_hunk_lines = []
        hunk_header = None

    for line in diff_text.splitlines():
        fm = file_re.match(line)
        if fm and line.startswith("+++"):
            current_file = fm.group(1)
            continue
        if line.startswith("---"):
            continue

        hm = hunk_re.match(line)
        if hm:
            flush_hunk()
            hunk_header = hm
            continue

        if hunk_header is not None:
            current_hunk_lines.append(line)

    flush_hunk()
    return hunks


def changed_line_ranges(hunks: list[DiffHunk]) -> dict[str, list[tuple[int, int]]]:
    """Return a mapping of filename → list of (start, end) line ranges that were changed."""
    result: dict[str, list[tuple[int, int]]] = {}
    for hunk in hunks:
        if not hunk.added_lines:
            continue
        fname = hunk.filename
        if fname not in result:
            result[fname] = []
        lines = sorted(ln for ln, _ in hunk.added_lines)
        # Merge consecutive lines into ranges
        start = lines[0]
        end = lines[0]
        for ln in lines[1:]:
            if ln == end + 1:
                end = ln
            else:
                result[fname].append((start, end))
                start = ln
                end = ln
        result[fname].append((start, end))
    return result
