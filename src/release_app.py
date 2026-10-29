"""Native main menu, report recovery and tray collection lifecycle."""
import argparse
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import queue
import sys
import traceback
import threading
import subprocess
from contextlib import nullcontext

sys.dont_write_bytecode=True
from icons import set_app_identity
from paths import DATA_ROOT, RESOURCE_ROOT, FROZEN
from tray import TrayIcon
from worker import Worker, RATES
from updater import UpdateChecker,StartupReleaseCheck, apply_update, launch_installer, cleanup_update, cleanup_legacy_backups
from update_ui import ProgressWindow
from version import VERSION
from settings import Settings
from main_menu import MainMenu, silent_message
from report_library import ReportLibrary
from viewer_manager import ViewerManager
from viewer_cache import cleanup_stale_caches
from log_migration import CaptureMaintenance
from release_notes import cached_notes


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
        self.settings=Settings(self.root)
        self.settings_window=None
        self.library=ReportLibrary(self.root)
        self.menu=MainMenu(self.library,self.tray.actions,show_welcome=FROZEN,notes=cached_notes(self.root))
        self.startup_check=None
        self.build_thread=None
        self.last_prompt=None
        self.viewers=ViewerManager(self.root)
        self.exporting=set()
        self.maintenance=CaptureMaintenance(self.root,self.busy_paths,lambda text:setattr(self.library,'status',text))

    def busy_paths(self):
        with getattr(self.worker,'recorders_lock',nullcontext()):
            active={r.path.resolve() for r in getattr(self.worker,'recorders',[]) if not r.done.is_set()}
        active.update(path for path,process in list(self.viewers.children.items()) if process.poll() is None)
        return active|self.exporting.copy()

    def open_capture(self,source,export=False):
        source=Path(source).resolve()
        with getattr(self.worker,'recorders_lock',nullcontext()):
            active={r.path.resolve() for r in getattr(self.worker,'recorders',[]) if not r.done.is_set()}
        if source in active:
            self.library.status='This battle is still recording. Wait until the recording finishes.'
            return
        if export:
            if self.build_thread and self.build_thread.is_alive():return
            def export():
                self.exporting.add(source)
                try:self.library.export_html(source)
                finally:self.exporting.discard(source)
            self.build_thread=threading.Thread(target=export,name='battle-html-export',daemon=False)
            self.build_thread.start()
        else:
            try:self.viewers.open(source);self.library.status='Opened '+source.stem+' in the app.'
            except Exception as error:self.library.status='Could not open recording: '+str(error)

    def build_missing(self, candidates=None):
        if self.build_thread and self.build_thread.is_alive():return
        with getattr(self.worker,'recorders_lock',nullcontext()):
            if candidates is None:candidates=[entry['log'] for entry in self.library.entries() if entry['log'] and not entry['html']]
            active=[r.path for r in getattr(self.worker,'recorders',[]) if not r.done.is_set()]
        paths={Path(path).resolve() for path in candidates}
        self.exporting.update(paths)
        def build():
            try:self.library.build_missing(active=active,candidates=candidates)
            finally:self.exporting.difference_update(paths)
        self.build_thread=threading.Thread(target=build,name='battle-logger-recovery',daemon=False)
        self.build_thread.start()

    def run(self):
        action=None
        try:
            self.tray.start()
            if not self.tray.ready.wait(5) or not self.tray.available:
                raise RuntimeError(self.tray.error or 'Windows could not create the notification icon.')
            self.menu.start()
            if FROZEN:
                self.library.move_shareables()
                self.library.clean_legacy_names(self.busy_paths())
            self.worker.start()
            if FROZEN:self.startup_check=StartupReleaseCheck(self.root,self.menu,self.tray.actions).start()
            self.maintenance.start()
            threading.Thread(target=cleanup_stale_caches,args=(self.root,),daemon=True).start()
            if FROZEN:threading.Thread(target=cleanup_after_start,args=(self.root,),daemon=True).start()
            while True:
                try:action=self.tray.actions.get(timeout=.2)
                except queue.Empty:action=None
                if action in ('exit','restart'):break
                if isinstance(action,tuple) and len(action)==2 and action[0] in ('open_capture','export_capture'):
                    self.open_capture(action[1],export=action[0]=='export_capture')
                if isinstance(action,tuple) and len(action)==2 and action[0]=='rename_capture':
                    source,name=action[1]
                    try:self.library.rename(source,name,self.busy_paths())
                    except Exception as error:self.library.status='Could not rename battle: '+str(error)
                    self.menu.update(self.last_status or self.worker.status)
                if isinstance(action,tuple) and len(action)==2 and action[0]=='startup_update_available':
                    release=action[1]
                    if not (self.startup_check and self.startup_check.stopped.is_set()) and not self.updates.pending and not (self.updates.thread and self.updates.thread.is_alive()):
                        self.menu.offer_update(release[0],lambda accepted,release=release:
                            self.tray.actions.put(('startup_update_download',release)) if accepted else None)
                if isinstance(action,tuple) and len(action)==2 and action[0]=='startup_update_download':
                    self.updates.start(release=action[1],download_approved=True)
                if action in ('main_menu','open_reports'):self.menu.focus()
                if action=='open_folder':open_reports(self.root)
                if action=='build_missing':self.build_missing()
                if action=='check_updates':
                    if self.startup_check:self.startup_check.stop()
                    self.menu.cancel_update_offer()
                    self.maintenance.start(delete_html=True)
                    self.updates.start()
                if action=='about' and (self.about is None or not self.about.thread.is_alive()):
                    self.about=ProgressWindow(title='About Battle Logger',about=True).start()
                if action=='settings':
                    if self.settings_window is None or not self.settings_window.thread.is_alive():
                        self.settings_window=ProgressWindow(title='Battle Logger settings',settings=self.settings).start()
                    else:self.settings_window.focus()
                if action=='install_update':break
                try:
                    message=self.channel.get_nowait()
                    status=message['status']
                    errors=[r['error'] for r in message['reports'] if r['error']]
                    self.library.active_paths={Path(r['path']).resolve() for r in message['reports'] if not r['done']}
                    if errors:status='Saving error: '+errors[-1]
                    if status!=self.last_status:
                        self.last_status=status
                        self.tray.set_tooltip('WH3 Battle Logger · '+status)
                    self.menu.update(status)
                    request=message.get('late_start_request')
                    if request and request!=self.last_prompt:
                        self.last_prompt=request
                        self.menu.ask_late_start(request,self.worker.answer_late_start)
                    elif request is None and self.last_prompt is not None:
                        self.last_prompt=None
                        self.menu.cancel_late_start()
                except queue.Empty:pass
                if not self.worker.is_alive():
                    raise RuntimeError(self.worker.status or 'Battle logging stopped unexpectedly.')
                if not self.tray.thread.is_alive():
                    raise RuntimeError(self.tray.error or 'The notification icon stopped unexpectedly.')
                if not self.menu.thread.is_alive():
                    raise RuntimeError(self.menu.error or 'The main menu stopped unexpectedly.')
        finally:
            # Keep the tray alive until encrypted recording saving finishes.
            self.tray.set_tooltip('WH3 Battle Logger · Saving and exiting…')
            self.worker.stop_event.set()
            if self.startup_check:self.startup_check.stop()
            self.maintenance.stop()
            if self.worker.is_alive():self.worker.join()
            self.tray.stop()
            if self.about:self.about.close()
            if self.settings_window:self.settings_window.close()
            self.menu.close()
            self.viewers.close()
            if self.build_thread:self.build_thread.join()
        if self.updates.pending:
            launch_installer(self.updates.pending,Path(sys.executable).resolve().parent)
        return action=='restart'


