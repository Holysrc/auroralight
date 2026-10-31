# SPDX-License-Identifier: MPL-2.0
"""One-time import from Command Center into auroralight.json: its per-game colours and its game list.

    python import_awcc.py

Run it before removing Command Center. Reads a copy of its database, changes nothing of its own. Games get their
folder as the rule when a launcher manifest knows them (fx_games.scan_games), otherwise their exe name, because Xbox
folders change with every update. Entries whose exe no longer exists are dropped. So is "Sunderfolk", which Command
Center had pointed at Outlook (olk.exe).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile

import aw_elc
import fx_games

BASE = os.path.expandvars(r"%LOCALAPPDATA%\Alienware\Alienware Command Center")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "fx.db")
        shutil.copy(os.path.join(BASE, "FX", "FXRepository.db"), copy)
        db = sqlite3.connect(copy)
        colors = {name: "#" + color[-6:].upper() for name, color in db.execute("select Name, DefaultColor from GameInfoFX")
                  if name != "System Default"}
        db.close()
    with open(os.path.join(BASE, "GameLibrary", "GameLibrary.json"), encoding="utf-8-sig") as f:
        library = json.load(f)["Games"]

    cfg = aw_elc.load_config()
    known = cfg.setdefault("known_colors", {})
    for g in library:
        art = g.get("FanArtColors") or []
        if g["Title"] not in colors and len(art) > 1:
            colors[g["Title"]] = "#" + art[1][-6:].upper()
    known.update(colors)

    rules, have, folders = [], set(), set()
    for name, folder in fx_games.scan_games():
        key, place = fx_games.name_key(name), aw_elc.norm_path(folder)
        if os.path.isdir(folder) and key not in have and place not in folders:
            have.add(key)
            folders.add(place)
            rules.append({"name": fx_games.tidy_name(name), "match": folder, "effect": "static",
                          "color": fx_games.known_color(cfg, name)})
    for g in library:
        exe = aw_elc.norm_path(g.get("ExePath") or "")
        key = fx_games.name_key(g["Title"])
        if key in have or not exe or exe.endswith("\\olk.exe") or not os.path.exists(exe):
            continue
        have.add(key)
        rules.append({"name": fx_games.tidy_name(g["Title"]), "match": exe.rsplit("\\", 1)[-1], "effect": "static",
                      "color": fx_games.known_color(cfg, g["Title"])})
    old = {aw_elc.norm_path(r.get("match", "")) for r in rules}
    rules += [r for r in cfg["rules"] if aw_elc.norm_path(r.get("match", "")) not in old]
    cfg["rules"] = rules
    aw_elc.save_json(aw_elc.CONFIG, cfg)
    print(f"known colours {len(known)}, rules {len(rules)}")
    for r in sorted(rules, key=lambda x: x["name"].lower()):
        print(f"  {r['color']} {r['name']} <- {r['match']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
