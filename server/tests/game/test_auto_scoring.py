"""Real engine rules and matcher regression cases; all references are synthetic fixtures."""

import random
from dataclasses import replace
from types import SimpleNamespace

import pytest
from builders import Scenario
from pydantic import ValidationError

from openblindysir_protocol.enums import GamePhase
from openblindysir_protocol.metadata import MusicalMetadata
from openblindysir_protocol.settings import SettingsPatch
from openblindysir_server.auth.sessions import SessionRegistry
from openblindysir_server.game import GameEngine, Instant, SecretIds, auto_scoring
from openblindysir_server.game.auto_scoring import match_answer
from openblindysir_server.game.state import Metadata, Settings, TrackRef
from openblindysir_server.persistence import SnapshotStore

REFERENCE = Metadata(
    title="Sapés comme jamais",
    artist="Maître Gims",
    album="Pilule bleue",
    year=2015,
    featuring="Niska",
)
RULES = Settings(
    answer_mode="fields", answer_fields=["title", "artist", "album", "year"], scoring_mode="auto"
)
EXAMPLE = "Sapéscomme Ja m ais Maitre Gims 2015 ft niska   pilule bleue"


def matched(text, metadata=REFERENCE, settings=RULES):
    return {row.criterion: row for row in match_answer(text, metadata, settings)}


@pytest.mark.parametrize(
    "answer",
    [
        EXAMPLE,
        "2015 PILULE BLEUE maître GIMS Sapés comme jamais",
        "Sapes comme jamias Maitre Gims Pilule bleue 2015",
    ],
)
def test_one_field_flexible_spaces_order_and_typo(answer):
    assert all(row.status == "matched" for row in matched(answer).values())


def test_default_threshold_is_per_criterion_and_year_is_exact():
    evidence = matched("Sapés comme jamias Maitre Gims Pilule bleue 2016")
    assert evidence["title"].similarity == 93.75
    assert evidence["title"].status == "matched"
    assert evidence["year"].status == "not_found"
    assert evidence["year"].threshold == 100
    strict = matched(
        "Sapés comme jamias Maitre Gims Pilule bleue 2015",
        settings=replace(RULES, acceptance_threshold=95),
    )
    assert strict["title"].status == "near_threshold"
    assert strict["artist"].status == "matched"


def test_missing_criterion_and_missing_reference_are_not_the_same():
    assert matched("Sapés comme jamais Maitre Gims 2015")["album"].status == "not_found"
    assert matched(EXAMPLE, replace(REFERENCE, album=None))["album"].status == "missing_reference"


def test_aliases_are_explicit_and_do_not_silently_change_reference():
    ref = replace(
        REFERENCE,
        artist="Another spelling",
        album="Canonical album",
        aliases={"artist": ["Maître Gims"], "album": ["Pilule bleue"]},
    )
    assert all(row.status == "matched" for row in matched(EXAMPLE, ref).values())
    assert matched(EXAMPLE, replace(ref, aliases=None))["album"].status != "matched"


@pytest.mark.parametrize("text", ["Air", "AIR"])
def test_short_references_are_exact(text):
    cfg = replace(RULES, answer_mode="title", acceptance_threshold=80)
    assert matched(text, Metadata(title="Air"), cfg)["title"].status == "matched"
    assert matched("Cairo", Metadata(title="Air"), cfg)["title"].status == "not_found"


def test_alternatives_and_conflicting_years_need_review():
    assert matched(EXAMPLE.replace("2015", "2015 2016"))["year"].status == "ambiguous"
    assert all(
        row.status != "matched" for row in matched(EXAMPLE + " ou une autre chanson").values()
    )
    assert (
        matched("AC/DC", Metadata(artist="AC/DC"), replace(RULES, answer_mode="artist"))[
            "artist"
        ].status
        == "matched"
    )


def test_unicode_and_optional_featuring():
    cfg = replace(RULES, answer_mode="artist")
    assert matched("فيروز", Metadata(artist="فيروز"), cfg)["artist"].status == "matched"
    cfg = replace(RULES, answer_fields=[*RULES.answer_fields, "featuring"])
    assert matched(EXAMPLE, settings=cfg)["featuring"].status == "matched"


