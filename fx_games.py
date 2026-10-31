# SPDX-License-Identifier: MPL-2.0
"""Installed games from the launchers' own records (Steam, Epic, GOG) and adding the new ones to the config.

A game is tracked by its folder, so any exe inside it counts. One the user removed from the list goes to `ignored` and
does not come back on its own; the "Find games" button restores those too.
"""
from __future__ import annotations

import colorsys
import glob
import hashlib
import json
import os
import re
import winreg

import aw_elc

STEAM_SKIP = re.compile(r"redistributable|proton|steam linux runtime|steamvr|soundtrack", re.I)
EPIC_MANIFESTS = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests\*.item"
GOG_KEY = r"SOFTWARE\WOW6432Node\GOG.com\Games"


def hash_color(name: str) -> str:
    """A steady bright colour for a game that came with no colour of its own."""
    hue = int(hashlib.sha1(name.encode()).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def tidy_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[®™©]", "", name)).strip()


def name_key(name: str) -> str:
    """Launchers and Command Center spell the same game differently: "Tycoon® 3" and "Tycoon 3"."""
    return re.sub(r"[^\w]", "", tidy_name(name)).casefold()


def known_color(cfg: dict, name: str) -> str:
    colors = {name_key(k): v for k, v in cfg.get("known_colors", {}).items()}
    return colors.get(name_key(name)) or hash_color(tidy_name(name))


def epic_games() -> list[tuple[str, str]]:
    found = []
    for item in glob.glob(EPIC_MANIFESTS):
        try:
            with open(item, encoding="utf-8") as f:
                m = json.load(f)
            found.append((m["DisplayName"], m["InstallLocation"]))
        except (OSError, ValueError, KeyError):
            pass
    return found


def steam_libraries() -> list[str]:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            root = winreg.QueryValueEx(key, "SteamPath")[0]
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as f:
            return [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"(.+?)"', f.read())]
    except OSError:
        return []


def steam_games() -> list[tuple[str, str]]:
    found = []
    for lib in steam_libraries():
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                with open(acf, encoding="utf-8") as f:
                    text = f.read()
                name = re.search(r'"name"\s+"(.+?)"', text).group(1)
                folder = re.search(r'"installdir"\s+"(.+?)"', text).group(1)
            except (OSError, AttributeError):
                continue
            if not STEAM_SKIP.search(name):
                found.append((name, os.path.join(lib, "steamapps", "common", folder)))
    return found


def gog_games() -> list[tuple[str, str]]:
    found = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GOG_KEY) as games:
            for i in range(winreg.QueryInfoKey(games)[0]):
                try:
                    with winreg.OpenKey(games, winreg.EnumKey(games, i)) as game:
                        found.append((winreg.QueryValueEx(game, "gameName")[0], winreg.QueryValueEx(game, "path")[0]))
                except OSError:
                    pass
    except OSError:
        pass
    return found


def scan_games() -> list[tuple[str, str]]:
    """(name, folder); the shortest name first, so that a game comes before its add-ons in the same folder."""
    return sorted(epic_games() + steam_games() + gog_games(), key=lambda g: len(g[0]))


def add_new_games(cfg: dict, restore_ignored: bool = False) -> list[str]:
    """Adds games not in the list yet to `cfg` and returns their names. Saving is up to the caller."""
    ignored = {aw_elc.norm_path(p) for p in cfg.get("ignored", [])}
    have = {aw_elc.norm_path(r.get("match", "")) for r in cfg["rules"]}
    added = []
    for name, folder in scan_games():
        place = aw_elc.norm_path(folder)
        if place in have or (place in ignored and not restore_ignored) or not os.path.isdir(folder):
            continue
        have.add(place)
        cfg["rules"].append({"name": tidy_name(name), "match": folder, "effect": "static",
                             "color": known_color(cfg, name)})
        added.append(tidy_name(name))
    if restore_ignored:
        cfg["ignored"] = []
    return added
