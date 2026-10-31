# SPDX-License-Identifier: MPL-2.0
"""Settings window for the chassis lighting: default look, brightness, a look per program. Starts the watcher if needed.

    pythonw fx_ui.pyw

Every change is saved to auroralight.json straight away and the watcher picks it up within a second.
"""
from __future__ import annotations

import ctypes as C
import json
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import aw_elc
import fx_games

EFFECT_NAMES = aw_elc.EFFECTS
EFFECT_IDS = {v: k for k, v in EFFECT_NAMES.items()}
SPEED_NAMES = {"slow": "Slow", "medium": "Medium", "fast": "Fast"}
SPEED_IDS = {v: k for k, v in SPEED_NAMES.items()}
NEEDS_COLOR2 = {"morph"}
NO_COLOR = {"spectrum", "wave"}
STATIC = {"static"}
AWCC_PROCESSES = ("alienfxsubagent.exe", "awcc.ucsubagent.exe")


def running_processes() -> set[str]:
    out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True,
                         creationflags=subprocess.CREATE_NO_WINDOW).stdout
    return {line.split('","')[0].strip('"').lower() for line in out.splitlines() if line}


def start_watcher() -> None:
    mutex = aw_elc.kernel32.CreateMutexW(None, False, aw_elc.MUTEX)
    exists = C.get_last_error() == 183
    aw_elc.kernel32.CloseHandle(mutex)
    if not exists:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        subprocess.Popen([pyw, os.path.join(aw_elc.HERE, "fx_watch.pyw")], cwd=aw_elc.HERE,
                         creationflags=subprocess.DETACHED_PROCESS)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = aw_elc.load_config()
        root.title("AuroraLight")
        root.geometry("860x600")
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(root)
        top.pack(fill="x", **pad)
        self.enabled = tk.BooleanVar(value=self.cfg.get("enabled", True))
        ttk.Checkbutton(top, text="Control the lighting", variable=self.enabled, command=self.on_enabled).pack(side="left")
        ttk.Label(top, text="Brightness").pack(side="left", padx=(20, 4))
        self.brightness = tk.IntVar(value=self.cfg.get("brightness", 100))
        scale = ttk.Scale(top, from_=0, to=100, length=200, variable=self.brightness)
        scale.pack(side="left")
        scale.bind("<ButtonRelease-1>", lambda _: self.on_brightness())
        self.bright_label = ttk.Label(top, width=5, text=f"{self.brightness.get()}%")
        self.bright_label.pack(side="left")
        ttk.Button(top, text="Default look…", command=self.edit_default).pack(side="right")

        self.status = ttk.Label(root, anchor="w")
        self.status.pack(fill="x", **pad)
        self.warning = ttk.Label(root, anchor="w", foreground="#B00020")
        self.warning.pack(fill="x", padx=8)

        table = ttk.Frame(root)
        table.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(table, columns=("look", "match"), selectmode="browse")
        self.tree.heading("#0", text="Program")
        self.tree.heading("look", text="Look")
        self.tree.heading("match", text="Tracked as")
        self.tree.column("#0", width=270)
        self.tree.column("look", width=210)
        self.tree.column("match", width=340)
        bar = ttk.Scrollbar(table, command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _: self.edit_selected())

        buttons = ttk.Frame(root)
        buttons.pack(fill="x", **pad)
        for text, cmd in (("Edit…", self.edit_selected), ("Preview", self.preview_selected),
                          ("Remove", self.delete_selected)):
            ttk.Button(buttons, text=text, command=cmd).pack(side="left", padx=(0, 6))
        for text, cmd in (("Find games", self.find_games), ("Choose exe…", self.add_exe),
                          ("From running…", self.add_running)):
            ttk.Button(buttons, text=text, command=cmd).pack(side="right", padx=(6, 0))

        self.swatches: dict[str, tk.PhotoImage] = {}
        if fx_games.add_new_games(self.cfg):
            self.save()
        self.fill()
        start_watcher()
        self.tick()

    # --- storage ---

    def save(self) -> None:
        aw_elc.save_json(aw_elc.CONFIG, self.cfg)

    def swatch(self, color: str) -> tk.PhotoImage:
        if color not in self.swatches:
            img = tk.PhotoImage(width=16, height=16)
            img.put(color, to=(0, 0, 16, 16))
            self.swatches[color] = img
        return self.swatches[color]

    def describe(self, item: dict) -> str:
        effect = item.get("effect", "static")
        text = EFFECT_NAMES.get(effect, effect)
        if effect not in NO_COLOR:
            text += f" {item.get('color', '')}"
        if effect in NEEDS_COLOR2:
            text += f" → {item.get('color2', '')}"
        if effect not in STATIC:
            text += f", {SPEED_NAMES.get(item.get('speed', 'medium'), '').lower()}"
        return text

    def fill(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.cfg["rules"].sort(key=lambda r: r["name"].lower())
        for i, rule in enumerate(self.cfg["rules"]):
            self.tree.insert("", "end", iid=str(i), text=" " + rule["name"], image=self.swatch(rule.get("color", "#000000")),
                             values=(self.describe(rule), rule.get("match", "")))

    def selected(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("AuroraLight", "Select a row in the list first.")
            return None
        return self.cfg["rules"][int(sel[0])]

    # --- actions ---

    def on_enabled(self) -> None:
        self.cfg["enabled"] = self.enabled.get()
        self.save()

    def on_brightness(self) -> None:
        self.cfg["brightness"] = int(self.brightness.get())
        self.bright_label.config(text=f"{self.cfg['brightness']}%")
        self.save()

    def preview(self, look: dict) -> None:
        self.cfg["preview"] = {**look, "until": time.time() + 8}
        self.save()

    def preview_selected(self) -> None:
        rule = self.selected()
        if rule:
            self.preview({k: rule[k] for k in ("effect", "color", "color2", "speed") if k in rule})

    def delete_selected(self) -> None:
        rule = self.selected()
        if rule and messagebox.askyesno("AuroraLight", f"Remove \"{rule['name']}\" from the list?"):
            self.cfg["rules"].remove(rule)
            self.cfg.setdefault("ignored", []).append(rule.get("match", ""))   # or the watcher adds a game back
            self.save()
            self.fill()

    def edit_selected(self) -> None:
        rule = self.selected()
        if rule:
            self.edit_look(rule["name"], rule, self.fill)

    def edit_default(self) -> None:
        self.edit_look("Default look (when no listed program is active)", self.cfg["default"], lambda: None)

    def edit_look(self, title: str, item: dict, done) -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        state = {"color": item.get("color", "#00F0F0"), "color2": item.get("color2", "#000000")}
        effect = tk.StringVar(value=EFFECT_NAMES.get(item.get("effect", "static")))
        speed = tk.StringVar(value=SPEED_NAMES.get(item.get("speed", "medium")))

        ttk.Label(win, text=title, wraplength=380).grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 6), sticky="w")
        ttk.Label(win, text="Look").grid(row=1, column=0, padx=10, pady=4, sticky="w")
        box = ttk.Combobox(win, textvariable=effect, values=list(EFFECT_IDS), state="readonly", width=24)
        box.grid(row=1, column=1, columnspan=2, padx=10, sticky="w")
        labels, chips = {}, {}

        def pick(key: str) -> None:
            chosen = colorchooser.askcolor(state[key], parent=win)[1]
            if chosen:
                state[key] = chosen.upper()
                chips[key].config(background=state[key])

        for row, key, text in ((2, "color", "Color"), (3, "color2", "Second color")):
            labels[key] = ttk.Label(win, text=text)
            labels[key].grid(row=row, column=0, padx=10, pady=4, sticky="w")
            chips[key] = tk.Button(win, background=state[key], width=8, relief="groove", command=lambda k=key: pick(k))
            chips[key].grid(row=row, column=1, padx=10, sticky="w")
        speed_label = ttk.Label(win, text="Speed")
        speed_label.grid(row=4, column=0, padx=10, pady=4, sticky="w")
        speed_box = ttk.Combobox(win, textvariable=speed, values=list(SPEED_IDS), state="readonly", width=14)
        speed_box.grid(row=4, column=1, padx=10, sticky="w")

        def result() -> dict:
            eff = EFFECT_IDS[effect.get()]
            return {"effect": eff, "color": state["color"], "color2": state["color2"], "speed": SPEED_IDS[speed.get()]}

        def refresh(*_) -> None:
            eff = EFFECT_IDS[effect.get()]
            for key, show in (("color", eff not in NO_COLOR), ("color2", eff in NEEDS_COLOR2)):
                for w in (labels[key], chips[key]):
                    w.grid() if show else w.grid_remove()
            for w in (speed_label, speed_box):
                w.grid() if eff not in STATIC else w.grid_remove()

        def ok() -> None:
            item.update(result())
            self.cfg.pop("preview", None)
            self.save()
            done()
            win.destroy()

        box.bind("<<ComboboxSelected>>", refresh)
        refresh()
        row = ttk.Frame(win)
        row.grid(row=5, column=0, columnspan=3, padx=10, pady=10, sticky="e")
        ttk.Button(row, text="Preview", command=lambda: self.preview(result())).pack(side="left", padx=4)
        ttk.Button(row, text="Save", command=ok).pack(side="left", padx=4)
        ttk.Button(row, text="Cancel", command=win.destroy).pack(side="left", padx=4)

    def add_rule(self, name: str, match: str) -> bool:
        target = aw_elc.norm_path(match)
        if any(aw_elc.norm_path(r.get("match", "")) == target for r in self.cfg["rules"]):
            return False
        self.cfg["rules"].append({"name": fx_games.tidy_name(name), "match": match, "effect": "static",
                                  "color": fx_games.known_color(self.cfg, name)})
        return True

    def add_exe(self) -> None:
        path = filedialog.askopenfilename(title="Program", filetypes=[("Programs", "*.exe")])
        if path:
            name = os.path.splitext(os.path.basename(path))[0]
            if self.add_rule(name, os.path.basename(path)):
                self.save()
                self.fill()

    def add_running(self) -> None:
        programs = aw_elc.windowed_programs()
        win = tk.Toplevel(self.root)
        win.title("Running programs")
        win.transient(self.root)
        win.grab_set()
        names = sorted(programs)
        lst = tk.Listbox(win, width=50, height=18)
        for n in names:
            lst.insert("end", n)
        lst.pack(padx=10, pady=10, fill="both", expand=True)

        def ok(*_) -> None:
            sel = lst.curselection()
            if sel:
                exe = names[sel[0]]
                if self.add_rule(os.path.splitext(exe)[0], exe):
                    self.save()
                    self.fill()
            win.destroy()

        lst.bind("<Double-1>", ok)
        ttk.Button(win, text="Add", command=ok).pack(pady=(0, 10))

    def find_games(self) -> None:
        added = fx_games.add_new_games(self.cfg, restore_ignored=True)
        self.save()
        self.fill()
        messagebox.showinfo("AuroraLight", f"New games: {len(added)}" + ("\n\n" + "\n".join(added) if added else ""))

    # --- status line ---

    def tick(self) -> None:
        try:
            with open(aw_elc.STATUS, encoding="utf-8") as f:
                s = json.load(f)
            line = f"Now: {s['showing']} — {self.describe(s['look'])}"
            if s.get("error"):
                line += " (the controller is not answering, retrying)"
        except (OSError, ValueError, KeyError):
            line = "Now: starting…"
        self.status.config(text=line if self.enabled.get() else "Not controlling the lighting")
        self.bright_label.config(text=f"{int(self.brightness.get())}%")
        conflict = running_processes() & set(AWCC_PROCESSES)
        self.warning.config(text="Alienware Command Center is running and may override the colors." if conflict else "")
        self.root.after(1500, self.tick)


def main() -> None:
    mutex = aw_elc.kernel32.CreateMutexW(None, False, aw_elc.WINDOW_MUTEX)
    if C.get_last_error() == 183:                 # already open: bring it forward, two windows would overwrite each other
        window = C.windll.user32.FindWindowW(None, "AuroraLight")
        if window:
            C.windll.user32.ShowWindow(window, 9)
            C.windll.user32.SetForegroundWindow(window)
        return
    try:
        C.windll.shcore.SetProcessDpiAwareness(1)
    except OSError:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
    aw_elc.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
