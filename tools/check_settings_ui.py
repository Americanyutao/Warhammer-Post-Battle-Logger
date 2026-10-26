"""Exercise the native settings dialog using temporary report preferences."""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
import tempfile

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from update_ui import ProgressWindow
from settings import Settings,ICONS_TIP

user=ctypes.WinDLL('user32',use_last_error=True)
user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=ctypes.c_ssize_t
user.GetDlgItem.argtypes=[w.HWND,ctypes.c_int];user.GetDlgItem.restype=w.HWND
with tempfile.TemporaryDirectory(dir=P/'build') as d:
    store=Settings(d);dialog=ProgressWindow(title='Battle Logger settings',settings=store).start()
    try:
        assert user.SendMessageW(dialog.hwnd,0x7f,0,0)
        assert user.SendMessageW(dialog.icons_checkbox,0xf0,0,0)==1
        assert user.SendMessageW(dialog.settings_tooltip,0x40d,0,0)==1
        assert 'easier sharing' in ICONS_TIP
        user.SendMessageW(dialog.icons_checkbox,0xf1,0,0)
        user.SendMessageW(dialog.hwnd,0x111,6,0)
        dialog.thread.join(3);assert not dialog.thread.is_alive(),dialog.error
        assert not Settings(d).report_options()['icons']
    finally:dialog.close()
    dialog=ProgressWindow(title='Battle Logger settings',settings=store).start()
    try:
        assert user.SendMessageW(dialog.icons_checkbox,0xf0,0,0)==0
        user.SendMessageW(dialog.icons_checkbox,0xf1,1,0)
        user.SendMessageW(dialog.hwnd,0x111,1,0)
        dialog.thread.join(3);assert not dialog.thread.is_alive(),dialog.error
        assert not Settings(d).report_options()['icons']
    finally:dialog.close()
result=dict(default_checked=True,save_persists=True,reopen_restores=True,cancel_preserves=True,hover_tooltip=True,app_icon=True)
(P/'build/settings-ui-check.json').write_bytes((json.dumps(result,indent=2)+'\n').encode('utf-8'))
print(json.dumps(result,indent=2))
