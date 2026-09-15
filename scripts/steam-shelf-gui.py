#!/usr/bin/env python3
"""Steam Shelf GUI entry point."""

import subprocess
import sys
import time
from pathlib import Path

# Add src to path for imports
# Handle both development and PyInstaller environments
if not getattr(sys, 'frozen', False):
    # Running in development - add src to path
    src_path = Path(__file__).parent.parent / "src"
    sys.path.insert(0, str(src_path))

from gui.main_window import SteamShelfGUI

GRACEFUL_EXIT_TIMEOUT = 30


def steam_is_running() -> bool:
    """Whether a Steam client process is currently up."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
            capture_output=True, text=True, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return "steam.exe" in result.stdout.lower()


def request_steam_exit() -> bool:
    """Ask Steam to close, and wait for it.

    Steam rewrites shortcuts.vdf when it exits, so it has to be closed before
    Steam Shelf writes to that file. It is asked, not killed: a forced kill can
    interrupt a download or lose in-progress game state.

    Returns:
        True when Steam is no longer running.
    """
    if not steam_is_running():
        return True

    print("Asking Steam to close...")
    try:
        subprocess.run(["cmd", "/c", "start", "", "steam://exit"],
                       capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Could not send the exit request to Steam: {exc}")

    deadline = time.time() + GRACEFUL_EXIT_TIMEOUT
    while time.time() < deadline:
        if not steam_is_running():
            print("Steam closed.")
            return True
        time.sleep(1)

    return not steam_is_running()


def ensure_steam_closed() -> bool:
    """Close Steam with the user's consent. Returns whether to continue."""
    if not steam_is_running():
        return True

    import tkinter as tk
    from tkinter import messagebox

    prompt = tk.Tk()
    prompt.withdraw()
    try:
        agreed = messagebox.askokcancel(
            "Steam needs to close",
            "Steam is running.\n\n"
            "Steam overwrites its shortcuts file when it exits, so it has to be "
            "closed before Steam Shelf can add games.\n\n"
            "Close Steam now? Finish any download or game first.",
        )
        if not agreed:
            return False

        if not request_steam_exit():
            messagebox.showerror(
                "Steam is still running",
                "Steam did not close within 30 seconds.\n\n"
                "Close it yourself, then start Steam Shelf again.",
            )
            return False
    finally:
        prompt.destroy()

    return True


if __name__ == "__main__":
    if not ensure_steam_closed():
        print("Aborted: Steam is still running.")
        raise SystemExit(1)

    app = SteamShelfGUI()
    app.run()
