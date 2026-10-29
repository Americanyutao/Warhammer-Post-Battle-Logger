"""Viewer process lifecycle, kept independent of collection and HTML export."""
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import subprocess
import sys
from paths import FROZEN


def viewer_command(source,root,key_path=None):
    command=[sys.executable]
    if not FROZEN:command+=['-B',str(Path(__file__).with_name('release_app.py'))]
    command+=['--view-log',str(source),'--data-dir',str(root)]
    if key_path:command+=['--view-key',str(key_path)]
    return command


def viewer_windows(pid):
    user=ctypes.WinDLL('user32',use_last_error=True)
    Proc=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[Proc,w.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.ShowWindow.argtypes=[w.HWND,ctypes.c_int];user.SetForegroundWindow.argtypes=[w.HWND]
    user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
    found=[]
    @Proc
    def visit(hwnd,unused):
        owner=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid:
            title=ctypes.create_unicode_buffer(1024);user.GetWindowTextW(hwnd,title,1024)
            if title.value.startswith('Battle overview: '):found.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    return user,found


class ViewerManager:
    def __init__(self,root):self.root=Path(root);self.children={}

    def open(self,source,key_path=None):
        source=Path(source).resolve()
        if source.suffix.lower()!='.wh3log' or not source.is_file():raise ValueError('The recording is unavailable.')
        previous=self.children.get(source)
        if previous and previous.poll() is None:
            user,windows=viewer_windows(previous.pid)
            if windows:user.ShowWindow(windows[0],9);user.SetForegroundWindow(windows[0])
            return previous
        process=subprocess.Popen(viewer_command(source,self.root,key_path),creationflags=0x08000000)
        self.children[source]=process
        return process

    def close(self):
        for process in self.children.values():
            if process.poll() is None:
                user,windows=viewer_windows(process.pid)
                for hwnd in windows:user.PostMessageW(hwnd,0x10,0,0)
        for process in self.children.values():
            if process.poll() is None:
                try:process.wait(timeout=15)
                except subprocess.TimeoutExpired:pass
