<p align="center">
<img src="docs/media/steamshelf2.png" alt="logo" width="200">
</p>

# Steam Shelf

Steam Shelf is a tool that automates the process of adding collections of ~~legally obtained~~ games to your Steam library as non-steam games. Simply point it to your games directory, and it will add them all, automatically fetching and applying the official Steam artworks.

<p align="left">
<img src="docs/media/Screenshot 2025-09-23 131156.png" alt="screenshot" width="200">
</p>

## ✨Features

- Batch Import: Scans a directory and adds all discovered games to Steam in one click.
- Automatic Artwork Curation: Automatically fetches high-quality official artwork (Portrait, Hero, Logo, and Capsule) for each game.
- Smart Game Matching: Uses folder names to intelligently find the correct corresponding Steam game for accurate artwork matching.

- Dual Interface: Choose between a GUI or a CLI tool.

- Standalone Executable: No installation required; just download and run the .exe.


## 🚀Usage
### Folder Naming

Steam Shelf looks each folder up through Steam's own store search, which does the
fuzzy matching itself. The folder name has to be *recognisable*, not exact:
`STALKER2` resolves to `S.T.A.L.K.E.R. 2: Heart of Chornobyl` with nothing renamed.
Version tags and bracketed noise (`[GOG]`, `v1.32`, `Repack`) are stripped before the
search.

A folder Steam cannot identify is **not dropped**. It is listed with its folder name,
flagged as unconfirmed, and you pick the right game from a dropdown or search for it by
hand. That is also how you correct a wrong guess.

| Folder name | Resolves to |
| :--- | :--- |
| `Alien Isolation` | `Alien: Isolation` |
| `STALKER2` | `S.T.A.L.K.E.R. 2: Heart of Chornobyl` |
| `Half-Life 2 Episode One` | `Half-Life 2: Episode One` |

### Artwork

Artwork comes from [SteamGridDB](https://www.steamgriddb.com) first, falling back to
Steam's own CDN. SteamGridDB needs a free API key, read from the `STEAMGRIDDB_API_KEY`
environment variable. Without it the tool still runs and uses the CDN alone -- which
means games with no Steam store page get no artwork.

### GUI
Just download and run steam shelf from the [releases](https://github.com/the-sofishticated-man/steam-shelf/releases)

### CLI (From Source)
start by cloning this repo:
```
git clone https://github.com/the-sofishticated-man/steam-shelf
cd steam-shelf
```
install all the dependancies:
```
pip install -r requirements.txt
```
then run the CLI script:
```
./scripts/steam-shelf.bat discover /path/to/your/game/directory
```
or:
```
python ./scripts/steam-shelf.py
```
**Note**: the CLI tool currently does not have support for changing a game's default path, so essentially you're stuck with what it *guesses* the executable is.

## 🤝 Contributing
Contributions are welcome. If you want to improve Steam Shelf, here's how to get started.

    1. Fork the repo
    2. Create a feature branch (`git checkout -b feature/your-feature`)
    3. Commit your changes (`git commit -m 'Add your feature'`)
    4. Push to the branch (`git push origin feature/your-feature`)
    5. Open a Pull Request


## Roadmap
Probably gonna add some more features in the future.

- [ ]  More metadata support (description, tags).
- [ ]  Icon fetching support.
- [ ]  Better UI (I have 0 artistic sense, sorry not sorry).
- [ ]  Functionality for changing executable paths in the CLI.
- [ ]  Cross-Platform support (Linux, MacOS).




## 📃License

This project is licensed under the [MIT License](https://choosealicense.com/licenses/mit/)


## ⚠️Disclaimer
Steam Shelf is not affiliated with Valve or Steam, PLEASE DON'T SUE ME.

Oh yea should probably also mention this is for **educational purposes only**.
