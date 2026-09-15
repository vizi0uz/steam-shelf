"""SteamGridDB artwork source.

Complements the official Steam CDN: SteamGridDB carries community artwork for
games that have no Steam store page at all, which the CDN by definition cannot
serve. Requires a free API key.

The key is read from the ``STEAMGRIDDB_API_KEY`` environment variable. It is
never written to disk by this module and never included in log output.
"""

import os
from pathlib import Path
from typing import List, Optional

import requests

API_BASE = "https://www.steamgriddb.com/api/v2"
API_KEY_ENV = "STEAMGRIDDB_API_KEY"
DEFAULT_TIMEOUT = 20

# Steam reads artwork out of userdata/<id>/config/grid using these suffixes.
# Verified against the files an existing Steam install had already written.
ASSET_SPECS = {
    # suffix: (endpoint, query parameters)
    "p": ("grids", {"dimensions": "600x900,342x482,660x930"}),
    "": ("grids", {"dimensions": "460x215,920x430"}),
    "_hero": ("heroes", {}),
    "_logo": ("logos", {}),
}


class SteamGridDBClient:
    """Minimal SteamGridDB v2 client covering the four Steam artwork slots."""

    def __init__(self, api_key: Optional[str] = None, session: requests.Session = None):
        self.api_key = api_key or os.environ.get(API_KEY_ENV) or None
        self.session = session or requests.Session()

    @property
    def available(self) -> bool:
        """Whether a key is configured. Without one the client is inert."""
        return bool(self.api_key)

    def _get(self, path: str, params: dict = None):
        """Call the API and return the ``data`` payload, or None on failure."""
        if not self.available:
            return None

        try:
            response = self.session.get(
                f"{API_BASE}/{path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params=params or {},
                timeout=DEFAULT_TIMEOUT,
            )
            if response.status_code == 401:
                # Say what is wrong without ever echoing the key itself.
                print("SteamGridDB rejected the API key (401).")
                return None
            if response.status_code == 404:
                return None
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"SteamGridDB request to {path} failed: {exc}")
            return None

        if not payload.get("success"):
            return None
        return payload.get("data")

    def game_id_from_steam_appid(self, steam_appid: int) -> Optional[int]:
        """Translate a Steam app ID into a SteamGridDB game ID."""
        data = self._get(f"games/steam/{steam_appid}")
        if isinstance(data, dict):
            return data.get("id")
        return None

    def search_game_id(self, term: str) -> Optional[int]:
        """Find a SteamGridDB game ID by name, for games not on Steam."""
        data = self._get(f"search/autocomplete/{requests.utils.quote(term)}")
        if isinstance(data, list) and data:
            return data[0].get("id")
        return None

    def asset_urls(self, game_id: int, suffix: str) -> List[str]:
        """Return candidate image URLs for one artwork slot, best first."""
        endpoint, params = ASSET_SPECS[suffix]
        data = self._get(f"{endpoint}/game/{game_id}", params)
        if not isinstance(data, list):
            return []
        return [item["url"] for item in data if item.get("url")]

    def download(self, url: str, destination: Path) -> bool:
        """Fetch one image to disk. Returns whether it succeeded."""
        try:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Failed to download artwork from {url}: {exc}")
            return False

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return True
