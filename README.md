# AuroraLight

**Per-game chassis lighting for the Alienware Aurora, without Alienware Command Center.**

AuroraLight gives every game and program its own color and effect. It sits in the tray, uses about 30 MB of memory, and needs no drivers, Python or administrator rights.

## Features

- **Lighting that follows what you use.** The look changes with the active window and stays through Alt-Tab until the program closes.
- **Six looks:** solid color, breathe, pulse, morph between two colors, spectrum and wave, with adjustable brightness and speed.
- **Games add themselves.** Steam, Epic and GOG games appear in the list within 5 minutes of installing. Any other program can be added from the settings window.
- **Tray icon in the current color.** Click it for settings, right-click for the menu.
- **Built to survive sleep.** The look is sent again after a wake from sleep or hibernation.
- **Bring your Command Center colors.** A one-time import copies its game colors before you uninstall it.

## Compatibility

Built for and tested on one machine: an **Alienware Aurora ACT1250** with the AW-ELC lighting controller (USB `187C:0550`, firmware 1.1.12) on Windows 11.

Waking from hibernation and detecting a freshly installed game have not been tested on real use yet, so reports are welcome.

Other models with this controller may work, but their LEDs can be numbered differently. See `LEDS` in `aw_elc.py`, and test before relying on it. To check your controller:

```bash
python aw_elc.py status
```

## Getting started

1. Download [AuroraLight-windows-x64.zip](https://github.com/Holysrc/auroralight/releases/latest/download/AuroraLight-windows-x64.zip) and unpack it anywhere. You don't need Python.
2. Close or uninstall Alienware Command Center, because it overrides the colors while it runs.
3. Run `AuroraLight.exe`.
4. To start it with Windows, put a shortcut to it in the `shell:startup` folder.

The exe is not code-signed, so Windows SmartScreen may warn you the first time. Choose **More info**, then **Run anyway**, or build it yourself from the source.

### Running from source

You need [Python](https://www.python.org/downloads/) 3.10 or newer with Tkinter, which the standard Windows installer includes.

```bash
pythonw fx_watch.pyw
```

To build the exe yourself:

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

### Keeping your Command Center colors

This one-time import needs the source and Python, and must run while Command Center is still installed. It writes next to the scripts, so copy the resulting `auroralight.json` to `%LOCALAPPDATA%\AuroraLight` if you use the exe.

```bash
python import_awcc.py
```

## Using it

Click the tray icon to open the settings window. Double-click a row to change its look, and use **Preview** to try it on the chassis for a few seconds.

| Button | What it does |
|---|---|
| **Default look…** | Sets the look used when no listed program is active |
| **Find games** | Scans right away and brings back games you removed |
| **Choose exe…** | Adds a program by picking its file |
| **From running…** | Adds a program that has a window open right now |
| **Remove** | Removes a program from the list; a removed game does not come back on its own |

Xbox and other store games are not found automatically, so add them with **From running…** or **Choose exe…**.

Settings are stored in `auroralight.json` and the log in `auroralight.log`. The exe keeps both in `%LOCALAPPDATA%\AuroraLight`; when run from source they sit next to the scripts.

## Limitations

- **Windows only.**
- **The whole chassis shows one look.** Separate zones are not supported.
- **Changes take about 2 seconds,** because the controller needs pauses between commands. That rules out effects that react to the action on screen.
- **Fans are not controlled.** Your BIOS keeps managing them, but Command Center's thermal profiles are gone if you uninstall it.

## Files

| File | Purpose |
|---|---|
| `fx_watch.pyw` | Background program: watches the active window and sets the lighting |
| `fx_ui.py` | Settings window |
| `fx_tray.py` | Tray icon |
| `fx_games.py` | Finds installed games |
| `aw_elc.py` | Talks to the controller through `hid.dll` and holds shared code; also a small command line tool |
| `import_awcc.py` | One-time import from Command Center |
| `build.ps1` | Builds `AuroraLight.exe` with PyInstaller |

## Credits

The controller's commands are documented by [alien-lights](https://github.com/JakeLaney/alien-lights) and [OpenRGB](https://gitlab.com/CalcProgrammer1/OpenRGB). Thanks to both projects.

AuroraLight is an independent project, not affiliated with or endorsed by Dell or Alienware. Alienware is a trademark of Dell Inc.

## License

[Mozilla Public License 2.0](LICENSE)