@pytest.mark.parametrize(
    "patch",
    [
        {"acceptance_threshold": 79},
        {"acceptance_threshold": 101},
        {"answer_fields": []},
        {"answer_fields": ["title", "title"]},
        {"answer_fields": ["password"]},
    ],
)
def test_configuration_bounds(patch):
    with pytest.raises(ValidationError):
        SettingsPatch.model_validate(patch)


def test_alias_bounds_and_controls():
    with pytest.raises(ValidationError):
        MusicalMetadata(aliases={"title": ["a"] * 9})
    with pytest.raises(ValidationError):
        MusicalMetadata(aliases={"artist": ["unsafe\x00"]})


def automatic_game(**config):
    sc = Scenario(rounds=1)
    for bridge_id, catalog in sc.s.catalogs.items():
        for track_id in catalog.entries:
            sc.s.metadata[TrackRef(bridge_id, track_id)] = REFERENCE
    assert (
        sc.configure(
            scoring_mode="auto", answer_mode="fields", answer_fields=RULES.answer_fields, **config
        ).error
        is None
    )
    r = sc.to_open()
    return sc, r, sc.player_ids[0]


def test_awards_are_private_until_reveal_then_released_once_in_waves():
    sc, r, pid = automatic_game()
    sc.submit(pid, EXAMPLE)
    assert r.score_draft[pid] == 4
    public = sc.view(pid).model_dump_json()
    assert "Pilule bleue" not in public.replace(EXAMPLE, "")
    assert "auto_evidence" not in public
    sc.to_review()
    assert all(row.score == 0 for row in sc.view(pid).finale.standings)
    assert sc.on_phase("finale_reveal", {"round_id": r.id}).error is None
    assert sc.view(pid).finale.round.awards_pending
    assert all(row.score == 0 for row in sc.view(pid).finale.standings)
    sc.advance_to(r.finale_wave_at)
    sc.on_phase("finale_reveal", {"round_id": r.id, "fast_forward": True})
    assert next(row.score for row in sc.view(pid).finale.standings if row.player_id == pid) == 4
    sc.on_phase("finale_reveal", {"round_id": r.id})
    assert sc.s.journal.events() == ()
    sc.finalize()
    assert sc.s.journal.scores(sc.s.game.game_id)[pid] == 4


def test_manual_correction_survives_explicit_regrade_and_reference_is_frozen():
    sc, r, pid = automatic_game()
    sc.s.metadata[r.slot.track_ref] = replace(REFERENCE, title="Changed during playback")
    sc.submit(pid, EXAMPLE)
    assert r.score_draft[pid] == 4
    sc.to_review()
    assert (
        sc.host(
            "score_draft",
            round_id=r.id,
            args={"player_id": pid, "points": 7, "expected_revision": 1},
        ).error
        is None
    )
    assert (
        sc.host(
            "track_metadata",
            round_id=r.id,
            args={"title": "Changed after playback", "regrade_auto": True},
        ).error
        is None
    )
    assert r.score_draft[pid] == 7
    assert pid in r.auto_overrides


def test_captured_zero_is_respected_and_no_answer_is_reviewed_zero():
    sc, r, pid = automatic_game(captured_policy="zero")
    sc.draft(pid, EXAMPLE)
    sc.to_review()
    assert r.score_draft.get(pid, 0) == 0
    assert r.participant_ids <= r.score_reviewed


def test_captured_manual_keeps_suggestions_without_awarding_or_reviewing():
    sc, r, pid = automatic_game(captured_policy="manual")
    sc.draft(pid, EXAMPLE)
    sc.to_review()
    assert r.score_draft.get(pid, 0) == 0
    assert pid not in r.score_reviewed
    assert all(row.status == "matched" for row in r.auto_evidence[pid])
    assert all(value is None for value in r.judgements[pid].values())
    auto_scoring.grade_round(sc.s, r, regrade=True)
    assert pid not in r.score_reviewed
    assert r.score_draft.get(pid, 0) == 0


