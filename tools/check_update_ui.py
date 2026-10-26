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
    assert user.SendMessageW(progress.hwnd,0x7f,0,0)
    assert user.SendMessageW(progress.hwnd,0x7f,1,0)
    progress.update('Installing changes',0,10*1048576,'bytes','report_view.js',3)
    import time
    time.sleep(.1)
    progress.update('Installing changes',int(4.5*1048576),10*1048576,'bytes','report_view.js',2)
    user.SendMessageW(progress.hwnd,0x8003,0,0)
    controls=children(progress.hwnd)
    assert any('4.50 MB / 10.00 MB installed' in text for _,_,text in controls)
    assert any(text=='45% complete' for _,_,text in controls)
    assert any(text=='Cancel' for _,_,text in controls)
    assert any(text=='Name: report_view.js' for _,_,text in controls)
    assert any(text=='Items remaining: 2' for _,_,text in controls)
    assert any(text=='Pause' for _,_,text in controls)
    user.SendMessageW(progress.hwnd,0x111,4,0)
    assert progress.paused.is_set()
    user.SendMessageW(progress.hwnd,0x111,4,0)
    assert not progress.paused.is_set()
    user.SendMessageW(progress.hwnd,0x111,5,0)
    assert any(text=='More details' for _,_,text in children(progress.hwnd))
    user.SendMessageW(progress.hwnd,0x111,5,0)
    user.SendMessageW(progress.hwnd,0x10,0,0)
    assert progress.cancelled.is_set()
    assert progress.hwnd
    user.SendMessageW(progress.hwnd,0x8003,0,0)
    assert any(text=='Cancelling update…' for _,_,text in children(progress.hwnd))
finally:progress.close()
about=ProgressWindow(title='About Battle Logger',about=True).start()
try:
    assert user.SendMessageW(about.hwnd,0x7f,0,0)
    assert user.SendMessageW(about.hwnd,0x7f,1,0)
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
