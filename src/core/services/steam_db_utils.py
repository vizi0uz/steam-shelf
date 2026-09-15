"""Local cache of resolved Steam app IDs.

Historically this module mirrored Steam's entire app list into SQLite and looked
names up offline. That interface is gone -- every version of
``ISteamApps/GetAppList`` now answers::

    404 Method 'GetAppList' not found in interface 'ISteamApps'

so the mirror silently stayed empty and every lookup failed. Resolution now
happens on demand through :mod:`core.services.steam_search`, and this module
keeps what was resolved so repeat runs do not hit the network again.
"""

import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Tuple

from core.services.steam_search import SteamAppMatch, SteamAppSearch

ILLEGAL_CHARS = r'[<>:"/\\|?*]'

# Resolutions older than this are re-checked, so a game that was not on Steam
# when it was first scanned can still be picked up later.
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60


def safe_name(name: str) -> str:
    """Strip characters Windows forbids in filenames."""
    return re.sub(ILLEGAL_CHARS, '', name).strip()


def default_db_path() -> Path:
    """Where the cache lives.

    A fixed per-user location, not the working directory: the frozen build used
    to drop ``steam.db`` wherever the executable happened to be launched from,
    so the cache was rebuilt or lost depending on how it was started.
    """
    import os

    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "SteamShelf" / "steam.db"


def _is_sqlite_uri(db_path) -> bool:
    """Whether a value names an in-memory or URI database rather than a file."""
    return isinstance(db_path, str) and (
        db_path == ":memory:" or db_path.startswith("file:")
    )


class SteamAppListUnavailable(RuntimeError):
    """Raised when the removed bulk app-list endpoint is requested."""


class SteamDatabase:
    """Name-to-appid resolution, cached on disk."""

    def __init__(self, db_path=None, search: SteamAppSearch = None):
        if db_path is None:
            self.db_path = default_db_path()
        else:
            # ":memory:" and other SQLite URIs are not filesystem paths and must
            # be passed through untouched.
            self.db_path = db_path if _is_sqlite_uri(db_path) else Path(db_path)

        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self.search = search or SteamAppSearch()

        self._init_database()

    def _init_database(self):
        """Create the schema if it is not there yet."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS games "
                "(id INTEGER PRIMARY KEY, name TEXT, safe_name TEXT UNIQUE)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS resolutions ("
                "term TEXT PRIMARY KEY, appid INTEGER, name TEXT, "
                "score REAL, confirmed INTEGER, resolved_at INTEGER)"
            )

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def sync(self, progress_callback=None):
        """No longer supported -- kept so old call sites fail loudly.

        Raises:
            SteamAppListUnavailable: always.
        """
        raise SteamAppListUnavailable(
            "Steam removed ISteamApps/GetAppList, so the full app list can no "
            "longer be mirrored locally. Steam Shelf now resolves names on "
            "demand and caches the results; no sync step is needed."
        )

    def resolve(self, name: str, force: bool = False):
        """Resolve a game name to a Steam app.

        Args:
            name: Folder or game name to look up.
            force: Skip the cache and search again.

        Returns:
            ``(match, confirmed, alternatives)`` where ``match`` is a
            :class:`SteamAppMatch` or ``None``. ``confirmed`` is True only when
            the match is unambiguous enough to use without asking the user.
        """
        if not force:
            known = self._read_known_game(name)
            if known is not None:
                return known

            cached = self._read_cache(name)
            if cached is not None:
                return cached

        matches = self.search.search(name)
        if not matches:
            self._write_cache(name, None, False)
            return None, False, []

        top = matches[0]
        runner_up = matches[1].score if len(matches) > 1 else 0.0
        confirmed = top.score >= 0.92 and (top.score - runner_up) >= 0.02

        self._write_cache(name, top, confirmed)
        return top, confirmed, matches

    def remember(self, name: str, match: SteamAppMatch):
        """Record a match the user picked by hand, as confirmed."""
        self._write_cache(name, match, True)

    def get_steam_id_from_name(self, name: str) -> Optional[int]:
        """Return the Steam app ID for a name, or None.

        Kept for backwards compatibility with existing call sites and tests.
        """
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT id FROM games WHERE safe_name = ?", (safe_name(name),)
            )
            row = cur.fetchone()
            if row:
                return row[0]

        match, _confirmed, _alternatives = self.resolve(name)
        return match.appid if match else None

    def _read_known_game(self, name: str):
        """Resolve straight from the games table, without touching the network.

        An exact title already stored locally needs no search at all, which
        keeps repeat scans and offline use working.
        """
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT id, name FROM games WHERE safe_name = ?", (safe_name(name),)
            )
            row = cur.fetchone()

        if not row:
            return None

        match = SteamAppMatch(row[0], row[1], 1.0)
        return match, True, [match]

    def _read_cache(self, name: str):
        """Return a cached resolution tuple, or None when absent or stale."""
        key = safe_name(name).lower()
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT appid, name, score, confirmed, resolved_at "
                "FROM resolutions WHERE term = ?",
                (key,),
            )
            row = cur.fetchone()

        if not row:
            return None

        appid, app_name, score, confirmed, resolved_at = row
        if time.time() - (resolved_at or 0) > CACHE_TTL_SECONDS:
            return None
        if appid is None:
            return None, False, []

        match = SteamAppMatch(appid, app_name, score or 0.0)
        return match, bool(confirmed), [match]

    def _write_cache(self, name: str, match: Optional[SteamAppMatch], confirmed: bool):
        """Persist a resolution, including a negative one."""
        key = safe_name(name).lower()
        with self._lock, self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO resolutions "
                "(term, appid, name, score, confirmed, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    key,
                    match.appid if match else None,
                    match.name if match else None,
                    match.score if match else None,
                    1 if confirmed else 0,
                    int(time.time()),
                ),
            )
            if match:
                conn.execute(
                    "INSERT OR IGNORE INTO games (id, name, safe_name) VALUES (?, ?, ?)",
                    (match.appid, match.name, safe_name(match.name)),
                )
            conn.commit()

    def close(self):
        """Close method for compatibility - connections are auto-closed."""
        pass


if __name__ == "__main__":
    db = SteamDatabase()
    for folder in ("Alien Isolation", "STALKER2"):
        print(folder, "->", db.resolve(folder))
