from pathlib import Path
from typing import List, Optional

from core.services.steam_search import normalize


class GameValidator:
    def __init__(self, blacklisted_dirs: set, blacklisted_exes: set):
        self.blacklisted_dirs = blacklisted_dirs
        self.blacklisted_exes = blacklisted_exes

    def is_valid_directory(self, directory: Path) -> bool:
        """Check if directory is valid for game discovery."""
        if not directory.is_dir():
            return False

        if directory.name.lower() in self.blacklisted_dirs:
            return False

        return True

    def filter_executables(self, exe_files: List[Path]) -> List[Path]:
        """Filter executables based on blacklisted keywords."""
        return [
            exe for exe in exe_files
            if not any(skip in exe.name.lower() for skip in self.blacklisted_exes)
        ]

    def find_main_executable(
        self,
        valid_exes: List[Path],
        game_name: str,
        root: Optional[Path] = None,
    ) -> Path:
        """Find the most likely main executable for a game.

        Args:
            valid_exes: Executables that survived the blacklist.
            game_name: Name to match against, usually the folder name.
            root: Directory the scan started from. When given, executables
                nearer the top win ties -- a game's launcher sits at the root
                while engine binaries and crash handlers hide several levels
                down, and those are often the larger files.
        """
        if not valid_exes:
            raise ValueError("No valid executables found")

        for exe in valid_exes:
            # First priority: exact name match
            if exe.stem.lower() == game_name.lower():
                return exe

        for exe in valid_exes:
            # Second priority: match once punctuation and spacing are ignored,
            # so "Stalker2.exe" still matches a "S.T.A.L.K.E.R. 2" folder.
            if normalize(exe.stem) == normalize(game_name):
                return exe

        def safe_get_size(file_path: Path) -> int:
            try:
                return file_path.stat().st_size
            except (OSError, PermissionError):
                return 0  # Return 0 if we can't access the file

        def depth(file_path: Path) -> int:
            if root is None:
                return 0
            try:
                return len(file_path.relative_to(root).parts)
            except ValueError:
                return 0

        # Third priority: shallowest, then biggest.
        return min(valid_exes, key=lambda exe: (depth(exe), -safe_get_size(exe)))
