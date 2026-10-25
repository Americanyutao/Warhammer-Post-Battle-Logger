"""Check the built GUI executable and its own hidden tray/Exit path."""
import ctypes
import argparse
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(os.environ.get('WH3_BUILD_DEPS',P/'build/packaging-deps')))
import pefile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app-dir',type=Path,default=P/'release/WH3BattleLogger')
    parser.add_argument('--headless',action='store_true')
    args=parser.parse_args()
    exe=args.app_dir/'WH3BattleLogger.exe'
    pe=pefile.PE(str(exe))
    assert pe.OPTIONAL_HEADER.Subsystem==2,'Release must have no console subsystem.'
    resource_types={entry.id for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
    assert {3,14}.issubset(resource_types),'Embedded application icons are missing.'
    pe.close()
    install=P/'build/packaged-install-check.json'
    subprocess.run([str(exe),'--check-install',str(install)],check=True,timeout=30)
    result=json.loads(install.read_text(encoding='utf-8'))
    assert result['frozen'] and result['report_rendered'] and result['encryption_roundtrip']
    assert not list(args.app_dir.rglob('*.wh3log'))
    assert not list(args.app_dir.rglob('logger.key'))
    if args.headless:
        result.update(gui_subsystem=True,embedded_icons=True)
        (P/'build/release-headless-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2))
        return
    user=ctypes.WinDLL('user32',use_last_error=True)
    Proc=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    user.EnumWindows.argtypes=[Proc,w.LPARAM];user.EnumWindows.restype=w.BOOL
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.IsWindowVisible.argtypes=[w.HWND];user.IsWindowVisible.restype=w.BOOL
    user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.PostMessageW.restype=w.BOOL
    process=None
    with tempfile.TemporaryDirectory(prefix='release-check-',dir=P/'build') as temp:
        try:
            process=subprocess.Popen([str(exe),'--data-dir',temp,'--pid',str(os.getpid())])
            def windows():
                found=[]
                @Proc
                def visit(hwnd,lp):
                    pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                    if pid.value==process.pid:
                        text=ctypes.create_unicode_buffer(128);user.GetWindowTextW(hwnd,text,128)
                        found.append((hwnd,text.value,bool(user.IsWindowVisible(hwnd))))
                    return True
                user.EnumWindows(visit,0)
                return found
            deadline=time.monotonic()+15;tray=None
            while time.monotonic()<deadline:
                found=windows()
                tray=next((hwnd for hwnd,title,_ in found if title=='Battle Logger tray'),None)
                if tray and (Path(temp)/'captures/logger.key').is_file():break
                if process.poll() is not None:raise RuntimeError('Release exited before tray startup.')
                time.sleep(.1)
            assert tray,'Release did not create its notification window.'
            assert not any(visible for _,_,visible in windows()),'A visible app window was created.'
            assert (Path(temp)/'captures/logger.key').stat().st_size==32
            # A second launch must not start another collector or capture key.
            second=Path(temp)/'second'
            subprocess.run([str(exe),'--data-dir',str(second)],check=True,timeout=10)
            assert not second.exists()
            assert user.PostMessageW(tray,0x111,2,0),'Could not send the native Exit command.'
            assert process.wait(timeout=15)==0,'Exit did not complete cleanly.'
            result.update(gui_subsystem=True,embedded_icons=True,no_visible_windows=True,
                single_instance=True,worker_started=True,clean_native_exit=True)
        finally:
            if process and process.poll() is None:
                process.terminate();process.wait(timeout=5)
    assert not list(args.app_dir.rglob('*.wh3log'))
    assert not list(args.app_dir.rglob('logger.key'))
    (P/'build/release-startup-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
