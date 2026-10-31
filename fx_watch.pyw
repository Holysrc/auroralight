# SPDX-License-Identifier: MPL-2.0
"""Background watcher: keeps the chassis lighting on the look of the program in use. Lives in the tray (fx_tray.py);
settings are in fx_ui.py. Part of AuroraLight.

    pythonw fx_watch.pyw

Once a second it asks which program owns the active window. A program with a rule gets its look, and keeps it after
Alt-Tab to something without a rule, until it exits. Otherwise the default look shows. Only this process talks to the
controller: the window just edits auroralight.json, including a short "preview". After a long gap between ticks (a wake
from sleep) the look is sent again, twice, because the controller can lose it and USB can take a moment to come back.
Every 5 minutes it adds newly installed games to the list (fx_games.py).
Log: auroralight.log next to this file.
"""
from __future__ import annotations

import ctypes as C
import logging
import logging.handlers
import os
import sys
import threading
import time

import aw_elc
import fx_games
import fx_tray

TICK_S = 1.0
WAKE_GAP_S = 15
RESEND_AFTER_WAKE_S = 10
RETRY_S = 10
SCAN_S = 300

log = logging.getLogger("fx")


def look_of(item: dict) -> dict:
    return {k: item.get(k) for k in ("effect", "color", "color2", "speed") if item.get(k) is not None}


class Watcher:
    def __init__(self, tray: fx_tray.Tray):
        self.tray = tray
        self.cfg = aw_elc.load_config()
        self.mtime = 0.0
        self.sticky: dict | None = None           # the rule program that was last active: {"pid", "rule"}
        self.controller: aw_elc.Controller | None = None
        self.applied = None
        self.retry_at = 0.0
        self.resend_at = 0.0
        self.showing = None

    def reload(self) -> None:
        try:
            mtime = os.path.getmtime(aw_elc.CONFIG)
        except OSError:
            return
        if mtime != self.mtime:
            try:
                self.cfg = aw_elc.load_config()
                self.mtime = mtime
            except ValueError as e:
                log.error("bad config: %s", e)

    def add_new_games(self) -> None:
        """Only while the window is closed: the window keeps its own copy of the config and would overwrite this."""
        if aw_elc.window_open():
            return
        try:
            cfg = aw_elc.load_config()
            added = fx_games.add_new_games(cfg)
            if added:
                aw_elc.save_json(aw_elc.CONFIG, cfg)
                log.info("new games: %s", ", ".join(added))
        except (OSError, ValueError) as e:
            log.warning("game scan: %s", e)

    def target(self) -> tuple[str, dict]:
        cfg = self.cfg
        preview = cfg.get("preview")
        if preview and preview.get("until", 0) > time.time():
            return "preview", look_of(preview)
        pid, path = aw_elc.foreground()
        if path:
            for rule in cfg["rules"]:
                if rule.get("enabled", True) and aw_elc.rule_matches(rule, path):
                    self.sticky = {"pid": pid, "rule": rule}
                    return rule["name"], look_of(rule)
        if self.sticky:
            rule = next((r for r in cfg["rules"] if r.get("match") == self.sticky["rule"].get("match")
                         and r.get("enabled", True)), None)
            if rule and aw_elc.is_alive(self.sticky["pid"]):
                return rule["name"], look_of(rule)
            self.sticky = None
        return "default", cfg["default"]

    def send(self, wanted: tuple) -> None:
        look, brightness = wanted
        try:
            if self.controller is None:
                self.controller = aw_elc.Controller()
            self.controller.play(look, brightness)
            self.applied = wanted
            self.retry_at = 0.0
        except (aw_elc.ControllerError, OSError) as e:
            log.warning("controller: %s", e)
            if self.controller:
                self.controller.close()
                self.controller = None
            self.retry_at = time.monotonic() + RETRY_S

    def report(self, name: str, wanted: tuple) -> None:
        state = {"showing": name, "look": wanted[0], "error": self.retry_at > 0}
        if state != self.showing:
            self.showing = state
            log.info("%s -> %s", name, wanted[0])
            look = wanted[0]
            self.tray.show(None if look.get("effect") in ("spectrum", "wave") else look.get("color"), name)
            try:
                aw_elc.save_json(aw_elc.STATUS, {**state, "pid": os.getpid()})
            except OSError:
                pass

    def run(self) -> None:
        last = time.monotonic()
        next_scan = last
        while True:
            time.sleep(TICK_S)
            now = time.monotonic()
            if now >= next_scan:
                next_scan = now + SCAN_S
                self.add_new_games()
            if now - last > WAKE_GAP_S:
                log.info("woke after %.0f s", now - last)
                self.applied = None
                self.resend_at = now + RESEND_AFTER_WAKE_S
            last = now
            self.reload()
            if not self.cfg.get("enabled", True):
                self.applied = None
                continue
            name, look = self.target()
            wanted = (look, self.cfg.get("brightness", 100))
            if self.resend_at and now >= self.resend_at:
                self.resend_at = 0.0
                self.applied = None
            if wanted != self.applied and now >= self.retry_at:
                self.send(wanted)
            self.report(name, wanted)


def main() -> int:
    if "--settings" in sys.argv:                  # the built exe has both parts, this one opens the window
        import fx_ui
        fx_ui.main()
        return 0
    handler = logging.handlers.RotatingFileHandler(os.path.join(aw_elc.HERE, "auroralight.log"),
                                                   maxBytes=500_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    mutex = aw_elc.kernel32.CreateMutexW(None, False, aw_elc.MUTEX)
    if C.get_last_error() == 183:                 # ERROR_ALREADY_EXISTS: another copy is running
        return 0
    log.info("started")
    tray = fx_tray.Tray(log)
    watcher = Watcher(tray)

    def work() -> None:
        try:
            watcher.run()
        except Exception:  # noqa: BLE001
            log.exception("watcher stopped")

    threading.Thread(target=work, daemon=True).start()
    try:
        tray.run()                                # until "Exit" in the tray menu; the colour stays on the chassis
    except Exception:  # noqa: BLE001
        log.exception("tray stopped")
        return 1
    finally:
        aw_elc.kernel32.CloseHandle(mutex)
    log.info("exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
