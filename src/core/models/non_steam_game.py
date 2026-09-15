import json
from pathlib import Path

class NonSteamGame:
    
    def __init__(self,
                 id:int,
                 name:str,
                 exe:str,
                 dir:str,
                 icon:str = "",
                 ShortcutPath:str = "",
                 LaunchOptions:str = "",
                 IsHidden:int = 0,
                 AllowDesktopConfig:int = 1,
                 AllowOverlay:int = 1,
                 OpenVR:int = 0,
                 Devkit:int = 0,
                 DevkitGameID:str = "",
                 DevkitOverrideAppID:int = 0,
                 LastPlayTime:int = 0,
                 FlatpakAppID:str = "",
                 sortas:str = "",
                 tags:dict = None,
                 openvr:int = None
                 ):
        # Attribute order is the field order written back to shortcuts.vdf, so
        # it mirrors what Steam itself writes. Steam spells the VR flag
        # "openvr" in lowercase; writing "OpenVR" instead renamed the key on
        # every round-trip.
        self.appid = id
        self.AppName= name
        self.Exe = exe
        self.StartDir = dir
        self.icon = icon
        self.ShortcutPath = ShortcutPath
        self.LaunchOptions = LaunchOptions
        self.IsHidden = IsHidden
        self.AllowDesktopConfig = AllowDesktopConfig
        self.AllowOverlay = AllowOverlay
        self.openvr = OpenVR if openvr is None else openvr
        self.Devkit = Devkit
        self.DevkitGameID = DevkitGameID
        self.DevkitOverrideAppID = DevkitOverrideAppID
        self.LastPlayTime = LastPlayTime
        self.FlatpakAppID = FlatpakAppID
        # "Sort as" is a name the user set in Steam. Dropping it silently
        # renamed their shortcuts on the next write.
        self.sortas = sortas
        self.tags = {} if tags is None else tags

    @property
    def OpenVR(self):
        """Backwards-compatible alias for the lowercase ``openvr`` field."""
        return self.openvr

    @OpenVR.setter
    def OpenVR(self, value):
        self.openvr = value


    @classmethod
    def from_candidate(cls, candidate):
        """Create a NonSteamGame from a GameCandidate.

        Exe is quoted and StartDir carries a trailing separator, matching what
        Steam itself writes. Without the quotes a path containing spaces --
        "C:\\Games\\DRM Free\\..." -- is parsed as a command plus arguments and
        the shortcut fails to launch.
        """
        exe = str(candidate.exe_path)
        start_dir = str(candidate.start_dir)

        if not exe.startswith('"'):
            exe = f'"{exe}"'
        if not start_dir.endswith(("\\", "/")):
            start_dir = start_dir + "\\"

        return cls(
            id=candidate.shortcut_id,  # Use shortcut_id for the non-Steam game app ID
            name=candidate.name,
            exe=exe,
            dir=start_dir
        )
    
    def __str__(self):
        obj = {
            "name": self.AppName,
            "steamID": self.appid,
            "exe": str(self.Exe),
            "StartDir": str(self.StartDir),
        }
        return json.dumps(obj, indent=4)
     
    def as_dict(self):
        return self.__dict__