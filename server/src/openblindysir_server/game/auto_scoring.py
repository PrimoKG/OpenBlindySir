"""Bounded, deterministic matching of several references inside one free-text answer.

References and rules are frozen at playback; evidence stays host-only until reveal.
No correctness feedback is sent in answer acknowledgements. No network/AI is used.
"""

import bisect
import re
import unicodedata
from dataclasses import replace
from itertools import product

from rapidfuzz.distance import DamerauLevenshtein

from openblindysir_protocol.enums import AnswerStatus
from openblindysir_server.game.state import AutoMatch, Metadata, Round, SessionState, Settings

FIELDS = ("title", "artist", "album", "year", "featuring")
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
ALTERNATIVES = re.compile(r"(?<!\S)(?:ou|or)(?!\S)", re.IGNORECASE)
FEATURE_MARKERS = {"ft", "feat", "featuring"}
MATCHER_VERSION = 1
MAX_DISTANCE_WORK = 2_000_000


def criteria(settings: Settings) -> list[str]:
    if settings.answer_mode == "fields":
        return list(settings.answer_fields)
    return {
        "title": ["title"],
        "artist": ["artist"],
        "both": ["title", "artist"],
        "custom": ["custom"],
    }[settings.answer_mode]


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if c.isalnum())


def _candidates(
    text: str, references: list[str], threshold: int, budget: list[int]
) -> tuple[list[tuple[float, int, int, str]], bool]:
    tokens = list(WORDS.finditer(text))
    parts = [normalize(token.group()) for token in tokens]
    compact = "".join(parts)
    ends = [0]
    for part in parts:
        ends.append(ends[-1] + len(part))
    matches: dict[tuple[int, int], tuple[float, int, int, str]] = {}
    # Exact matches are cheap and searched over the entire input, even if the fuzzy
    # work budget has been consumed by another criterion. Require token boundaries.
    unique = {normalize(reference): reference for reference in references if normalize(reference)}
    boundaries = set(ends)
    for expected, reference in unique.items():
        position = compact.find(expected)
        while position >= 0:
            end = position + len(expected)
            if position in boundaries and end in boundaries:
                start_index = bisect.bisect_right(ends, position) - 1
                end_index = bisect.bisect_left(ends, end) - 1
                key = (tokens[start_index].start(), tokens[end_index].end())
                matches[key] = (100, *key, reference)
                if len(matches) >= 8:
                    break
            position = compact.find(expected, position + 1)
    if matches:
        return sorted(matches.values(), key=lambda x: (x[2] - x[1], x[1]))[:8], False
    exhausted = False
    for reference in unique.values():
        expected = normalize(reference)
        if not expected:
            continue
        effective = 100 if len(expected) <= 3 else threshold
        # Include a ten-point review band; length bounds exclude impossible candidates.
        floor = max(1, effective - 10) / 100
        minimum = max(1, int(len(expected) * floor))
        maximum = int(len(expected) / floor)
        for start in range(len(tokens)):
            low = max(start + 1, bisect.bisect_left(ends, ends[start] + minimum))
            high = bisect.bisect_right(ends, ends[start] + maximum)
            for end in range(low, high):
                segment = compact[ends[start] : ends[end]]
                work = len(expected) * len(segment)
                if work > budget[0]:
                    exhausted = True
                    break
                budget[0] -= work
                similarity = 100 * DamerauLevenshtein.normalized_similarity(
                    expected, segment, score_cutoff=floor
                )
                key = (tokens[start].start(), tokens[end - 1].end())
                if similarity < floor * 100:
                    continue
                candidate = (similarity, *key, reference)
                if key not in matches or similarity > matches[key][0]:
                    matches[key] = candidate
            if exhausted:
                break
        if exhausted:
            break
    # Bounded evidence and work: pathological inputs stay for human review.
    return sorted(matches.values(), key=lambda x: (-x[0], x[2] - x[1], x[1]))[:8], exhausted


