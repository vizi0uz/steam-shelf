"""Fetch the four artwork slots Steam shows for a shortcut.

Sources are tried in order: SteamGridDB first, because it covers games that have
no Steam store page and offers alternatives per slot, then Steam's official CDN.
A slot that neither source can fill is simply left empty -- Steam falls back to
the executable's own icon.
"""

from pathlib import Path
from typing import Optional

from core.services.image_client import SteamImageClient
from core.services.steamgriddb_client import ASSET_SPECS, SteamGridDBClient

# Which Steam CDN asset backs each grid slot, when SteamGridDB has nothing.
CDN_EQUIVALENT = {
    "p": "library_600x900_2x.jpg",
    "": "capsule_616x353.jpg",
    "_hero": "library_hero.jpg",
    "_logo": "logo.png",
}


class ArtworkProvider:
    """Chain SteamGridDB and the Steam CDN into one artwork lookup."""

    def __init__(
        self,
        save_path: Path,
        griddb: SteamGridDBClient = None,
        image_client: SteamImageClient = None,
    ):
        self.save_path = Path(save_path)
        self.griddb = griddb or SteamGridDBClient()
        self.image_client = image_client or SteamImageClient(save_path)

    @property
    def griddb_available(self) -> bool:
        return self.griddb.available

    def fetch_for(
        self,
        shortcut_id: int,
        steam_appid: Optional[int] = None,
        name: Optional[str] = None,
        progress_callback=None,
    ) -> dict:
        """Download every artwork slot for one shortcut.

        Args:
            shortcut_id: Non-Steam app ID; decides the filenames Steam reads.
            steam_appid: Steam app ID when the game was identified.
            name: Game name, used to search SteamGridDB when there is no appid.
            progress_callback: ``(message, fraction)`` updates.

        Returns:
            ``{slot: source}`` naming which source filled each slot.
        """
        self.save_path.mkdir(parents=True, exist_ok=True)

        griddb_game_id = self._resolve_griddb_game(steam_appid, name)
        filled = {}
        slots = list(ASSET_SPECS)

        for index, suffix in enumerate(slots):
            if progress_callback:
                label = suffix or "capsule"
                progress_callback(f"Fetching {label} artwork...", index / len(slots))

            source = None
            if griddb_game_id is not None:
                source = self._try_griddb(griddb_game_id, shortcut_id, suffix)
            if source is None and steam_appid is not None:
                source = self._try_cdn(steam_appid, shortcut_id, suffix)

            filled[suffix] = source

        if progress_callback:
            progress_callback("Artwork complete", 1.0)

        return filled

    def _resolve_griddb_game(self, steam_appid, name) -> Optional[int]:
        """Find the SteamGridDB game id, by appid when known, else by name."""
        if not self.griddb.available:
            return None

        if steam_appid is not None:
            game_id = self.griddb.game_id_from_steam_appid(steam_appid)
            if game_id is not None:
                return game_id

        if name:
            return self.griddb.search_game_id(name)

        return None

    def _try_griddb(self, griddb_game_id: int, shortcut_id: int, suffix: str):
        """Download the first working SteamGridDB image for a slot."""
        for url in self.griddb.asset_urls(griddb_game_id, suffix)[:3]:
            extension = Path(url.split("?")[0]).suffix or ".png"
            destination = self.save_path / f"{shortcut_id}{suffix}{extension}"
            if self.griddb.download(url, destination):
                self._drop_stale_variants(shortcut_id, suffix, keep=destination)
                return "steamgriddb"
        return None

    def _try_cdn(self, steam_appid: int, shortcut_id: int, suffix: str):
        """Fall back to Steam's own artwork for a slot."""
        img_type = CDN_EQUIVALENT[suffix]
        before = set(self.save_path.glob(f"{shortcut_id}{suffix}.*"))

        self.image_client.download_slot(steam_appid, img_type, shortcut_id)

        after = set(self.save_path.glob(f"{shortcut_id}{suffix}.*"))
        written = after - before
        if written:
            self._drop_stale_variants(shortcut_id, suffix, keep=next(iter(written)))
            return "steam-cdn"
        return "steam-cdn" if after else None

    def _drop_stale_variants(self, shortcut_id: int, suffix: str, keep: Path):
        """Keep one file per slot.

        Steam picks whichever extension it finds first, so leaving both a .png
        and a .jpg in the same slot makes the displayed artwork unpredictable.
        """
        for existing in self.save_path.glob(f"{shortcut_id}{suffix}.*"):
            if existing.name != keep.name and existing.suffix.lower() in {
                ".png", ".jpg", ".jpeg", ".webp",
            }:
                try:
                    existing.unlink()
                except OSError as exc:
                    print(f"Could not remove stale artwork {existing.name}: {exc}")
