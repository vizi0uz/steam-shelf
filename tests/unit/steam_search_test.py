"""Tests for name-to-appid resolution.

Every test here runs offline: the HTTP session is stubbed, so results are
deterministic and the suite does not depend on Steam being reachable.
"""

import pytest

from core.services.steam_search import (
    SteamAppSearch,
    clean_search_term,
    normalize,
    similarity,
)


class _StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected status {self.status_code}")

    def json(self):
        return self._payload


class _StubSession:
    """Answers the store endpoint with a canned payload."""

    def __init__(self, items):
        self.items = items
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None, **kwargs):
        self.calls.append((url, params))
        return _StubResponse({"items": self.items})


def _app(appid, name):
    return {"type": "app", "id": appid, "name": name}


class TestNormalize:
    def test_drops_punctuation_and_spacing(self):
        assert normalize("S.T.A.L.K.E.R. 2") == normalize("STALKER 2") == "stalker2"

    def test_is_case_insensitive(self):
        assert normalize("Alien: Isolation") == normalize("alien isolation")

    def test_empty_string(self):
        assert normalize("") == ""


class TestCleanSearchTerm:
    def test_strips_bracketed_release_tags(self):
        assert clean_search_term("Witcher 3 [FitGirl Repack]") == "Witcher 3"

    def test_strips_version_numbers(self):
        # Versions must be removed while their dots are intact, or "v1.32"
        # survives as a stray "32" and poisons the search.
        assert clean_search_term("Some Game v1.32") == "Some Game"

    def test_keeps_a_plain_name_untouched(self):
        assert clean_search_term("Alien Isolation") == "Alien Isolation"

    def test_never_returns_empty(self):
        assert clean_search_term("[GOG]") == "[GOG]"


class TestSimilarity:
    def test_identical_after_normalisation_scores_one(self):
        assert similarity("Alien Isolation", "Alien: Isolation") == 1.0

    def test_subtitle_still_scores_high(self):
        assert similarity("STALKER2", "S.T.A.L.K.E.R. 2: Heart of Chornobyl") >= 0.90

    def test_unrelated_names_score_low(self):
        assert similarity("Alien Isolation", "Euro Truck Simulator") < 0.5


class TestSteamAppSearch:
    def test_exact_match_ranks_first(self):
        session = _StubSession([
            _app(4665290, "Alien: Isolation 2"),
            _app(214490, "Alien: Isolation"),
        ])
        results = SteamAppSearch(session=session).search("Alien Isolation")

        assert results[0].appid == 214490
        assert results[0].score == 1.0

    def test_steam_ordering_breaks_ties(self):
        """Two equally-scoring subtitles keep the order Steam returned them in.

        A local string metric cannot tell "Heart of Chornobyl" from "Cost of
        Hope"; Steam's own relevance ranking can, so it must not be discarded.
        """
        session = _StubSession([
            _app(1643320, "S.T.A.L.K.E.R. 2: Heart of Chornobyl"),
            _app(3765020, "S.T.A.L.K.E.R. 2: Cost of Hope"),
        ])
        results = SteamAppSearch(session=session).search("STALKER2")

        assert results[0].appid == 1643320

    def test_dlc_entries_are_excluded(self):
        session = _StubSession([
            {"type": "dlc", "id": 282513, "name": "Alien: Isolation - Trauma"},
            _app(214490, "Alien: Isolation"),
        ])
        results = SteamAppSearch(session=session).search("Alien Isolation")

        assert [r.appid for r in results] == [214490]

    def test_ambiguous_match_is_not_confirmed(self):
        session = _StubSession([
            _app(1643320, "S.T.A.L.K.E.R. 2: Heart of Chornobyl"),
            _app(3765020, "S.T.A.L.K.E.R. 2: Cost of Hope"),
        ])
        match, confirmed = SteamAppSearch(session=session).best_match("STALKER2")

        assert match.appid == 1643320
        assert confirmed is False

    def test_exact_match_is_confirmed(self):
        session = _StubSession([_app(214490, "Alien: Isolation")])
        match, confirmed = SteamAppSearch(session=session).best_match("Alien Isolation")

        assert match.appid == 214490
        assert confirmed is True

    def test_no_results_returns_nothing(self):
        session = _StubSession([])
        match, confirmed = SteamAppSearch(session=session).best_match("R5Reloaded")

        assert match is None
        assert confirmed is False
