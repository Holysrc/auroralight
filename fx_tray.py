"""Tray icon of the watcher: a dot in the colour now showing. Click = settings window, right click = menu.

Plain ctypes, runs the Windows message loop on the calling thread. Explorer restarts are handled: the icon comes back.
"""
from __future__ import annotations

import ctypes as C
import ctypes.wintypes as W
import os
import subprocess
import sys

import aw_elc

TITLE = "Подсветка Alienware"
CLASS_NAME = "FxLightsTray"
SIZE = 32
GREY = "#9A9A9A"
WM_DESTROY, WM_COMMAND, WM_NULL = 0x0002, 0x0111, 0x0000
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
WM_TRAY, WM_SET_ICON = 0x8001, 0x8002
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MENU_SETTINGS, MENU_EXIT = 1, 2
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x0100, 0x0002

user32 = C.WinDLL("user32.dll", use_last_error=True)
gdi32 = C.WinDLL("gdi32.dll")
shell32 = C.WinDLL("shell32.dll")
kernel32 = C.WinDLL("kernel32.dll")
LRESULT = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)


class WNDCLASS(C.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", C.c_int), ("cbWndExtra", C.c_int),
                ("hInstance", W.HINSTANCE), ("hIcon", W.HICON), ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


class NOTIFYICONDATA(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128), ("dwState", W.DWORD),
                ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256), ("uVersion", W.UINT),
                ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD), ("guidItem", C.c_byte * 16),
                ("hBalloonIcon", W.HICON)]


class ICONINFO(C.Structure):
    _fields_ = [("fIcon", W.BOOL), ("xHotspot", W.DWORD), ("yHotspot", W.DWORD), ("hbmMask", W.HBITMAP),
                ("hbmColor", W.HBITMAP)]


class POINT(C.Structure):
    _fields_ = [("x", W.LONG), ("y", W.LONG)]


user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [C.POINTER(WNDCLASS)]
user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int,
                                   W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
user32.CreateWindowExW.restype = W.HWND
user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
user32.TranslateMessage.argtypes = [C.POINTER(W.MSG)]
user32.DispatchMessageW.argtypes = [C.POINTER(W.MSG)]
user32.CreatePopupMenu.restype = W.HMENU
user32.AppendMenuW.argtypes = [W.HMENU, W.UINT, C.c_size_t, W.LPCWSTR]
user32.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, C.c_int, C.c_int, C.c_int, W.HWND, C.c_void_p]
user32.DestroyMenu.argtypes = [W.HMENU]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.GetCursorPos.argtypes = [C.POINTER(POINT)]
user32.CreateIconIndirect.argtypes = [C.POINTER(ICONINFO)]
user32.CreateIconIndirect.restype = W.HICON
user32.DestroyIcon.argtypes = [W.HICON]
user32.RegisterWindowMessageW.argtypes = [W.LPCWSTR]
gdi32.CreateBitmap.argtypes = [C.c_int, C.c_int, W.UINT, W.UINT, C.c_void_p]
gdi32.CreateBitmap.restype = W.HBITMAP
gdi32.DeleteObject.argtypes = [W.HANDLE]
shell32.Shell_NotifyIconW.argtypes = [W.DWORD, C.POINTER(NOTIFYICONDATA)]
kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]
kernel32.GetModuleHandleW.restype = W.HMODULE


def dot_icon(color: str) -> W.HICON:
    """A round dot: the mask makes everything outside the circle transparent."""
    rgb = aw_elc.parse_color(color)
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    pixels, mask = bytearray(), bytearray()
    middle = (SIZE - 1) / 2
    radius = SIZE / 2 - 2
    for y in range(SIZE):
        bits = 0
        for x in range(SIZE):
            inside = (x - middle) ** 2 + (y - middle) ** 2 <= radius ** 2
            pixels += bytes((b, g, r, 255)) if inside else bytes(4)
            bits = (bits << 1) | (0 if inside else 1)
        mask += bits.to_bytes(4, "big")
    hb_color = gdi32.CreateBitmap(SIZE, SIZE, 1, 32, bytes(pixels))
    hb_mask = gdi32.CreateBitmap(SIZE, SIZE, 1, 1, bytes(mask))
    icon = user32.CreateIconIndirect(C.byref(ICONINFO(True, 0, 0, hb_mask, hb_color)))
    gdi32.DeleteObject(hb_color)
    gdi32.DeleteObject(hb_mask)
    return icon


def open_settings() -> None:
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    subprocess.Popen([pyw, os.path.join(aw_elc.HERE, "fx_ui.pyw")], cwd=aw_elc.HERE)


class Tray:
    def __init__(self, log):
        self.log = log
        self.hwnd = None
        self.icon = None
        self.color = GREY
        self.tip = TITLE
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.proc = WNDPROC(self.on_message)      # kept alive: Windows calls it for the life of the window

    def show(self, color: str | None, tip: str) -> None:
        """Called from the watcher thread; the window's own thread does the work."""
        self.color, self.tip = color or GREY, f"{TITLE}: {tip}"[:127]
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_SET_ICON, 0, 0)

    def notify(self, action: int) -> bool:
        data = NOTIFYICONDATA(cbSize=C.sizeof(NOTIFYICONDATA), hWnd=self.hwnd, uID=1,
                              uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP, uCallbackMessage=WM_TRAY, hIcon=self.icon,
                              szTip=self.tip)
        return bool(shell32.Shell_NotifyIconW(action, C.byref(data)))

    def refresh_icon(self, action: int = NIM_MODIFY) -> None:
        old = self.icon
        self.icon = dot_icon(self.color)
        ok = self.notify(action)
        if old:
            user32.DestroyIcon(old)
        if action == NIM_ADD:
            self.log.info("tray icon %s", "added" if ok else "NOT added")

    def menu(self) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, MENU_SETTINGS, "Настройки…")
        user32.AppendMenuW(menu, 0, MENU_EXIT, "Выход")
        at = POINT()
        user32.GetCursorPos(C.byref(at))
        user32.SetForegroundWindow(self.hwnd)     # or the menu does not close on a click elsewhere
        chosen = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, at.x, at.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if chosen == MENU_SETTINGS:
            open_settings()
        elif chosen == MENU_EXIT:
            user32.DestroyWindow(self.hwnd)

    def on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event == WM_LBUTTONUP:
                open_settings()
            elif event == WM_RBUTTONUP:
                self.menu()
            return 0
        if msg == WM_SET_ICON:
            self.refresh_icon()
            return 0
        if msg == self.taskbar_created:
            self.refresh_icon(NIM_ADD)
            return 0
        if msg == WM_DESTROY:
            self.notify(NIM_DELETE)
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> None:
        """Blocks until "Выход"."""
        module = kernel32.GetModuleHandleW(None)
        user32.RegisterClassW(C.byref(WNDCLASS(lpfnWndProc=self.proc, hInstance=module, lpszClassName=CLASS_NAME)))
        # not TITLE: the settings window finds itself by that title
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, CLASS_NAME, 0, 0, 0, 0, 0, None, None, module, None)
        self.refresh_icon(NIM_ADD)
        msg = W.MSG()
        while user32.GetMessageW(C.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(C.byref(msg))
            user32.DispatchMessageW(C.byref(msg))
