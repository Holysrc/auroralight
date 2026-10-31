# SPDX-License-Identifier: MPL-2.0
"""AuroraLight: Alienware AW-ELC chassis lighting (USB 187C:0550) from Windows, plus what the other files share.

    python aw_elc.py status
    python aw_elc.py play static|breathe|pulse|morph|spectrum|wave [color] [color2] [brightness 0-100]

Plain ctypes over hid.dll: no packages, no driver, no admin. Command bytes as documented by the alien-lights and OpenRGB
projects, tried on this PC's firmware 1.1.12. The colour goes into the controller's volatile slot, so it can be gone
after a power cut; the watcher sets it again after a wake. LEDS is the set Command Center itself lights on this PC:
the controller reports 70 segments, the remaining ones are left alone.
"""
from __future__ import annotations

import ctypes as C
import ctypes.wintypes as W
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "auroralight.json")
STATUS = os.path.join(HERE, "auroralight.status.json")
MUTEX = "Local\\auroralight-watcher"
WINDOW_MUTEX = "Local\\auroralight-window"          # held while the settings window is open
DEFAULT_CONFIG = {"enabled": True, "default": {"effect": "static", "color": "#00F0F0"}, "brightness": 100,
                  "rules": [], "known_colors": {}}

REPORT = 33                                       # 34 on the wire: Windows wants a leading report id, here 0
BATCH = REPORT - 5
LEDS = [*range(60), 63, 64, 65, 68]
SLOT = 0xFFFF
ANIM_NEW, ANIM_FINISH_PLAY = 1, 3
COLOR, PULSE, MORPH = 0, 1, 2
EFFECTS = {"static": "Solid color", "breathe": "Breathe", "pulse": "Pulse", "morph": "Morph between two colors",
           "spectrum": "Spectrum", "wave": "Wave"}
SPEEDS = {"slow": (3000, 90), "medium": (1500, 160), "fast": (700, 240)}
SPECTRUM = [0xFF0040, 0xFF8000, 0xFFE000, 0x20E040, 0x00C8FF, 0x3050FF, 0xA030F0]

hid = C.WinDLL("hid.dll")
setupapi = C.WinDLL("setupapi.dll")
kernel32 = C.WinDLL("kernel32.dll", use_last_error=True)
user32 = C.WinDLL("user32.dll")


class GUID(C.Structure):
    _fields_ = [("a", C.c_ulong), ("b", C.c_ushort), ("c", C.c_ushort), ("d", C.c_ubyte * 8)]


class IFACE(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("guid", GUID), ("flags", W.DWORD), ("res", C.c_size_t)]


setupapi.SetupDiGetClassDevsW.restype = C.c_void_p
setupapi.SetupDiGetClassDevsW.argtypes = [C.POINTER(GUID), C.c_wchar_p, C.c_void_p, W.DWORD]
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [C.c_void_p, C.c_void_p, C.POINTER(GUID), W.DWORD, C.POINTER(IFACE)]
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [C.c_void_p, C.POINTER(IFACE), C.c_void_p, W.DWORD,
                                                      C.POINTER(W.DWORD), C.c_void_p]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [C.c_void_p]
kernel32.CreateFileW.restype = C.c_void_p
kernel32.CreateFileW.argtypes = [C.c_wchar_p, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, C.c_void_p]
kernel32.CloseHandle.argtypes = [C.c_void_p]
kernel32.OpenProcess.restype = C.c_void_p
kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [C.c_void_p, W.DWORD, C.c_wchar_p, C.POINTER(W.DWORD)]
kernel32.GetExitCodeProcess.argtypes = [C.c_void_p, C.POINTER(W.DWORD)]
kernel32.CreateMutexW.restype = C.c_void_p
kernel32.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, C.c_wchar_p]
kernel32.OpenMutexW.restype = C.c_void_p
kernel32.OpenMutexW.argtypes = [W.DWORD, W.BOOL, C.c_wchar_p]
hid.HidD_SetOutputReport.argtypes = [C.c_void_p, C.c_void_p, C.c_ulong]
hid.HidD_GetInputReport.argtypes = [C.c_void_p, C.c_void_p, C.c_ulong]
user32.GetForegroundWindow.restype = C.c_void_p
user32.GetWindowThreadProcessId.argtypes = [C.c_void_p, C.POINTER(W.DWORD)]
user32.IsWindowVisible.argtypes = [C.c_void_p]
user32.GetWindowTextLengthW.argtypes = [C.c_void_p]
WNDENUMPROC = C.WINFUNCTYPE(W.BOOL, C.c_void_p, C.c_void_p)
user32.EnumWindows.argtypes = [WNDENUMPROC, C.c_void_p]


