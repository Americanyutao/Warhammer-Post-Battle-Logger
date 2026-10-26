"""Windowless release: automatic collection, notification icon and two commands."""
import argparse
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import queue
import sys
import traceback
import threading

sys.dont_write_bytecode=True
from icons import set_app_identity
from paths import DATA_ROOT, RESOURCE_ROOT, FROZEN
from tray import TrayIcon
from worker import Worker, RATES
from updater import UpdateChecker, apply_update, launch_installer, cleanup_update, cleanup_legacy_backups
from update_ui import ProgressWindow
from version import VERSION


def open_reports(root):
    directory=Path(root)/'captures'
    directory.mkdir(parents=True,exist_ok=True)
    os.startfile(str(directory))
    return directory


class BackgroundApp:
    def __init__(self, root=DATA_ROOT, rate=1., pid=None, worker=None, tray=None):
        self.root=Path(root)
        self.channel=queue.Queue(maxsize=1)
        self.worker=worker if worker is not None else Worker(self.root,self.channel,rate,pid,preview=False)
        self.tray=tray if tray is not None else TrayIcon()
        self.last_status=None
        self.updates=UpdateChecker(self.tray.actions)
        self.about=None

    def run(self):
        try:
            self.tray.start()
            if not self.tray.ready.wait(5) or not self.tray.available:
                raise RuntimeError(self.tray.error or 'Windows could not create the notification icon.')
            self.worker.start()
            if FROZEN:threading.Thread(target=cleanup_after_start,args=(self.root,),daemon=True).start()
            while True:
                try:action=self.tray.actions.get(timeout=.2)
                except queue.Empty:action=None
                if action=='exit':break
                if action=='check_updates':self.updates.start()
                if action=='about' and (self.about is None or not self.about.thread.is_alive()):
                    self.about=ProgressWindow(title='About Battle Logger',about=True).start()
                if action=='install_update':break
                if action=='open_reports':open_reports(self.root)
                try:
                    message=self.channel.get_nowait()
                    status=message['status']
                    errors=[r['error'] for r in message['reports'] if r['error']]
                    if errors:status='Saving error: '+errors[-1]
                    if status!=self.last_status:
                        self.last_status=status
                        self.tray.set_tooltip('WH3 Battle Logger · '+status)
                except queue.Empty:pass
                if not self.worker.is_alive():
                    raise RuntimeError(self.worker.status or 'Battle logging stopped unexpectedly.')
                if not self.tray.thread.is_alive():
                    raise RuntimeError(self.tray.error or 'The notification icon stopped unexpectedly.')
        finally:
            # Keep the tray alive until encrypted capture and HTML saving finish.
            self.tray.set_tooltip('WH3 Battle Logger · Saving and exiting…')
            self.worker.stop_event.set()
            if self.worker.is_alive():self.worker.join()
            self.tray.stop()
            if self.about:self.about.close()
        if self.updates.pending:
            launch_installer(self.updates.pending,Path(sys.executable).resolve().parent)



def cleanup_after_start(root, directory=None, pid=None):
    try:
        if directory:cleanup_update(directory,pid)
        if directory is None:cleanup_legacy_backups(root)
    except Exception:
        log=Path(root)/'logs';log.mkdir(parents=True,exist_ok=True)
        (log/'update-cleanup-error.txt').write_text(traceback.format_exc(),encoding='utf-8')


def acquire_instance():
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,w.BOOL,w.LPCWSTR]
    kernel.CreateMutexW.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateMutexW(None,False,'Local\\WarhammerIII.BattleLogger.Release')
    error=ctypes.get_last_error()
    if not handle:raise ctypes.WinError(error)
    if error==183:
        kernel.CloseHandle(handle)
        return None,kernel
    return handle,kernel


def check_install(destination):
    """Exercise bundled reader/report/encryption resources without a game or UI."""
    import json
    import tempfile
    from aggregate import Battle
    from demo import frames
    from logfile import LogWriter,read_log
    from memory import load_profiles
    from report import convert
    from report_assets import assets_for
    unit=dict(id='check',name='Steam Tank',side='Allied',army='1',first={},
              last=dict(unit_key='wh_main_emp_veh_steam_tank'))
    assets=assets_for([unit])
    card=assets['unit_cards']['check']
    assert card=='ui/units/icons/wh_main_emp_steamtank.png'
    profiles=load_profiles(RESOURCE_ROOT/'profiles')
    with tempfile.TemporaryDirectory(prefix='wh3-logger-check-') as temp:
        log=Path(temp)/'check.wh3log';key=bytes(range(32))
        writer=LogWriter(log,key,dict(source='synthetic'))
        for frame in frames(2,1):writer.write(frame)
        writer.close({})
        assert list(read_log(log,key))[-1]['kind']=='footer'
        report=convert(log,key)
        assert 'Battle overview' in report.read_text(encoding='utf-8')
    Path(destination).write_text(json.dumps(dict(frozen=FROZEN,version=VERSION,profiles=len(profiles),
        icon_resolved=card,report_rendered=True,encryption_roundtrip=True),indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description='WARHAMMER III background battle logger')
    parser.add_argument('--rate',type=float,choices=RATES,default=1.)
    parser.add_argument('--pid',type=int)
    parser.add_argument('--data-dir',type=Path,default=DATA_ROOT,help=argparse.SUPPRESS)
    parser.add_argument('--check-install',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--apply-update',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--cleanup-update',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--wait-pid',type=int,help=argparse.SUPPRESS)
    args=parser.parse_args()
    handle=None;kernel=None
    try:
        if os.name!='nt':raise RuntimeError('The release logger requires Windows.')
        if args.apply_update:
            if not FROZEN or not args.wait_pid:raise RuntimeError('Invalid updater invocation.')
            apply_update(args.apply_update,args.wait_pid)
            return
        if args.check_install:
            check_install(args.check_install)
            return
        if args.cleanup_update:
            if not FROZEN or not args.wait_pid:raise RuntimeError('Invalid cleanup invocation.')
            threading.Thread(target=cleanup_after_start,args=(args.data_dir,args.cleanup_update,args.wait_pid),daemon=True).start()
        set_app_identity('release')
        handle,kernel=acquire_instance()
        if handle is None:return
        BackgroundApp(root=args.data_dir,rate=args.rate,pid=args.pid).run()
    except Exception:
        directory=args.data_dir/'logs';directory.mkdir(parents=True,exist_ok=True)
        (directory/'last-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.MessageBoxW.argtypes=[w.HWND,w.LPCWSTR,w.LPCWSTR,w.UINT]
        user.MessageBoxW(None,'Battle Logger stopped. Details are saved in logs/last-error.txt.',
                         'WARHAMMER III Battle Logger',0x10)
        raise SystemExit(1)
    finally:
        if handle:kernel.CloseHandle(handle)


if __name__=='__main__':main()
