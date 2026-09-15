from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from core.services.game_validator import GameValidator
from core.services.steam_db_utils import SteamDatabase
from core.services.steam_search import SteamAppMatch
from core.utils.shortcut_utils import generate_shortcut_appid


class DiscoveryStats(NamedTuple):
    """Why a scan produced the number of candidates it did.

    Without this the UI could only say "nothing found", which is what made the
    real failure impossible to diagnose: a folder rejected for having no Steam
    match was reported as a folder with no executables in it.
    """

    directories_seen: int = 0
    directories_skipped: int = 0   # blacklisted or already added
    without_executables: int = 0
    without_steam_match: int = 0
    candidates: int = 0


class GameCandidate(NamedTuple):
    steam_id: Optional[int]  # Steam app ID for artwork; None when unresolved
    shortcut_id: int  # Generated shortcut app ID for file naming
    name: str  # Name the shortcut will carry in Steam
    exe_path: Path
    start_dir: Path
    confirmed: bool = False  # Whether the Steam match is unambiguous
    folder_name: str = ""  # Directory the game was discovered in
    matches: Tuple[SteamAppMatch, ...] = ()  # Alternatives for the user to pick


class GameDiscoveryService:
    def __init__(self, steam_db: SteamDatabase, validator: GameValidator, added_games: set = None):
        self.steam_db = steam_db
        self.validator = validator
        self.games_already_added = added_games or set()  # Track added games to avoid duplicates
        self.last_stats = DiscoveryStats()

    def discover_games_from_directory(self, path: Path, progress_callback=None) -> List[GameCandidate]:
        """Discover games from a directory structure."""
        candidates = []
        counters = {
            "directories_skipped": 0,
            "without_executables": 0,
            "without_steam_match": 0,
        }

        # Get list of directories to process
        directories = [d for d in path.iterdir() if d.is_dir()]
        total_dirs = len(directories)

        for i, directory in enumerate(directories):
            try:
                if progress_callback:
                    progress_callback(f"Scanning {directory.name}...", i / max(total_dirs, 1))

                candidate = self._process_directory(directory, counters)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                print(f"Failed to process directory {directory.name}: {e}")
                continue

        self.last_stats = DiscoveryStats(
            directories_seen=total_dirs,
            candidates=len(candidates),
            **counters,
        )

        if progress_callback:
            progress_callback("Game discovery complete", 1.0)

        return candidates

    def _process_directory(self, directory: Path, counters: dict = None) -> Optional[GameCandidate]:
        """Process a single directory for game discovery.

        Executables are located *before* the Steam lookup. The reverse order is
        what broke discovery entirely: an unresolvable name discarded the folder
        before anything on disk was ever examined.
        """
        counters = counters if counters is not None else {}
        folder_name = directory.name

        # Skip if already added
        if folder_name in self.games_already_added:
            counters["directories_skipped"] = counters.get("directories_skipped", 0) + 1
            return None

        # Validate directory
        if not self.validator.is_valid_directory(directory):
            counters["directories_skipped"] = counters.get("directories_skipped", 0) + 1
            return None

        # Find executables -- this is the part the old order never reached
        exe_files = list(directory.rglob("*.exe"))
        valid_exes = self.validator.filter_executables(exe_files)

        if not valid_exes:
            print(f"No valid executables found in {folder_name}")
            counters["without_executables"] = counters.get("without_executables", 0) + 1
            return None

        main_exe = self.validator.find_main_executable(valid_exes, folder_name, directory)
        print(f"Likely main exe for {folder_name}: {main_exe}")

        # Now try to identify the game on Steam. A miss is no longer fatal: the
        # candidate is returned unconfirmed so the user can correct it.
        match, confirmed, alternatives = self.steam_db.resolve(folder_name)

        if match is None:
            counters["without_steam_match"] = counters.get("without_steam_match", 0) + 1
            print(f"No Steam match for {folder_name}; keeping it as unconfirmed")

        # A confirmed match supplies the proper title ("STALKER2" becomes
        # "S.T.A.L.K.E.R. 2: Heart of Chornobyl"); otherwise keep the folder
        # name until the user says which game it is.
        display_name = match.name if (match and confirmed) else folder_name

        return GameCandidate(
            steam_id=match.appid if match else None,
            shortcut_id=generate_shortcut_appid(display_name, str(main_exe.resolve())),
            name=display_name,
            exe_path=main_exe.resolve(),
            start_dir=main_exe.parent,
            confirmed=confirmed,
            folder_name=folder_name,
            matches=tuple(alternatives),
        )
