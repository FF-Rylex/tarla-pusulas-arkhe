"""Harita ve HTML araçlarını uygulamanın sekmelerinde çalıştırır."""
import ctypes
from ctypes import wintypes
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from functools import lru_cache


def available():
    return importlib.util.find_spec("webview") is not None


def launch(title, url, parent_hwnd):
    if os.name != "nt":
        raise RuntimeError("Uygulama içi haritalar Windows ve Microsoft Edge WebView2 gerektirir.")
    if not available():
        raise RuntimeError("Harita sekmeleri için build_exe.bat ile uygulamayı yeniden derleyin.")
    args = [title, url, str(parent_hwnd)]
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--web-window", *args]
    else:
        cmd = [sys.executable, str(Path(__file__).resolve()), *args]
    # Webview kendi ana iş parçacığında çalışır; tkinter döngüsünü engellemez.
    return subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent),
                            creationflags=subprocess.CREATE_NO_WINDOW)


@lru_cache(maxsize=None)
def _win32(name, result, *arguments):
    function = getattr(ctypes.WinDLL("user32", use_last_error=True), name)
    function.restype = result
    function.argtypes = arguments
    return function


def _resize(parent, child):
    rect = wintypes.RECT()
    get_rect = _win32("GetClientRect", wintypes.BOOL, wintypes.HWND,
                      ctypes.POINTER(wintypes.RECT))
    if not get_rect(parent, ctypes.byref(rect)):
        return False
    move = _win32("SetWindowPos", wintypes.BOOL, wintypes.HWND, wintypes.HWND,
                  ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
    # SWP_ASYNCWINDOWPOS | SWP_NOACTIVATE | SWP_NOZORDER
    return bool(move(child, None, 0, 0, rect.right, rect.bottom, 0x4014))


def _child(parent):
    get_window = _win32("GetWindow", wintypes.HWND, wintypes.HWND, wintypes.UINT)
    return get_window(parent, 5)  # GW_CHILD


def resize_embedded(parent):
    child = _child(parent)
    return bool(child and _resize(parent, child))


def load_status(parent):
    child = _child(parent)
    get_prop = _win32("GetPropW", wintypes.HANDLE, wintypes.HWND, wintypes.LPCWSTR)
    return (get_prop(child, "TarlaLoadStatus") or 0) if child else 0


def _attach(parent, child):
    get_style = _win32("GetWindowLongW", wintypes.LONG, wintypes.HWND, ctypes.c_int)
    set_style = _win32("SetWindowLongW", wintypes.LONG, wintypes.HWND, ctypes.c_int, wintypes.LONG)
    style = get_style(child, -16)  # GWL_STYLE
    ws_popup, ws_child = 0x80000000, 0x40000000
    set_style(child, -16, (style & ~ws_popup) | ws_child)
    set_parent = _win32("SetParent", wintypes.HWND, wintypes.HWND, wintypes.HWND)
    ctypes.set_last_error(0)
    if not set_parent(child, parent) and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    _resize(parent, child)


def run(title, url, parent_hwnd):
    try:
        import webview
        class PresentationAPI:
            _window = None
            def set_title(self, text):
                if self._window is not None:
                    self._window.set_title(str(text)[:180])
        api = PresentationAPI()
        api._window = webview.create_window(title, url, min_size=(1, 1),
                                            x=-32000, y=-32000, width=480, height=320,
                                            frameless=True, easy_drag=False,
                                            draggable=False, zoomable=False, js_api=api)
        child = None

        def attach():
            nonlocal child
            try:
                form = api._window.native
                child = int(form.Handle.ToInt64())
                control = form.browser.webview
                control.CoreWebView2InitializationCompleted += initialized
                control.NavigationCompleted += navigation_completed
            except Exception:
                # before_show hatalarını pywebview yakalar. Üst süreç sekmede bildirir.
                os._exit(1)

        def initialized(sender, args):
            if not args.IsSuccess:
                os._exit(1)

        def navigation_completed(sender, args):
            try:
                _attach(int(parent_hwnd), child)
                set_prop = _win32("SetPropW", wintypes.BOOL, wintypes.HWND,
                                  wintypes.LPCWSTR, wintypes.HANDLE)
                set_prop(child, "TarlaLoadStatus", 1 if args.IsSuccess else 2)
            except Exception:
                os._exit(1)

        api._window.events.before_show += attach
        webview.start(gui="edgechromium")
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(run(*sys.argv[1:]))
