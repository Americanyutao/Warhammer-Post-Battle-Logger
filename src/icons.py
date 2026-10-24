"""LOG artwork shared by Windows window, taskbar, executable and tray icons."""
import ctypes
import base64
from ctypes import wintypes as w
import os
from paths import resource_path

ICON_DIR = resource_path('assets/app')
ICON_PATH = ICON_DIR / 'battle_logger.ico'


def set_app_identity(mode='release'):
    if os.name == 'nt':
        shell=ctypes.WinDLL('shell32',use_last_error=True)
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes=[w.LPCWSTR]
        shell.SetCurrentProcessExplicitAppUserModelID.restype=ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID('WarhammerIII.BattleLogger.'+mode)


def set_window_icon(root):
    import tkinter as tk
    images=[tk.PhotoImage(master=root,data=base64.b64encode((ICON_DIR/f'battle_logger-{size}.png').read_bytes())) for size in (256,48,32,16)]
    root.iconphoto(True,*images)
    root._battle_logger_icons=images


def load_tray_icon():
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.LoadImageW.argtypes=[w.HINSTANCE,w.LPCWSTR,w.UINT,ctypes.c_int,ctypes.c_int,w.UINT]
    user.LoadImageW.restype=w.HICON
    icon=user.LoadImageW(None,str(ICON_PATH),1,32,32,0x10)
    if not icon:raise ctypes.WinError(ctypes.get_last_error())
    return icon
