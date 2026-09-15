from pathlib import Path
from typing import List, NamedTuple, Optional
from core.services.steam_db_utils import SteamDatabase
from core.services.game_validator import GameValidator
from core.utils.shortcut_utils import generate_shortcut_appid

class DiscoveryStats(NamedTuple):
    """Why a scan ended up with the candidates it did.

    Without this the UI can only say "nothing found" and guess at the reason,
    which is how a failed Steam lookup came to be reported to users as missing
    executables.
    """
    directories_seen: int = 0
    directories_skipped: int = 0
    without_executables: int = 0
    without_steam_match: int = 0
    candidates: int = 0

class GameCandidate(NamedTuple):
    steam_id: Optional[int]  # Steam app ID for downloading images; None when unidentified
    shortcut_id: int  # Generated shortcut app ID for file naming
    name: str
    exe_path: Path
    start_dir: Path
    confirmed: bool = False  # Whether this game is a confirmed match in the Steam database
class GameDiscoveryService:
    def __init__(self, steam_db: SteamDatabase, validator: GameValidator, added_games: set = None):
        self.steam_db = steam_db
        self.validator = validator
        self.games_already_added = added_games or set()  # Track added games to avoid duplicates
        self.last_scan_stats = DiscoveryStats()

    def discover_games_from_directory(self, path: Path, progress_callback=None) -> List[GameCandidate]:
        """Discover games from a directory structure."""
        candidates = []
        counters = {}

        # Get list of directories to process
        directories = [d for d in path.iterdir() if d.is_dir()]
        total_dirs = len(directories)

        for i, directory in enumerate(directories):
            try:
                if progress_callback:
                    progress_callback(f"Scanning {directory.name}...", i / total_dirs)

                candidate = self._process_directory(directory, counters)
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                print(f"Failed to process directory {directory.name}: {e}")
                continue

        self.last_scan_stats = DiscoveryStats(
            directories_seen=total_dirs,
            directories_skipped=counters.get("directories_skipped", 0),
            without_executables=counters.get("without_executables", 0),
            without_steam_match=counters.get("without_steam_match", 0),
            candidates=len(candidates),
        )

        if progress_callback:
            progress_callback("Game discovery complete", 1.0)

        return candidates

    def _process_directory(self, directory: Path, counters: dict = None) -> Optional[GameCandidate]:
        """Process a single directory for game discovery.

        Executables are located *before* the Steam lookup, and a folder the
        lookup cannot identify is kept rather than dropped. The reverse order
        is what broke discovery entirely: an unresolvable name discarded the
        folder before anything on disk was ever examined, and the UI then
        reported the empty result as missing executables.
        """
        counters = counters if counters is not None else {}
        name = directory.name
        # Skip if already added
        if name in self.games_already_added:
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
            print(f"No valid executables found in {name}")
            counters["without_executables"] = counters.get("without_executables", 0) + 1
            return None


        # Find main executable
        main_exe = self.validator.find_main_executable(valid_exes, name)

        print(f"Likely main exe for {name}: {main_exe}")

        # Check if it's a known Steam game. A miss is no longer fatal: the
        # candidate is kept unconfirmed, so the game still reaches the library
        # -- under its folder name, and without artwork.
        steam_id = self.steam_db.get_steam_id_from_name(name)
        if not steam_id:
            counters["without_steam_match"] = counters.get("without_steam_match", 0) + 1
            print(f"No Steam match for {name}; keeping it as unconfirmed")

        # Generate shortcut app ID using the game name and executable
        shortcut_id = generate_shortcut_appid(name, str(main_exe))

        return GameCandidate(
            steam_id=steam_id if steam_id else None,
            shortcut_id=shortcut_id,
            name=name,
            exe_path=main_exe.resolve(),
            start_dir=main_exe.parent,
            confirmed=bool(steam_id)
        )