def test_numeric_guesses_cannot_win_but_known_optional_year_is_allowed():
    cfg = replace(RULES, answer_mode="title")
    assert matched("1989 1990 1991", Metadata(title="1989"), cfg)["title"].status == "ambiguous"
    assert matched("1989 2014", Metadata(title="1989", year=2014), cfg)["title"].status == "matched"
    assert matched("1989", Metadata(title="1989"), cfg)["title"].status == "matched"


def test_auto_scores_references_and_progress_survive_snapshot(tmp_path):
    sc, r, pid = automatic_game()
    sc.submit(pid, EXAMPLE)
    sc.to_review()
    sc.on_phase("finale_reveal", {"round_id": r.id})
    sessions = SessionRegistry(idle_ttl_ms=86400000)
    store = SnapshotStore(tmp_path, ("player", "host", "bridge"))
    store.save(sc.engine, sessions, sc.clock.now())
    fresh = GameEngine(
        sc.s.config,
        ids=SecretIds(),
        rng=random.Random(1),
        started_at=Instant(900000, sc.clock.now().wall_ms + 1000),
    )
    store.restore(
        fresh, SessionRegistry(idle_ttl_ms=86400000), Instant(900000, sc.clock.now().wall_ms + 1000)
    )
    loaded = fresh.state.game.rounds[0]
    assert loaded.score_draft[pid] == 4
    assert loaded.auto_reference == r.auto_reference
    assert loaded.auto_evidence == r.auto_evidence
    assert loaded.finale_wave_at > 900000
    assert fresh.state.game.phase is GamePhase.FINAL_SCORE_REVIEW


def test_pathological_matching_has_a_deterministic_work_budget(monkeypatch):
    original = auto_scoring.DamerauLevenshtein.normalized_similarity
    calls = []

    def counted(expected, segment, **kwargs):
        calls.append(len(expected) * len(segment))
        return original(expected, segment, **kwargs)

    monkeypatch.setattr(
        auto_scoring, "DamerauLevenshtein", SimpleNamespace(normalized_similarity=counted)
    )
    metadata = Metadata(
        title="a" * 256,
        artist="b" * 256,
        album="c" * 256,
        featuring="d" * 256,
        year=2015,
        aliases={key: ["xy" * 128] * 8 for key in ["title", "artist", "album", "featuring"]},
    )
    cfg = replace(
        RULES,
        answer_fields=["title", "artist", "album", "year", "featuring"],
        acceptance_threshold=80,
    )
    result = matched("q " * 749, metadata, cfg)
    assert sum(calls) <= auto_scoring.MAX_DISTANCE_WORK
    assert result["title"].status == "complex_answer"
    # Exact references anywhere in the bounded answer still work after budget exhaustion.
    metadata = replace(metadata, artist="Gims")
    result = matched("q " * 700 + "Gims", metadata, cfg)
    assert result["artist"].status == "matched"


@pytest.mark.parametrize("digits", ["²⁰¹⁵", "２０１５", "٢٠١٥"])  # noqa: RUF001 - Unicode fixtures
def test_normalized_unicode_years_do_not_crash(digits):
    cfg = replace(RULES, answer_fields=["year"])
    assert matched(digits, settings=cfg)["year"].status == "matched"


def test_unparseable_numeric_unicode_remains_unmatched():
    cfg = replace(RULES, answer_fields=["year"])
    assert matched("①②③⑩", settings=cfg)["year"].status == "not_found"


@pytest.mark.parametrize("extra", ["ft wrong song", "feat Wrong Artist", "featuring other guesses"])
def test_featuring_prefix_cannot_hide_unknown_guesses(extra):
    evidence = matched(
        "Hello Adele " + extra,
        Metadata(title="Hello", artist="Adele"),
        replace(RULES, answer_mode="both"),
    )
    assert all(row.status == "ambiguous" for row in evidence.values())


@pytest.mark.parametrize("answer", ["Hello Adele Adele", "Adele Hello Adele"])
def test_compatible_segments_are_allocated_across_all_fields(answer):
    evidence = matched(
        answer, Metadata(title="Hello Adele", artist="Adele"), replace(RULES, answer_mode="both")
    )
    assert all(row.status == "matched" for row in evidence.values())