class ControllerError(RuntimeError):
    pass


def find_path() -> str | None:
    guid = GUID()
    hid.HidD_GetHidGuid(C.byref(guid))
    devs = setupapi.SetupDiGetClassDevsW(C.byref(guid), None, None, 0x12)  # present + device interface
    try:
        i = 0
        while True:
            iface = IFACE(cbSize=C.sizeof(IFACE))
            if not setupapi.SetupDiEnumDeviceInterfaces(devs, None, C.byref(guid), i, C.byref(iface)):
                return None
            i += 1
            need = W.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(devs, C.byref(iface), None, 0, C.byref(need), None)
            buf = C.create_string_buffer(need.value)
            C.cast(buf, C.POINTER(W.DWORD))[0] = 8    # cbSize of the detail struct on 64-bit
            if setupapi.SetupDiGetDeviceInterfaceDetailW(devs, C.byref(iface), buf, need, None, None):
                path = C.wstring_at(C.addressof(buf) + 4)
                if "vid_187c&pid_0550" in path.lower():
                    return path
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(devs)


class Controller:
    def __init__(self):
        path = find_path()
        if not path:
            raise ControllerError("AW-ELC not found")
        self.handle = kernel32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
        if self.handle in (None, C.c_void_p(-1).value):
            raise ControllerError(f"cannot open AW-ELC, error {C.get_last_error()}")

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def transfer(self, payload: bytes, delay: float = 0.07) -> bytes:
        out = (C.c_ubyte * (REPORT + 1))(0, *payload)
        if not hid.HidD_SetOutputReport(self.handle, out, REPORT + 1):
            raise ControllerError(f"write failed, error {C.get_last_error()}")
        time.sleep(delay)                         # the controller is rate-sensitive
        back = (C.c_ubyte * (REPORT + 1))()
        if not hid.HidD_GetInputReport(self.handle, back, REPORT + 1):
            raise ControllerError(f"read failed, error {C.get_last_error()}")
        return bytes(back)[1:]

    def checked(self, payload: bytes, match: int, delay: float = 0.07) -> bytes:
        answer = self.transfer(payload, delay)
        if answer[:match] != payload[:match]:
            raise ControllerError(f"rejected {payload[:4].hex()}: {answer[:8].hex()}")
        return answer

    def identity(self) -> dict:
        conf = self.checked(bytes((3, 0x20, 2)), 3)
        fw = self.checked(bytes((3, 0x20, 0)), 3)
        return {"platform": (conf[3] << 8) | conf[4], "segments": conf[5], "firmware": f"{fw[3]}.{fw[4]}.{fw[5]}"}

    def animation(self, sub: int) -> None:
        payload = bytes((3, 0x21, sub >> 8, sub & 0xFF, SLOT >> 8, SLOT & 0xFF, 0, 0))
        self.checked(payload, 4, 1.0 if sub == ANIM_FINISH_PLAY else 0.07)

    def play(self, look: dict, brightness: int) -> None:
        """`look` = {"effect", "color", "color2", "speed"}; see EFFECTS."""
        sequences = build_sequences(look)
        self.animation(ANIM_NEW)
        for phase, actions in enumerate(sequences):
            leds = LEDS[phase::len(sequences)]
            for zones in batched(leds):
                self.checked(bytes((3, 0x23, 1, len(zones) >> 8, len(zones) & 0xFF, *zones)), 2)
                for i in range(0, len(actions), 3):   # three actions fit one report
                    self.checked(bytes((3, 0x24, *(b for a in actions[i:i + 3] for b in action_bytes(*a)))), 2)
        self.animation(ANIM_FINISH_PLAY)
        dim = 100 - max(0, min(100, brightness))
        for zones in batched(LEDS):
            self.checked(bytes((3, 0x26, dim, len(zones) >> 8, len(zones) & 0xFF, *zones)), 3)