def restart_command(root, rate, pid=None):
    command=[sys.executable]
    if not FROZEN:command+=['-B',str(Path(__file__).resolve())]
    command+=['--data-dir',str(root),'--rate',str(rate)]
    if pid is not None:command+=['--pid',str(pid)]
    return command


def focus_running_menu():
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.FindWindowW.argtypes=[w.LPCWSTR,w.LPCWSTR];user.FindWindowW.restype=w.HWND
    user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
    hwnd=user.FindWindowW(None,'Battle Logger tray')
    if hwnd:user.PostMessageW(hwnd,0x111,1,0)



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
    parser.add_argument('--export-log',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--view-log',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--view-key',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--viewer-check',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    handle=None;kernel=None;restart=False
    try:
        if os.name!='nt':raise RuntimeError('The release logger requires Windows.')
        if args.export_log:
            from report import convert
            from logfile import load_key
            from settings import load_report_options
            source=args.export_log.resolve();root=args.data_dir.resolve()
            if source.parent!=(root/'captures') or source.suffix.lower()!='.wh3log':raise ValueError('Invalid export recording path.')
            output=root/'captures/shareables'/(source.stem+'.html');output.parent.mkdir(parents=True,exist_ok=True)
            convert(source,load_key(root/'captures/logger.key'),output,recover_tail=True,report_options=load_report_options(root))
            return
        if args.view_log:
            from report_viewer import run_viewer
            run_viewer(args.view_log,args.data_dir,args.view_key,args.viewer_check)
            return
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
        if handle is None:
            focus_running_menu()
            return
        restart=BackgroundApp(root=args.data_dir,rate=args.rate,pid=args.pid).run()
    except Exception as error:
        directory=args.data_dir/'logs';directory.mkdir(parents=True,exist_ok=True)
        error_file='export-last-error.txt' if args.export_log else 'viewer-last-error.txt' if args.view_log else 'last-error.txt'
        (directory/error_file).write_text(traceback.format_exc(),encoding='utf-8')
        if args.export_log:raise SystemExit(1)
        if args.viewer_check:
            import json
            args.viewer_check.write_text(json.dumps(dict(success=False,error=traceback.format_exc())),encoding='utf-8')
            raise SystemExit(1)
        if args.view_log:
            detail='The recording could not be authenticated. Check that its logger.key matches.' if type(error).__name__=='InvalidTag' else (str(error) or type(error).__name__)
            silent_message('Could not open this recording.\n\n'+detail[:800]+'\n\nDetails: logs/'+error_file,'Cannot open recording')
        else:
            silent_message('Battle Logger stopped. Details are saved in logs/last-error.txt.','WARHAMMER III Battle Logger')
        raise SystemExit(1)
    finally:
        if handle:kernel.CloseHandle(handle)
    # The old collector has saved and released the single-instance mutex first.
    if restart:subprocess.Popen(restart_command(args.data_dir,args.rate,args.pid),creationflags=0x08000000)


if __name__=='__main__':main()