def test_multiple_known_optional_fields_and_featuring_are_accepted():
    assert (
        matched(EXAMPLE, settings=replace(RULES, answer_mode="title"))["title"].status == "matched"
    )
    assert (
        matched(EXAMPLE, settings=replace(RULES, answer_mode="artist"))["artist"].status
        == "matched"
    )
    assert (
        matched(
            EXAMPLE.replace("niska", "someone else"), settings=replace(RULES, answer_mode="title")
        )["title"].status
        == "ambiguous"
    )


@pytest.mark.parametrize("separator", [" / ", "; ", " | "])
def test_punctuation_separating_correct_fields_is_accepted(separator):
    evidence = matched(
        separator.join(["Hello", "Adele"]),
        Metadata(title="Hello", artist="Adele"),
        replace(RULES, answer_mode="both"),
    )
    assert all(row.status == "matched" for row in evidence.values())


def test_numeric_title_is_not_a_conflicting_release_year():
    evidence = matched(
        "1989 2014",
        Metadata(title="1989", year=2014),
        replace(RULES, answer_fields=["title", "year"]),
    )
    assert all(row.status == "matched" for row in evidence.values())
    assert (
        matched(
            "1989 2014 2015",
            Metadata(title="1989", year=2014),
            replace(RULES, answer_fields=["title", "year"]),
        )["year"].status
        == "ambiguous"
    )


def test_filename_fallback_is_never_trusted_even_on_explicit_regrade():
    sc = Scenario(rounds=1, tags=False)
    assert sc.configure(scoring_mode="auto").error is None
    r = sc.to_open()
    assert r.auto_reference.title is r.auto_reference.artist is None
    pid = sc.player_ids[0]
    sc.submit(pid, "Synthetic filename")
    sc.to_review()
    assert sc.host("track_metadata", round_id=r.id, args={"regrade_auto": True}).error is None
    assert r.auto_reference.title is r.auto_reference.artist is None
    assert {row.status for row in r.auto_evidence[pid]} == {"missing_reference"}


def test_wrong_year_cannot_exempt_unknown_text_from_guess_validation():
    evidence = matched(
        "Hello Adele other song 2016",
        Metadata(title="Hello", artist="Adele", year=2015),
        replace(RULES, answer_fields=["title", "artist", "year"]),
    )
    assert evidence["title"].status == evidence["artist"].status == "ambiguous"
    assert evidence["year"].status == "not_found"
    # A single unknown requested artist still allows points for a correct title.
    evidence = matched(
        "Hello Unknown Artist",
        Metadata(title="Hello", artist="Adele"),
        replace(RULES, answer_mode="both"),
    )
    assert evidence["title"].status == "matched"
    assert evidence["artist"].status == "not_found"


def test_automatic_last_round_revisit_does_not_repeat_award_waves():
    sc = Scenario(rounds=2)
    for bridge_id, catalog in sc.s.catalogs.items():
        for track_id in catalog.entries:
            sc.s.metadata[TrackRef(bridge_id, track_id)] = REFERENCE
    assert sc.configure(scoring_mode="auto").error is None
    pid = sc.player_ids[0]
    first = sc.to_open()
    sc.submit(pid, "Sapés comme jamais Maitre Gims")
    sc.to_review()
    last = sc.to_open()
    sc.submit(pid, "Sapés comme jamais Maitre Gims")
    sc.to_review()
    for r in (last, first, last):
        assert sc.on_phase("finale_reveal", {"round_id": r.id}).error is None
    assert first.finale_wave_at is last.finale_wave_at is None
    assert next(row.score for row in sc.view(pid).finale.standings if row.player_id == pid) == 4
    sc.finalize()
    assert sc.s.journal.score(sc.s.game.game_id, pid) == 4


@pytest.mark.parametrize("title", ["Ou aller", "Or elsewhere"])
def test_alternative_word_at_reference_boundary_is_part_of_the_reference(title):
    evidence = matched(
        "Adele " + title, Metadata(title=title, artist="Adele"), replace(RULES, answer_mode="both")
    )
    assert all(row.status == "matched" for row in evidence.values())