def batched(leds: list[int]) -> list[list[int]]:
    return [leds[i:i + BATCH] for i in range(0, len(leds), BATCH)]


def action_bytes(mode: int, duration: int, tempo: int, rgb: int) -> tuple[int, ...]:
    return (mode, duration >> 8, duration & 0xFF, tempo >> 8, tempo & 0xFF,
            (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)


def build_sequences(look: dict) -> list[list[tuple[int, int, int, int]]]:
    """One action list per phase; the LEDs are dealt out between the phases, which is what makes a wave run."""
    effect = look.get("effect", "static")
    c1 = parse_color(look.get("color", "#00F0F0"))
    c2 = parse_color(look.get("color2", "#000000"))
    duration, pulse_tempo = SPEEDS.get(look.get("speed", "medium"), SPEEDS["medium"])
    if effect == "breathe":
        return [[(MORPH, duration, 64, c1), (MORPH, duration, 64, 0)]]
    if effect == "pulse":
        return [[(PULSE, duration, pulse_tempo, c1)]]
    if effect == "morph":
        return [[(MORPH, duration, 64, c1), (MORPH, duration, 64, c2)]]
    if effect == "spectrum":
        return [[(MORPH, duration, 64, c) for c in SPECTRUM]]
    if effect == "wave":
        return [[(MORPH, duration, 64, c) for c in SPECTRUM[o:] + SPECTRUM[:o]]
                for o in (round(p * len(SPECTRUM) / 4) for p in range(4))]
    return [[(COLOR, 1, 2, c1)]]


def parse_color(text: str) -> int:
    return int(text.strip().lstrip("#"), 16) & 0xFFFFFF


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    return cfg


def window_open() -> bool:
    h = kernel32.OpenMutexW(0x100000, False, WINDOW_MUTEX)  # SYNCHRONIZE
    if h:
        kernel32.CloseHandle(h)
    return bool(h)


def save_json(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)                         # the watcher never reads a half-written file


def norm_path(path: str) -> str:
    return re.sub(r"[\\/]+", r"\\", path).rstrip("\\").lower()


def rule_matches(rule: dict, path: str) -> bool:
    """`match` is a bare exe name, a full exe path or a folder the program lives under."""
    target = norm_path(rule.get("match", ""))
    if not target:
        return False
    if "\\" not in target:
        return path.rsplit("\\", 1)[-1] == target
    return path == target or path.startswith(target + "\\")


def process_path(pid: int) -> str | None:
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        size = W.DWORD(1024)
        buf = C.create_unicode_buffer(1024)
        return norm_path(buf.value) if kernel32.QueryFullProcessImageNameW(h, 0, buf, C.byref(size)) else None
    finally:
        kernel32.CloseHandle(h)


def foreground() -> tuple[int, str | None]:
    pid = W.DWORD()
    window = user32.GetForegroundWindow()
    if not window:
        return 0, None
    user32.GetWindowThreadProcessId(window, C.byref(pid))
    return pid.value, process_path(pid.value)


def is_alive(pid: int) -> bool:
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    try:
        code = W.DWORD()
        return bool(kernel32.GetExitCodeProcess(h, C.byref(code))) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(h)


def windowed_programs() -> dict[str, str]:
    """Exe name -> full path for everything that has a visible titled window right now."""
    found: dict[str, str] = {}

    def visit(window, _):
        if user32.IsWindowVisible(window) and user32.GetWindowTextLengthW(window):
            pid = W.DWORD()
            user32.GetWindowThreadProcessId(window, C.byref(pid))
            path = process_path(pid.value)
            if path:
                found[path.rsplit("\\", 1)[-1]] = path
        return True

    user32.EnumWindows(WNDENUMPROC(visit), None)
    return found


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("status", "play"):
        print(__doc__)
        return 2
    with Controller() as c:
        if sys.argv[1] == "status":
            print(c.identity())
        else:
            a = sys.argv[2:] + [None] * 4
            c.play({"effect": a[0], "color": a[1] or "#00F0F0", "color2": a[2] or "#000000"}, int(a[3] or 100))
            print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
