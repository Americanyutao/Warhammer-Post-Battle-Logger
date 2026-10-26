"""Desktop QA for native update progress, cancellation and About release-notes link."""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from update_ui import ProgressWindow, RELEASE_NOTES, VERSION

user=ctypes.WinDLL('user32',use_last_error=True)
Proc=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
user.EnumChildWindows.argtypes=[w.HWND,Proc,w.LPARAM]
user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=ctypes.c_ssize_t

def children(hwnd):
    found=[]
    @Proc
    def visit(child,lp):
        text=ctypes.create_unicode_buffer(1024);kind=ctypes.create_unicode_buffer(128)
        user.GetWindowTextW(child,text,1024);user.GetClassNameW(child,kind,128)
        found.append((child,kind.value,text.value));return True
    user.EnumChildWindows(hwnd,visit,0)
    return found

progress=ProgressWindow().start()
try:
    progress.update('Downloading changes: 4.5 / 10.0 MB',45,100)
    user.SendMessageW(progress.hwnd,0x8003,0,0)
    controls=children(progress.hwnd)
    assert any('4.5 / 10.0 MB' in text for _,_,text in controls)
    bar=next(hwnd for hwnd,kind,_ in controls if kind=='msctls_progress32')
    assert user.SendMessageW(bar,0x408,0,0)==45
    user.SendMessageW(progress.hwnd,0x10,0,0)
    assert progress.cancelled.is_set()
finally:progress.close()
about=ProgressWindow(title='About Battle Logger',about=True).start()
try:
    controls=children(about.hwnd)
    assert any(f'Installed version: {VERSION}' in text for _,_,text in controls)
    assert any(text=='GitHub release notes' for _,_,text in controls)
    with patch('update_ui.webbrowser.open') as browser:
        user.SendMessageW(about.hwnd,0x111,2,0)
        browser.assert_called_once_with(RELEASE_NOTES+'/tag/v'+VERSION)
finally:about.close()
result=dict(version=VERSION,progress_percent=45,cancel=True,about_version=True,release_notes_link=True)
(P/'build/update-ui-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
