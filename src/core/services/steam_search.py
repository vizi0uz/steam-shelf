"""Resolve a game name to a Steam app ID using Steam's public search endpoints.

This replaces the ``ISteamApps/GetAppList`` bulk download that Steam Shelf used to
mirror into a local database. That interface no longer exists -- Steam answers every
version of it with::

    404 Method 'GetAppList' not found in interface 'ISteamApps'

which left the local database empty and made every folder fail to match. Searching
on demand is also a better fit for the problem: Valve's own search already handles
the fuzzy part, so ``STALKER2`` resolves to ``S.T.A.L.K.E.R. 2: Heart of Chornobyl``
without the user renaming anything on disk.
"""

import re
from difflib import SequenceMatcher
from typing import List, NamedTuple

import requests

STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
COMMUNITY_SEARCH_URL = "https://steamcommunity.com/actions/SearchApps/{term}"

# Steam's store endpoint rejects the default requests user agent often enough that
# it is worth sending a browser-like one.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) steam-shelf"

DEFAULT_TIMEOUT = 20

# Noise commonly found in release folder names that never appears in a store title.
_NOISE_PATTERNS = (
    r"\[.*?\]",
    r"\(.*?\)",
    r"\b(gog|repack|fitgirl|dodi|codex|plaza|razor1911|elamigos|rune|empress)\b",
    r"\bv?\d+\.\d+[\d.]*\b",
    r"\b(multi\d+|proper|readnfo|incl|dlcs?|update|build\s*\d+)\b",
    r"\b(deluxe|ultimate|goty|complete|definitive|enhanced|remastered)\s+edition\b",
)

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


class SteamAppMatch(NamedTuple):
    """One candidate returned by a Steam search."""

    appid: int
    name: str
    score: float  # 0.0-1.0 similarity against the term that was searched


def normalize(name: str) -> str:
    """Reduce a name to a comparable form.

    Lowercases, drops punctuation and collapses whitespace, so that
    ``S.T.A.L.K.E.R. 2`` and ``STALKER2`` land close to each other.
    """
    text = name.lower()
    text = _PUNCTUATION.sub("", text)
    return _WHITESPACE.sub("", text)


def clean_search_term(folder_name: str) -> str:
    """Strip release-group noise from a folder name before searching.

    Order matters: bracketed tags and version numbers are removed while their
    punctuation is still intact, because ``v1.32`` stops looking like a version
    the moment the dots become spaces.
    """
    text = folder_name
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = text.replace("_", " ").replace("-", " ")
    text = _WHITESPACE.sub(" ", text).strip(" -")
    return text or folder_name


def similarity(term: str, candidate: str) -> float:
    """Score how well a store title matches the term that was searched."""
    a, b = normalize(term), normalize(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # A store title that starts with the term is usually the base game plus a
    # subtitle ("S.T.A.L.K.E.R. 2" -> "...: Heart of Chornobyl"). Flag it, but
    # do not let the boost decide between two such titles -- Steam's own
    # relevance ranking is better at that than string length is.
    if b.startswith(a):
        ratio = max(ratio, 0.90)
    elif a in b:
        ratio = max(ratio, 0.85)
    return ratio


class SteamAppSearch:
    """Look up Steam app IDs by name, newest-working-endpoint first."""

    def __init__(self, session: requests.Session = None, country: str = "us"):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.country = country

    def search(self, term: str, limit: int = 8) -> List[SteamAppMatch]:
        """Return candidate Steam apps for a name, best match first.

        Never raises on network trouble -- an empty list means "could not
        resolve", which callers must handle as a candidate needing manual
        confirmation rather than as a fatal error.
        """
        cleaned = clean_search_term(term)

        results = self._store_search(cleaned)
        if not results:
            results = self._community_search(cleaned)

        scored = [
            (rank, SteamAppMatch(appid, name, similarity(cleaned, name)))
            for rank, (appid, name) in enumerate(results)
        ]
        # Steam's result order already encodes relevance and popularity, which
        # beats any local string metric at telling "Heart of Chornobyl" from
        # "Cost of Hope". So only the similarity *band* reorders results; within
        # a band the store's own ranking decides.
        #
        # The band is two decimals, not one: at one decimal an exact title and a
        # merely similar one both round to 1.0, and the exact match loses to
        # whatever Steam happened to list first.
        scored.sort(key=lambda item: (-round(item[1].score, 2), item[0]))
        return [match for _, match in scored[:limit]]

    def best_match(self, term: str, confident_at: float = 0.92):
        """Return ``(match, confirmed)`` for a name.

        ``confirmed`` is True only when the top hit scores above
        ``confident_at`` and is clearly ahead of the runner-up. Anything else
        goes back to the user for confirmation instead of being guessed at.
        """
        matches = self.search(term)
        if not matches:
            return None, False

        top = matches[0]
        runner_up = matches[1].score if len(matches) > 1 else 0.0
        confirmed = top.score >= confident_at and (top.score - runner_up) >= 0.02
        return top, confirmed

    def _store_search(self, term: str):
        """Query the storefront search API. Returns ``[(appid, name), ...]``."""
        try:
            response = self.session.get(
                STORE_SEARCH_URL,
                params={"term": term, "cc": self.country, "l": "en"},
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Store search failed for {term!r}: {exc}")
            return []

        return [
            (item["id"], item["name"])
            for item in payload.get("items", [])
            # "app" excludes DLC, soundtracks and bundles, which share a title
            # with the base game and would otherwise outrank nothing useful.
            if item.get("type") == "app" and item.get("id") and item.get("name")
        ]

    def _community_search(self, term: str):
        """Fallback search used when the storefront endpoint returns nothing."""
        try:
            response = self.session.get(
                COMMUNITY_SEARCH_URL.format(term=requests.utils.quote(term)),
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Community search failed for {term!r}: {exc}")
            return []

        results = []
        for item in payload or []:
            try:
                results.append((int(item["appid"]), item["name"]))
            except (KeyError, TypeError, ValueError):
                continue
        return results