def _field_candidates(
    text: str, metadata: Metadata, settings: Settings
) -> tuple[dict[str, list[tuple[float, int, int, str]]], set[str]]:
    candidates = {}
    limited = set()
    budget = [MAX_DISTANCE_WORK]
    for key in criteria(settings):
        value = getattr(metadata, key, None)
        references = ([str(value)] if value is not None else []) + (metadata.aliases or {}).get(
            key, []
        )
        if key != "year":
            candidates[key], exhausted = _candidates(
                text, references, settings.acceptance_threshold, budget
            )
            if exhausted:
                limited.add(key)
    return candidates, limited


def _allocate(candidates: dict[str, list[tuple[float, int, int, str]]], threshold: int):
    """Choose compatible evidence together (at most 8**4 combinations)."""
    keys = [key for key, options in candidates.items() if options]
    references = {
        ref: normalize(ref) for options in candidates.values() for _, _, _, ref in options
    }
    best, best_rank = {}, (-1, -1, -1, -1.0)
    for combination in product(*(candidates[key] for key in keys)):
        collisions = {
            i
            for i, (_, start, end, ref) in enumerate(combination)
            for j, (_, left, right, other) in enumerate(combination)
            if i != j and start < right and end > left and references[ref] != references[other]
        }
        accepted = sum(
            score >= (100 if len(references[ref]) <= 3 else threshold)
            for i, (score, _, _, ref) in enumerate(combination)
            if i not in collisions
        )
        rank = (
            accepted,
            len(keys) - len(collisions),
            -len(collisions),
            sum(c[0] for c in combination),
        )
        if rank > best_rank:
            best, best_rank = dict(zip(keys, combination, strict=True)), rank
    return best


def _known_extras(
    words: list[str], metadata: Metadata, requested: list[str], feature_matched: bool
):
    """Cover extra words with complete known references; an ft prefix grants no exemption."""
    allowed = set()
    for key in FIELDS:
        if key in requested:
            continue
        value = getattr(metadata, key)
        refs = ([str(value)] if value is not None else []) + (metadata.aliases or {}).get(key, [])
        for reference in refs:
            normalized = normalize(reference)
            if normalized:
                allowed.add(normalized)
                if key == "featuring":
                    allowed.update(marker + normalized for marker in FEATURE_MARKERS)
    if feature_matched:
        allowed.update(FEATURE_MARKERS)
    # Only token boundaries may divide optional fields, just as for requested fields.
    reachable = {0}
    maximum = max(map(len, allowed), default=0)
    for start in range(len(words)):
        if start not in reachable:
            continue
        segment = ""
        for end in range(start, len(words)):
            segment += words[end]
            if len(segment) > maximum:
                break
            if segment in allowed:
                reachable.add(end + 1)
    return len(words) in reachable


