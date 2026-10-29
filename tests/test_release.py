import ctypes
from ctypes import wintypes as w
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from release_app import BackgroundApp,open_reports
from tray import TrayIcon
from worker import Worker
from icons import ICON_PATH,load_tray_icon


class ReleaseTests(unittest.TestCase):
    def test_export_helper_bypasses_menu_tray_and_single_instance(self):
        from release_app import main
        with tempfile.TemporaryDirectory(dir=P/'build') as temp:
            root=Path(temp);source=root/'captures/Named battle.wh3log';source.parent.mkdir();source.write_bytes(b'fixture')
            (source.parent/'logger.key').write_bytes(bytes(32))
            with patch('sys.argv',['logger','--export-log',str(source),'--data-dir',str(root)]),patch('report.convert') as convert,patch('release_app.acquire_instance') as mutex,patch('release_app.BackgroundApp') as app:
                main();mutex.assert_not_called();app.assert_not_called()
                self.assertEqual(convert.call_args.args,(source.resolve(),bytes(32),root/'captures/shareables/Named battle.html'))
                self.assertTrue(convert.call_args.kwargs['recover_tail'])
            with patch('sys.argv',['logger','--export-log',str(source),'--data-dir',str(root)]),patch('report.convert',side_effect=OSError('fixture failure')),patch('release_app.silent_message') as message:
                with self.assertRaises(SystemExit) as error:main()
                self.assertEqual(error.exception.code,1);message.assert_not_called()
                self.assertIn('fixture failure',(root/'logs/export-last-error.txt').read_text(encoding='utf-8'))


    def test_report_command_opens_directory_not_an_html_file(self):
        with tempfile.TemporaryDirectory(dir=P/'build') as temp,patch('release_app.os.startfile') as launch:
            directory=open_reports(temp)
            self.assertTrue(directory.is_dir())
            launch.assert_called_once_with(str(Path(temp)/'captures'))

    def test_release_disables_live_summary_work_and_exit_joins_saving(self):
        worker=Worker(P,queue.Queue(1),preview=False)
        with patch('worker.Battle') as battle:
            worker.battle=battle.return_value
            worker.publish();battle.return_value.summary.assert_not_called()
        calls=[]
        class FakeWorker:
            def __init__(self):self.stop_event=threading.Event();self.status='Ready';self.running=False
            def start(self):self.running=True;calls.append('worker_started')
            def is_alive(self):return self.running
            def join(self):
                self_test.assertTrue(self.stop_event.is_set());calls.append('saved');self.running=False
        class FakeTray:
            def __init__(self):
                self.ready=threading.Event();self.ready.set();self.available=True;self.error=None
                self.thread=self;self.actions=queue.Queue();self.actions.put('open_reports');self.actions.put('check_updates');self.actions.put('exit')
            def start(self):calls.append('tray_started')
            def is_alive(self):return True
            def set_tooltip(self,text):pass
            def stop(self):calls.append('tray_stopped')
        self_test=self
        with patch('release_app.CaptureMaintenance'),patch('release_app.BackgroundApp.build_missing'),patch('release_app.MainMenu') as menu,patch('release_app.open_reports') as open_folder:
            app=BackgroundApp(worker=FakeWorker(),tray=FakeTray())
            with patch.object(app.updates,'start') as check:app.run()
            check.assert_called_once()
            self.assertEqual(app.maintenance.start.call_count,2)
            app.maintenance.start.assert_called_with(delete_html=True)
            app.maintenance.stop.assert_called_once()
            open_folder.assert_not_called()
            menu.return_value.start.assert_called_once()
            menu.return_value.focus.assert_called_once()
            menu.return_value.close.assert_called_once()
        self.assertEqual(calls,['tray_started','worker_started','saved','tray_stopped'])

    def test_log_icon_loads_and_native_tray_has_no_visible_window(self):
        self.assertTrue(ICON_PATH.is_file())
        tray=TrayIcon();tray.start()
        try:
            self.assertTrue(tray.ready.wait(5));self.assertTrue(tray.available,tray.error)
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.IsWindowVisible.argtypes=[w.HWND];user.IsWindowVisible.restype=w.BOOL
            self.assertFalse(user.IsWindowVisible(tray.hwnd))
            tray.set_tooltip('WH3 Battle Logger · Startup check')
        finally:tray.stop()
        self.assertFalse(tray.thread.is_alive());self.assertIsNone(tray.hwnd)


if __name__=='__main__':unittest.main()
