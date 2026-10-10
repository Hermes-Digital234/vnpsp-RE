# vnpsp-RE

A VNDS (Visual Novel DS) interpreter for the Sony PSP. Play VNDS visual novels on a PSP, PPSSPP, or a PS Vita running Adrenaline.

**Status:** pre-release. The current build is closed source. The asset converter is open source.

## Compatibility

| Platform | Status |
|----------|--------|
| PPSSPP | Works. add it as homebrew, not as a game |
| PSP slim/3000/Go/Street (64 MB, custom firmware) | Works |
| PS Vita (via Adrenaline) | Works |
| PSP-1000 (32 MB) | Currently untested. Audio-heavy games may run out of memory and crash. |

If PPSSPP crashes while skipping text, turn off Fast Memory Access in its settings.

## What you need

- A device from the table above
- Your own VNDS game files. No games are included, and none are linked here.
- Python 3 and ffmpeg (on your PATH) to run the converter

## Setup

1. Convert your game:
```
   python convert_assets.py <path to game directory>
```
2. On your PSP, create the folder `/PSP/GAME/vnds-RE/`.
3. Copy `EBOOT.PBP` (from the releases page) into that folder, alongside the folder with the converted game.
4. Launch it. If only one game is found, it starts automatically.

## Controls

| Button | Action |
|--------|--------|
| Cross | Next line / select |
| Circle | Cancel |
| Square | Backlog |
| Triangle | Fast forward |
| L | D-pad down |
| R | Next line / select |

*L/R were added to play with a psp go while its closed

## Notes

- Updates during pre-release may break save files.
- Found a bug? Please open an issue and say which device or emulator you used and which game.
- Bug fixes are welcome as pull requests, but please open an issue first. I'm not accepting new feature PRs for now.
- License: BSD 2-Clause (see `LICENSE`).

## Development

The current pre-release was written for myself, just to get things working, which is why its source is still closed. I'm now rewriting it from scratch on the `Rewrite` branch (BSD 2-Clause) with the goal of making it clean, expandable and easy to port to other platforms. The rewrite doesn't run yet, so use the pre-release from the releases page for now.
