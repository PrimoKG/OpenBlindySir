"""Filename fallback is shared by library, preflight and actual scoring."""

from dataclasses import replace

import pytest
from builders import Scenario

from openblindysir_server.game.filename_metadata import filename_metadata
from openblindysir_server.game.metadata import scoring_metadata, selection_metadata
from openblindysir_server.game.rounds import build_reveal
from openblindysir_server.game.state import Metadata


@pytest.mark.parametrize(
    ("filename", "title", "artist", "featuring"),
    [
        ("Niska - Réseaux.mp3", "Réseaux", "Niska", None),
        (
            "Travis Scott - FE!N (Official Music Video) ft. Playboi Carti.mp3",
            "FE!N",
            "Travis Scott",
            "Playboi Carti",
        ),
        (
            "01. GIMS feat. Niska - Sapés comme jamais (Clip Officiel).flac",
            "Sapés comme jamais",
            "GIMS",
            "Niska",
        ),
        ("GIMS - Sapés comme jamais (feat. Niska).mp3", "Sapés comme jamais", "GIMS", "Niska"),
        ("GIMS & DYSTINCT - SPIDER (Official Lyrics Video).mp3", "SPIDER", "GIMS & DYSTINCT", None),
        ("The Weeknd - Starboy (Lyrics) ft. Daft Punk.mp3", "Starboy", "The Weeknd", "Daft Punk"),
        ("Réseaux.mp3", "Réseaux", None, None),
        ("FE!N.mp3", "FE!N", None, None),
        ("Couleur-café.mp3", "Couleur-café", None, None),
        ("Song (HD).mp3", "Song", None, None),
        ("Artist - Song (feat. Guest) (Remix).mp3", "Song (Remix)", "Artist", "Guest"),
        ("9a9a31f9-5cd4-4055-ac7d-557713f87b2a.mp3", None, None, None),
        ("folder/Chanson_avec_espaces.MP3", "Chanson avec espaces", None, None),
        ("Prince - 1999.mp3", "1999", "Prince", None),
        ("Song (Live).mp3", "Song (Live)", None, None),
        ("Piste 12.mp3", None, None, None),
        ("track-001.flac", None, None, None),
    ],
)
def test_filename_hints(filename, title, artist, featuring):
    meta = filename_metadata(filename)
    assert (meta.title, meta.artist, meta.featuring) == (title, artist, featuring)
    assert meta.year is meta.album is None


def prepare():
    sc = Scenario(rounds=1, tracks=1, tags=False)
    catalog = next(iter(sc.s.catalogs.values()))
    tid = next(iter(catalog.entries))
    catalog.entries[tid] = replace(catalog.entries[tid], relpath="Niska - Réseaux.mp3")
    return sc


def test_filename_reference_is_ready_frozen_graded_and_revealed_consistently():
    sc = prepare()
    assert sc.configure(scoring_mode="auto", ready_only=True, answer_mode="both").error is None
    r = sc.to_open()
    assert (r.auto_reference.title, r.auto_reference.artist) == ("Réseaux", "Niska")
    pid = sc.player_ids[0]
    sc.submit(pid, "Niska reseaux")
    sc.to_review()
    assert pid in r.score_reviewed
    assert r.score_draft[pid] == 2
    reveal = build_reveal(sc.s, r)
    assert (reveal.title, reveal.artist) == ("Réseaux", "Niska")


def test_filename_never_overrides_tags_host_corrections_or_explicit_clears():
    sc = prepare()
    r = sc.to_open()
    ref = r.slot.track_ref
    catalog = sc.s.catalogs[ref.bridge_id]
    catalog.entries[ref.track_id] = replace(
        catalog.entries[ref.track_id],
        tags=Metadata(title="Embedded title", artist="Embedded artist"),
    )
    assert selection_metadata(sc.s, ref, None).title == "Embedded title"
    assert scoring_metadata(sc.s, ref, None).artist == "Embedded artist"
    sc.s.metadata[ref] = Metadata(title="Host title", cleared_fields=["artist", "featuring"])
    meta = scoring_metadata(sc.s, ref, None)
    assert meta.title == "Host title"
    assert meta.artist is meta.featuring is None


def test_title_only_filename_does_not_invent_artist_and_handles_missing_catalog():
    sc = prepare()
    catalog = next(iter(sc.s.catalogs.values()))
    tid = next(iter(catalog.entries))
    catalog.entries[tid] = replace(catalog.entries[tid], relpath="FE!N.mp3")
    r = sc.to_open()
    ref = r.slot.track_ref
    assert scoring_metadata(sc.s, ref, None).title == "FE!N"
    assert scoring_metadata(sc.s, ref, None).artist is None
    sc.s.catalogs.clear()
    assert scoring_metadata(sc.s, ref, None).title is None
