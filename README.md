# vnpsp-RE
A vnds interpreter for the sony psp.

To use this you have to supply your own vnds games.

Games have to be converted before they are playable.
To convert a game run the following command:

```bash
python convert_assets.py <path to game directory>
```

Then on your psp you need to create the following directory:

```
/PSP/GAME/vnds-RE/
```

Then you put the eboot.pbp in that directory alongside the converted game.

If only 1 game is detected it will automatically launch that one.
