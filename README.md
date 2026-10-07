# vnpsp-RE
A vnds interpreter for the sony psp.

This interpreter works on 64mb psp's and ppsspp.
I have not tested with a real psp 1000 but it worked in ppsspp with 32mb's of ram.
In games with large sound assets the psp 1000 might run out of ram and crash.

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
