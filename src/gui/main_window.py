import tkinter as tk
from gui.utils.user_selection import UserSelectionFrame
from gui.widgets.games_display import GamesDisplayFrame
from gui.widgets.current_games import CurrentGamesFrame
from gui.widgets.loading_screen import LoadingScreen
from gui.utils.threading_utils import ThreadManager
from core.models.repository import NonSteamGameRepository
from core.services.steam_db_utils import SteamDatabase
from steamclient import get_users
import threading


class SteamShelfGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.main_user = None
        self.chosen_directory = None
        self.steam_repo = None
        self.users = None  # Will be loaded after sync
        self.steam_db = SteamDatabase()
        
        # Initialize thread manager
        self.thread_manager = ThreadManager(self.root)
        
        # UI Components
        self.loading_screen = None
        self.user_selection = None
        self.current_games = None
        self.games_display = None
        
        self.setup_window()
        self.show_loading()
    
    def setup_window(self):
        """Initialize the main window."""
        self.root.title("Steam Shelf - Initializing")
        self.root.geometry("600x900")
        self.root.configure(bg='#2a2a2a')
        
        # Set custom icon - just put icon.ico in your project root
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass  # Use default icon if file not found
    
    def show_loading(self):
        """Show loading screen while Steam users are read."""
        # Create and show loading screen
        self.loading_screen = LoadingScreen(self.root)
        self.loading_screen.show()

        # Look up Steam users in a separate thread
        startup_thread = threading.Thread(target=self.perform_startup, daemon=True)
        startup_thread.start()

    def perform_startup(self):
        """Load Steam users.

        There is no database to synchronise any more: Steam removed the bulk
        app-list endpoint, and names are resolved on demand instead. Startup is
        now just reading the local Steam users, which is fast.
        """
        try:
            self.root.after(
                0, lambda: self.loading_screen.update_progress(40, "Reading Steam users...")
            )
            self.users = get_users()

            if not self.users:
                raise RuntimeError(
                    "No Steam users found. Sign in to Steam at least once, then reopen Steam Shelf."
                )

            self.root.after(
                0, lambda: self.loading_screen.update_progress(100, "Ready")
            )
            self.root.after(0, self.transition_to_user_selection)

        except Exception as e:
            # A startup failure must stop the flow, not let the user continue
            # into an interface that cannot work.
            message = str(e)
            print(f"Startup error: {message}")
            self.root.after(0, lambda: self._fail_startup(message))

    def _fail_startup(self, message: str):
        """Report a fatal startup problem and close."""
        from tkinter import messagebox

        self.loading_screen.update_progress(0, "Startup failed")
        messagebox.showerror("Steam Shelf could not start", message)
        self.root.destroy()
    
    def transition_to_user_selection(self):
        """Transition from loading screen to user selection."""
        # Hide and destroy loading screen
        self.loading_screen.hide()
        self.loading_screen.destroy()
        
        # Update window title
        self.root.title("Steam Shelf - User Selection")
        
        # Create user selection interface
        self.create_user_selection_interface()
    
    def create_user_selection_interface(self):
        """Create the user selection interface."""
        self.user_selection = UserSelectionFrame(
            self.root, 
            self.users, 
            self.on_user_selected
        )

    def on_user_selected(self, user):
        """Handle user selection and proceed to next step."""
        self.main_user = user
        # Pass the already-synced database to the repository
        self.steam_repo = NonSteamGameRepository(
            self.main_user.id, 
            discovery_service=None  # Will create with synced database
        )
        # Update the discovery service to use our synced database
        from core.services.game_discovery import GameDiscoveryService
        from core.services.game_validator import GameValidator
        
        from core.models.repository import BLACKLISTED_DIRECTORIES, BLACKLISTED_EXECUTABLES

        validator = GameValidator(BLACKLISTED_DIRECTORIES, BLACKLISTED_EXECUTABLES)

        self.steam_repo.discovery_service = GameDiscoveryService(
            self.steam_db,  # Shared resolution cache
            validator,
            added_games={game.AppName for game in self.steam_repo.games},
            added_executables={game.Exe for game in self.steam_repo.games},
        )
        
        # Hide user selection frame
        self.user_selection.hide()
        
        # Show main interface
        self.show_main_interface()

    def show_main_interface(self):
        """Show the main interface after user selection."""
        # Create current games display
        self.current_games = CurrentGamesFrame(self.root, self.steam_repo)
        
        # Create games discovery and addition interface
        self.games_display = GamesDisplayFrame(
            self.root, 
            self.steam_repo, 
            self.on_directory_chosen,
            self.thread_manager  # Pass thread manager
        )
        
        # Set callback for when games are added
        self.games_display.set_on_games_added_callback(self.on_games_added)

    def on_directory_chosen(self, directory):
        """Handle when a directory is chosen for scanning."""
        self.chosen_directory = directory

    def on_games_added(self):
        """Handle when games are successfully added to Steam."""
        # Refresh the current games display to show newly added games
        if self.current_games:
            self.current_games.refresh()

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()