def match_answer(text: str, metadata: Metadata, settings: Settings) -> list[AutoMatch]:
    text = text[:1500]
    result: list[AutoMatch] = []
    occupied: list[tuple[int, int, str, int]] = []
    candidates, limited = _field_candidates(text, metadata, settings)
    selected = _allocate(candidates, settings.acceptance_threshold)
    # Process textual evidence before years; unavoidable collisions require review.
    fields = sorted(
        criteria(settings),
        key=lambda key: -(candidates.get(key, [(0,)])[0][0] if candidates.get(key) else 0),
    )
    for key in fields:
        value = getattr(metadata, key, None)
        reference = str(value) if value is not None else None
        limit = (
            100
            if key == "year" or (reference and len(normalize(reference)) <= 3)
            else settings.acceptance_threshold
        )
        if value is None and not (metadata.aliases or {}).get(key):
            result.append(AutoMatch(key, None, None, 0, limit, "missing_reference"))
            continue
        if key == "year":
            years = {
                int(digits)
                for token in WORDS.finditer(text)
                if len(digits := normalize(token.group())) == 4
                and digits.isdecimal()
                and not any(
                    token.start() >= left
                    and token.end() <= right
                    and normalize(other) != str(value)
                    for left, right, other, _ in occupied
                )
            }
            correct = value in years
            status = (
                "ambiguous" if correct and len(years) > 1 else "matched" if correct else "not_found"
            )
            result.append(
                AutoMatch(
                    key,
                    reference,
                    reference if correct else None,
                    100 if correct else 0,
                    100,
                    status,
                )
            )
            continue
        options = candidates.get(key, [])
        if not options:
            result.append(
                AutoMatch(
                    key,
                    reference,
                    None,
                    0,
                    limit,
                    "complex_answer" if key in limited else "not_found",
                )
            )
            continue
        score, start, end, reference = selected[key]
        limit = 100 if len(normalize(reference)) <= 3 else settings.acceptance_threshold
        status = (
            "complex_answer"
            if key in limited
            else "matched"
            if score >= limit
            else "near_threshold"
        )
        for left, right, other, index in occupied:
            if start < right and end > left and normalize(other) != normalize(reference):
                status = "ambiguous"
                result[index] = replace(result[index], status="ambiguous")
        result.append(AutoMatch(key, reference, text[start:end], round(score, 3), limit, status))
        occupied.append((start, end, reference, len(result) - 1))
    # Explicit lists of alternatives cannot win by containing the expected answer somewhere.
    if any(
        not any(mark.start() >= left and mark.end() <= right for left, right, _, _ in occupied)
        for mark in ALTERNATIVES.finditer(text)
    ):
        result = [
            replace(row, status="ambiguous") if row.status == "matched" else row for row in result
        ]
    # Unexplained words beside a successful match often indicate multiple artist/title guesses.
    # A featuring clause is legitimate extra information even when not requested.
    used = {(start, end) for start, end, _, _ in occupied}
    leftovers = [
        token
        for token in WORDS.finditer(text)
        if not any(token.start() >= left and token.end() <= right for left, right in used)
        and not (
            "year" in criteria(settings)
            and len(digits := normalize(token.group())) == 4
            and digits.isdecimal()
        )
    ]
    words = [normalize(token.group()) for token in leftovers]
    if (
        words
        and not any(row.criterion != "year" and row.status != "matched" for row in result)
        and not _known_extras(
            words,
            metadata,
            criteria(settings),
            any(row.criterion == "featuring" and row.status == "matched" for row in result),
        )
    ):
        result = [
            replace(row, status="ambiguous") if row.status == "matched" else row for row in result
        ]
    order = criteria(settings)
    return sorted(result, key=lambda row: order.index(row.criterion))


def grade_round(
    s: SessionState, r: Round, *, regrade: bool = False, only: set[str] | None = None
) -> None:
    cfg = r.auto_config
    if cfg is None or cfg.scoring_mode != "auto" or cfg.answer_mode == "custom" or not r.included:
        return
    ids = r.participant_ids | set(r.answers)
    if only is not None:
        ids &= only
    for pid in ids:
        if (
            pid not in s.players
            or pid in r.auto_overrides
            or (pid in r.auto_evidence and not regrade)
        ):
            continue
        answer = r.answers.get(pid)
        text = answer.text if answer else None
        evidence = match_answer(text or "", r.auto_reference or Metadata(), cfg)
        zero = not text or (
            answer is not None
            and answer.status is AnswerStatus.CAPTURED
            and cfg.captured_policy == "zero"
        )
        manual_draft = (
            bool(text)
            and answer is not None
            and answer.status is AnswerStatus.CAPTURED
            and cfg.captured_policy == "manual"
        )
        decisions = {
            f"{row.criterion}_correct": False
            if zero
            else None
            if manual_draft
            else True
            if row.status == "matched"
            else None
            if row.status in {"missing_reference", "ambiguous", "near_threshold", "complex_answer"}
            else False
            for row in evidence
        }
        points = sum(
            getattr(cfg, f"{key.removesuffix('_correct')}_points")
            for key, accepted in decisions.items()
            if accepted is True
        )
        r.auto_evidence[pid] = evidence
        r.judgements[pid] = decisions
        r.score_revisions[pid] = r.score_revisions.get(pid, 0) + 1
        if all(value is not None for value in decisions.values()):
            r.score_reviewed.add(pid)
        else:
            r.score_reviewed.discard(pid)
        if points:
            r.score_draft[pid] = points
        else:
            r.score_draft.pop(pid, None)
    s.touched = True
