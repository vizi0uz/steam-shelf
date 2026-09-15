from pathlib import Path

from core.services.artwork_provider import ArtworkProvider
from core.services.image_client import SteamImageClient
from core.utils.vdf_utils import write_binary_vdf, parse_vdf
from core.models.non_steam_game import NonSteamGame
from core.services.game_discovery import GameDiscoveryService
from core.services.game_validator import GameValidator
from core.utils.steam_path import get_steam_path_or_fallback
from core.utils.vdf_serializer import VDFSerializer
from core.services.steam_db_utils import SteamDatabase

BLACKLISTED_DIRECTORIES = {"steam"}

# Support binaries that ship next to a game and would otherwise win the
# "biggest executable" tiebreak. "unins" matters because InnoSetup names its
# uninstallers unins000.exe, which "uninstall" never matched.
BLACKLISTED_EXECUTABLES = {
    "uninstall", "unins", "setup", "update",
    "crashreport", "crashhandler", "vcredist", "dxsetup", "directx",
    "redist", "dotnet", "oalinst", "benchmark",
}

class NonSteamGameRepository:
    """Repository for managing non-Steam games.
        
    Args:
        user_id (int): Steam user ID for saving images
        steam_path (Path): Steam installation path
        discovery_service (GameDiscoveryService, optional): Game discovery service
        serializer (VDFSerializer, optional): VDF serialization service
        validator (GameValidator, optional): Game validation service
        steam_image_client (SteamImageClient, optional): Image downloading service
    """
    def __init__(self, 
                 user_id: int,
                 steam_path : Path | None = None,
                 discovery_service: GameDiscoveryService = None,
                 serializer: VDFSerializer = None ,
                 validator: GameValidator = None,
                 steam_image_client:SteamImageClient = None):
        self.user_id = user_id
        self.games: list[NonSteamGame] = []
        self.game_candidates: list = []  # Store original candidates for image downloading
        
        # Use dependency injection or create default services
        self.validator = validator or GameValidator(
            BLACKLISTED_DIRECTORIES, 
            BLACKLISTED_EXECUTABLES
        )
        self.serializer = serializer or VDFSerializer()
        steam_path = steam_path or get_steam_path_or_fallback()
        self.steam_path = steam_path
        self.shortcuts_vdf_path = steam_path /"userdata"/str(user_id)/"config"/"shortcuts.vdf"
        grid_path = steam_path/"userdata"/str(user_id)/"config"/"grid"
        self.image_client = steam_image_client or SteamImageClient(save_path=grid_path)
        self.artwork_provider = ArtworkProvider(
            save_path=grid_path,
            image_client=self.image_client,
        )
        if self.shortcuts_vdf_path.exists():
            self.load_games_from_vdf(self.shortcuts_vdf_path)
        else:
            print("No shortcuts.vdf file found, defaulting to empty repo")
        self.discovery_service = discovery_service or GameDiscoveryService(
            SteamDatabase(),
            self.validator,
            added_games={game.AppName for game in self.games},
            added_executables={game.Exe for game in self.games},
        )
        
    
    def add_game(self, game: NonSteamGame):
        """Add a game to the repository.
        
        Args:
            game (NonSteamGame): Game to add
        """
        self.games.append(game)
    
    def load_games_from_directory(self, path: Path, progress_callback=None):
        """Load games by discovering them from a directory structure.
        
        Args:
            path (Path): Directory to scan for games
            progress_callback: Optional callback for progress updates (message, progress)
            
        Raises:
            FileNotFoundError: If directory doesn't exist
        """
        candidates = self.discovery_service.discover_games_from_directory(path, progress_callback)
        # Why a scan came back thin is the thing the UI has to be able to say.
        self.last_scan_stats = self.discovery_service.last_stats
        self.game_candidates.extend(candidates)  # Store candidates for image downloading
        for candidate in candidates:
            game = NonSteamGame.from_candidate(candidate)
            self.add_game(game)
                
        
    def load_games_from_vdf(self, path: Path):
        """Load games from an existing VDF file.
        
        Args:
            path (Path): Path to VDF file
            
        Raises:
            FileNotFoundError: If VDF file doesn't exist
        """
        vdf_data = parse_vdf(path)
        games = self.serializer.games_from_vdf_dict(vdf_data)
        for game in games:
            self.add_game(game)
            
    def save_games_as_vdf(self, path: Path = None):
        """Save games to a VDF file.

        The file is rewritten from scratch every time, so a timestamped copy is
        kept first: if the in-memory list is ever short of what was on disk,
        the previous shortcuts are recoverable instead of gone.

        Args:
            path (Path, optional): Output VDF file path
        """
        save_path = path if path else self.shortcuts_vdf_path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        if save_path.exists():
            self._backup_vdf(save_path)

        vdf_data = self.serializer.games_to_vdf_dict(self.games)

        # Write beside the target and swap, so an interrupted write cannot
        # leave Steam with a truncated shortcuts file.
        staging = save_path.with_suffix(save_path.suffix + ".tmp")
        write_binary_vdf(vdf_data, staging)
        staging.replace(save_path)

    def _backup_vdf(self, save_path: Path) -> Path:
        """Copy the current shortcuts file next to it, stamped with the time."""
        import shutil
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = save_path.with_name(f"{save_path.stem}.{stamp}.bak")
        shutil.copy2(save_path, backup)
        print(f"Backed up existing shortcuts to {backup}")
        return backup

    def save_game_images(self, progress_callback=None):
        """Download and save artwork for all discovered games.

        A candidate without a Steam app ID is no longer skipped: SteamGridDB
        can still find artwork by name, which is the only route for a game that
        has no Steam store page.

        Args:
            progress_callback: Optional callback for progress updates (message, progress)
        """
        total_games = len(self.game_candidates)
        if not total_games:
            if progress_callback:
                progress_callback("No artwork to download", 1.0)
            return

        for i, candidate in enumerate(self.game_candidates):
            print(
                f"Fetching artwork for {candidate.name} "
                f"(Steam ID: {candidate.steam_id}, Shortcut ID: {candidate.shortcut_id})"
            )

            def game_progress_callback(message, sub_progress, _i=i, _name=candidate.name):
                if progress_callback:
                    overall_progress = (_i + sub_progress) / total_games
                    progress_callback(f"{_name}: {message}", overall_progress)

            self.artwork_provider.fetch_for(
                shortcut_id=candidate.shortcut_id,
                steam_appid=candidate.steam_id,
                name=candidate.name,
                progress_callback=game_progress_callback if progress_callback else None,
            )

        if progress_callback:
            progress_callback("All images downloaded", 1.0)
            
    def __iter__(self):
        """Iterate over games in the repository."""
        for game in self.games:
            yield game
if __name__ == "__main__":
    stuff = NonSteamGameRepository(user_id=0)
    stuff.load_games_from_directory(Path(r"H:\Games"))
    for game in stuff:
        print(game)
        