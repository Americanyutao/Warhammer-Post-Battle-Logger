import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
import updater

class UpdateTests(unittest.TestCase):
    def release(self, tag='v99.0.0'):
        return dict(tag_name=tag, assets=[dict(name=updater.ASSET,size=10,digest='sha256:'+'0'*64,browser_download_url=f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/app.zip')])
    def fetch(self, release):
        response=io.BytesIO(json.dumps(release).encode())
        with patch('updater.urllib.request.urlopen',return_value=response):return updater.latest_release()
    def test_versions_and_release_selection(self):
        self.assertGreater(updater.version_tuple('v1.10.0'),updater.version_tuple('1.9.0'))
        self.assertIsNone(self.fetch(self.release('v1.0.0')))
        self.assertIsNotNone(self.fetch(self.release()))
        for tag in ('latest','v2.0.0-beta', 'v1.2'):
            with self.assertRaises(ValueError):updater.version_tuple(tag)
    def test_untrusted_or_incomplete_release_rejected(self):
        for field,value in [('digest',None),('size',updater.MAX_DOWNLOAD+1),('browser_download_url','https://example.com/app.zip')]:
            release=self.release();release['assets'][0][field]=value
            with self.assertRaises(ValueError):self.fetch(release)
    def package(self, directory, extra=None):
        archive=Path(directory)/'app.zip'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('WH3BattleLogger/WH3BattleLogger.exe',b'new')
            z.writestr('WH3BattleLogger/_internal/python313.dll',b'runtime')
            z.writestr('WH3BattleLogger/captures/logger.key',b'evil')
            if extra:z.writestr(extra,b'bad')
        return archive
    def test_unpack_preserves_private_data_boundary_and_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            stage=updater.unpack_package(self.package(temp),Path(temp)/'stage')
            self.assertFalse((stage/'captures').exists())
            for path in ('../escape','C:/escape','WH3BattleLogger/..\\escape'):
                with self.assertRaises(ValueError):updater.unpack_package(self.package(temp,path),Path(temp)/'bad')
    def test_install_and_copy_failure_rollback_preserve_key(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);stage=updater.unpack_package(self.package(temp),root/'stage')
            dest=root/'installed';(dest/'captures').mkdir(parents=True)
            (dest/'captures/logger.key').write_bytes(b'private')
            (dest/'WH3BattleLogger.exe').write_bytes(b'old')
            (dest/'_internal').mkdir();(dest/'_internal/old.dll').write_bytes(b'old runtime')
            with patch('updater.shutil.copytree',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):updater.install_files(stage,dest)
            self.assertEqual((dest/'WH3BattleLogger.exe').read_bytes(),b'old')
            self.assertTrue((dest/'_internal/old.dll').exists())
            backup=updater.install_files(stage,dest)
            self.assertEqual((backup/'WH3BattleLogger.exe').read_bytes(),b'old')
            self.assertEqual((dest/'WH3BattleLogger.exe').read_bytes(),b'new')
            self.assertFalse((dest/'_internal/old.dll').exists())
            self.assertEqual((dest/'captures/logger.key').read_bytes(),b'private')
    def test_checksum_failure_leaves_no_staged_app(self):
        asset=self.release()['assets'][0];asset['size']=3
        with patch('updater.urllib.request.urlopen',return_value=io.BytesIO(b'bad')):
            with self.assertRaises(ValueError):updater.download_update(asset)
    def test_check_is_single_flight(self):
        from threading import Event
        gate=Event()
        checker=updater.UpdateChecker(None)
        with patch.object(checker,'run',side_effect=lambda:gate.wait(2)) as run:
            checker.start();thread=checker.thread;checker.start()
            self.assertIs(thread,checker.thread);gate.set();thread.join();run.assert_called_once()

class UpdateLifecycleTests(unittest.TestCase):
    def test_updater_waits_for_original_process_before_installing(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);stage=root/'stage';stage.mkdir();dest=root/'installed';dest.mkdir()
            (dest/'WH3BattleLogger.exe').write_bytes(b'old')
            process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(0.3)'])
            try:
                with patch('updater.sys.executable',str(stage/'WH3BattleLogger.exe')),patch('updater.install_files') as install,patch('updater.subprocess.Popen') as launch:
                    updater.apply_update(dest,process.pid)
                    self.assertIsNotNone(process.poll())
                    # Windows runners can supply an 8.3 TEMP path; the updater
                    # intentionally resolves it to the full installation path.
                    install.assert_called_once_with(stage.resolve(),dest.resolve())
                    launch.assert_called_once()
            finally:process.wait(timeout=5)

    def test_update_exit_saves_before_launching_helper(self):
        from release_app import BackgroundApp
        from threading import Event
        import queue
        calls=[]
        class Worker:
            stop_event=Event();status='Ready';running=False
            def start(self):self.running=True
            def is_alive(self):return self.running
            def join(self):calls.append('saved');self.running=False
        class Tray:
            available=True;error=None;ready=Event();ready.set()
            actions=queue.Queue();actions.put('install_update')
            def __init__(self):self.thread=self
            def start(self):pass
            def is_alive(self):return True
            def set_tooltip(self,text):pass
            def stop(self):calls.append('tray stopped')
        app=BackgroundApp(worker=Worker(),tray=Tray());app.updates.pending=Path('staged')
        with patch('release_app.launch_installer',side_effect=lambda *args:calls.append('installer')):
            app.run()
        self.assertEqual(calls,['saved','tray stopped','installer'])

if __name__=='__main__':unittest.main()
