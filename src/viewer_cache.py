"""Per-window browser cache leases; capture data stays in memory."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import shutil
import time
import uuid


def process_stamp(pid):
    """Creation identity, False for an exited process, None if inaccessible."""
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
    kernel.GetProcessTimes.argtypes=[w.HANDLE]+[ctypes.POINTER(w.FILETIME)]*4
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:return False if ctypes.get_last_error() in (87,1168) else None
    try:
        status=w.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(status)):return None
        if status.value!=259:return False
        stamps=[w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in stamps]):return None
        return (stamps[0].dwHighDateTime<<32)|stamps[0].dwLowDateTime
    finally:kernel.CloseHandle(handle)


def remove_cache(path,root):
    path=Path(path);root=Path(root).resolve()
    if path.is_symlink() or path.is_junction() or path.resolve().parent!=root or not path.name.startswith('view-'):
        raise ValueError('Cache path is outside the viewer cache directory.')
    shutil.rmtree(path)


def cleanup_stale_caches(root):
    root=Path(root)/'cache/report-viewer'
    if not root.is_dir():return
    for path in root.glob('view-*'):
        try:
            owner=json.loads((path/'owner.json').read_text(encoding='utf-8'))
            if not isinstance(owner,dict):continue
            if owner.get('schema')!=1 or type(owner.get('pid')) is not int or type(owner.get('stamp')) is not int:continue
            if not 0<owner['pid']<2**32:continue
            stamp=process_stamp(owner['pid'])
            if stamp is False or (stamp is not None and stamp!=owner['stamp']):remove_cache(path,root)
        except (OSError,ValueError,KeyError):continue


class ViewerCache:
    def __init__(self,root):
        self.root=Path(root)/'cache/report-viewer'
        self.path=self.root/('view-'+uuid.uuid4().hex)

    def __enter__(self):
        cleanup_stale_caches(self.root.parent.parent)
        self.path.mkdir(parents=True)
        try:
            stamp=process_stamp(os.getpid())
            if not stamp:raise RuntimeError('Could not identify the viewer process.')
            (self.path/'owner.json').write_text(json.dumps(dict(schema=1,pid=os.getpid(),stamp=stamp)),encoding='utf-8')
        except Exception:
            remove_cache(self.path,self.root)
            raise
        return self

    def __exit__(self,*args):
        # WebView2 releases profile files after its native window is disposed.
        for delay in (0,.1,.2,.4,.8,1.6,2):
            if delay:time.sleep(delay)
            if not self.path.exists():return
            try:remove_cache(self.path,self.root);return
            except OSError:continue
        # A crash/slow browser shutdown is retried safely on the next launch.
