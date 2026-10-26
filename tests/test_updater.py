import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'src'),str(P/'tools')]
import updater
from update_manifest import validate_manifest, app_path, file_hash, MANIFEST
from package_update import package_release
from update_ui import Cancelled

class Response(io.BytesIO):
    status=206
    def __init__(self,blob,start,end,total):
        super().__init__(blob[start:end]);self.headers={'Content-Range':f'bytes {start}-{end-1}/{total}'}

class FakeProgress:
    def __init__(self,*args,**kwargs):pass
    def start(self):return self
    def update(self,*args):pass
    def close(self):pass

class UpdateTests(unittest.TestCase):
    def release(self,tag='v99.0.0'):
        def asset(name,size):return dict(name=name,size=size,digest='sha256:'+'0'*64,browser_download_url=f'https://github.com/{updater.REPOSITORY}/releases/download/{tag}/{name}')
        return dict(tag_name=tag,assets=[asset(updater.ASSET,10),asset(MANIFEST,10)])
    def fetch(self,release):
        with patch('updater.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(release).encode())):
            return updater.latest_release()
    def test_versions_and_release_selection(self):
        self.assertGreater(updater.version_tuple('v1.10.0'),updater.version_tuple('1.9.0'))
        self.assertIsNone(self.fetch(self.release('v1.0.0')))
        self.assertIsNotNone(self.fetch(self.release()))
        for tag in ('latest','v2.0.0-beta','v1.2'):
            with self.assertRaises(ValueError):updater.version_tuple(tag)
    def test_untrusted_or_incomplete_release_rejected(self):
        for field,value in [('digest',None),('size',updater.MAX_DOWNLOAD+1),('browser_download_url','https://example.com/app.zip')]:
            release=self.release();release['assets'][0][field]=value
            with self.assertRaises(ValueError):self.fetch(release)
        release=self.release();release['assets'].pop()
        with self.assertRaisesRegex(ValueError,'missing'):self.fetch(release)
    def test_metadata_checksum_failure(self):
        asset=self.release()['assets'][1];asset['size']=3
        with patch('updater.urllib.request.urlopen',return_value=io.BytesIO(b'bad')):
            with self.assertRaises(ValueError):updater.read_verified(asset)
    def test_compressed_manifest_is_verified_and_bounded(self):
        import gzip
        data=dict(schema=1,version='9.0.0')
        compressed=gzip.compress(json.dumps(data).encode())
        with patch('updater.read_verified',return_value=compressed):
            self.assertEqual(updater.read_manifest({}),data)
        with patch('updater.MAX_MANIFEST',8),patch('updater.read_verified',return_value=compressed):
            with self.assertRaises(ValueError):updater.read_manifest({})

    def test_path_validation_blocks_user_data_and_windows_escapes(self):
        for path in ('../escape','C:/escape','_internal/..\\escape','captures/logger.key','_internal/CON.txt','_internal/file.','_internal//file','_internal/../x'):
            with self.subTest(path=path),self.assertRaises(ValueError):app_path(path)
    def test_check_is_single_flight(self):
        gate=threading.Event();checker=updater.UpdateChecker(None)
        with patch.object(checker,'run',side_effect=lambda:gate.wait(2)) as run:
            checker.start();thread=checker.thread;checker.start()
            self.assertIs(thread,checker.thread);gate.set();thread.join();run.assert_called_once()

class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.old=self.root/'installed';self.new=self.root/'new'
        for folder in (self.old,self.new):
            (folder/'_internal/assets').mkdir(parents=True)
            (folder/'_internal/python313.dll').write_bytes(b'runtime')
            (folder/'WH3BattleLogger.exe').write_bytes(b'old executable')
        image=os.urandom(128*1024)
        for folder in (self.old,self.new):(folder/'_internal/assets/image.png').write_bytes(image)
        (self.old/'_internal/obsolete.dll').write_bytes(b'obsolete')
        (self.old/'captures').mkdir();(self.old/'captures/logger.key').write_bytes(b'private')
        (self.old/'captures/report.html').write_bytes(b'old report')
        (self.new/'WH3BattleLogger.exe').write_bytes(b'new executable')
        (self.new/'_internal/report.css').write_bytes(b'new style')
        (self.new/'_internal/empty').write_bytes(b'')
        self.manifest=package_release(self.new,self.root/'publish','9.0.0')
        self.blob=(self.root/'publish'/updater.ASSET).read_bytes()
        self.asset=dict(size=len(self.blob),browser_download_url='https://example.invalid/app.zip')
        self.requests=[]
    def network(self,req,timeout=0):
        value=req.get_header('Range');self.requests.append(value)
        self.assertIsNotNone(value,'Only byte-range downloads are allowed')
        start,end=map(int,value[6:].split('-'))
        return Response(self.blob,start,end+1,len(self.blob))
    def prepare(self):
        files=validate_manifest(self.manifest,'v9.0.0',len(self.blob))
        changed,removed=updater.plan_update(files,self.old)
        with patch('updater.urllib.request.urlopen',side_effect=self.network):
            stage=updater.stage_update(self.asset,files,changed,removed,self.old)
        return stage,changed,removed
    def test_only_changed_bytes_downloaded_and_one_copy_after_install(self):
        stage,changed,removed=self.prepare()
        self.assertNotIn('_internal/assets/image.png',[f['path'] for f in changed])
        self.assertEqual(removed,['_internal/obsolete.dll'])
        transferred=sum(int(r.split('-')[1])-int(r.split('=')[1].split('-')[0])+1 for r in self.requests)
        self.assertLess(transferred,len(self.blob)//10)
        self.assertTrue(os.path.samefile(stage/'_internal/assets/image.png',self.old/'_internal/assets/image.png'))
        self.assertFalse(os.path.samefile(stage/'_internal/python313.dll',self.old/'_internal/python313.dll'))
        updater.install_files(stage,self.old)
        self.assertEqual((self.old/'WH3BattleLogger.exe').read_bytes(),b'new executable')
        self.assertFalse((self.old/'_internal/obsolete.dll').exists())
        self.assertEqual((self.old/'captures/logger.key').read_bytes(),b'private')
        self.assertEqual((self.old/'captures/report.html').read_bytes(),b'old report')
        self.assertFalse((stage.parent/'rollback').exists())
        self.assertEqual(list(self.old.glob('.update-backup-*')),[])
        with patch('updater.sys.executable',str(self.old/'WH3BattleLogger.exe')),patch('updater.wait_for_exit'):
            updater.cleanup_update(stage.parent,123)
        self.assertEqual(sorted(p.name for p in self.old.iterdir()),['WH3BattleLogger.exe','_internal','captures'])
    def test_failed_copy_restores_old_files_and_private_data(self):
        stage,_,_=self.prepare()
        with patch('updater.shutil.copy2',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):updater.install_files(stage,self.old)
        self.assertEqual((self.old/'WH3BattleLogger.exe').read_bytes(),b'old executable')
        self.assertEqual((self.old/'captures/logger.key').read_bytes(),b'private')
        self.assertTrue((self.old/'_internal/obsolete.dll').is_file())
        self.assertFalse((stage.parent/'rollback').exists())
    def test_legacy_full_zip_helper_also_leaves_no_backup(self):
        updater.install_files(self.new,self.old)
        self.assertEqual((self.old/'WH3BattleLogger.exe').read_bytes(),b'new executable')
        self.assertFalse((self.old/'_internal/obsolete.dll').exists())
        self.assertEqual(list(self.old.glob('.update-backup-*')),[])
    def test_corrupt_reused_file_is_downloaded_and_missing_file_repaired(self):
        (self.old/'_internal/python313.dll').write_bytes(b'corrupt')
        files=self.manifest['files'];changed,_=updater.plan_update(files,self.old)
        self.assertIn('_internal/python313.dll',[f['path'] for f in changed])
    def test_server_ignoring_range_is_rejected_without_full_download(self):
        files=self.manifest['files'];changed,removed=updater.plan_update(files,self.old)
        response=Response(self.blob,0,1,len(self.blob));response.status=200
        with patch('updater.urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'partial downloads'):updater.stage_update(self.asset,files,changed,removed,self.old)
        self.assertEqual(list(self.old.glob('wh3-logger-update-*')),[])
    def test_corrupted_download_never_installs(self):
        self.blob=b'X'*len(self.blob)
        with self.assertRaises((ValueError,updater.zlib.error)):self.prepare()
        self.assertEqual(list(self.old.glob('wh3-logger-update-*')),[])
        self.assertEqual((self.old/'WH3BattleLogger.exe').read_bytes(),b'old executable')
    def test_cancel_cleans_staging_and_preserves_app(self):
        def cancel(*args):raise Cancelled()
        files=self.manifest['files'];changed,removed=updater.plan_update(files,self.old)
        with patch('updater.urllib.request.urlopen',side_effect=self.network):
            with self.assertRaises(Cancelled):updater.stage_update(self.asset,files,changed,removed,self.old,cancel)
        self.assertEqual(list(self.old.glob('wh3-logger-update-*')),[])
        self.assertEqual((self.old/'WH3BattleLogger.exe').read_bytes(),b'old executable')
    def test_real_http_range_download_installs_without_fetching_images(self):
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        received=[];blob=self.blob
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                value=self.headers.get('Range')
                if not value:
                    self.send_error(400);return
                first,last=map(int,value[6:].split('-'))
                payload=blob[first:last+1];received.append(len(payload))
                self.send_response(206)
                self.send_header('Content-Range',f'bytes {first}-{last}/{len(blob)}')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers();self.wfile.write(payload)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            asset=dict(self.asset,browser_download_url=f'http://127.0.0.1:{server.server_port}/app.zip')
            changed,removed=updater.plan_update(self.manifest['files'],self.old)
            stage=updater.stage_update(asset,self.manifest['files'],changed,removed,self.old)
            updater.install_files(stage,self.old)
            self.assertEqual((self.old/'WH3BattleLogger.exe').read_bytes(),b'new executable')
            self.assertLess(sum(received),len(blob)//10)
        finally:server.shutdown();server.server_close();thread.join()

    def test_manifest_bounds_duplicate_and_release_mismatch(self):
        for mutate in (lambda d:d.update(version='1.0.0'),lambda d:d['files'].append(d['files'][0].copy()),lambda d:d['files'][0].update(offset=len(self.blob)+1),lambda d:d['files'][0].update(path='captures/logger.key')):
            data=json.loads(json.dumps(self.manifest));mutate(data)
            with self.assertRaises(ValueError):validate_manifest(data,'v9.0.0',len(self.blob))
    def test_cleanup_rejects_unrelated_directory_and_removes_legacy_backup(self):
        with patch('updater.sys.executable',str(self.old/'WH3BattleLogger.exe')):
            with self.assertRaises(ValueError):updater.cleanup_update(self.root,1)
        backup=self.old/('.update-backup-'+'a'*32);backup.mkdir();(backup/'WH3BattleLogger.exe').write_bytes(b'old')
        keep=self.old/('.update-backup-'+'b'*32);keep.mkdir();(keep/'notes.txt').write_text('mine')
        updater.cleanup_legacy_backups(self.old)
        self.assertFalse(backup.exists());self.assertTrue(keep.exists())

class UpdateLifecycleTests(unittest.TestCase):
    def test_updater_waits_for_original_process_before_installing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();stage=root/'stage';stage.mkdir();dest=root/'installed';dest.mkdir()
            (dest/'WH3BattleLogger.exe').write_bytes(b'old')
            process=subprocess.Popen([sys.executable,'-c','import time;time.sleep(0.3)'])
            try:
                with patch('updater.sys.executable',str(stage/'WH3BattleLogger.exe')),patch('updater.install_files') as install,patch('updater.subprocess.Popen') as launch,patch('updater.ProgressWindow',FakeProgress):
                    updater.apply_update(dest,process.pid)
                    self.assertIsNotNone(process.poll())
                    self.assertEqual(install.call_args.args[:2],(stage.resolve(),dest.resolve()))
                    launch.assert_called_once()
                    self.assertIn('--cleanup-update',launch.call_args.args[0])
            finally:process.wait(timeout=5)
    def test_update_exit_saves_before_launching_helper(self):
        from release_app import BackgroundApp
        import queue
        calls=[]
        class Worker:
            stop_event=threading.Event();status='Ready';running=False
            def start(self):self.running=True
            def is_alive(self):return self.running
            def join(self):calls.append('saved');self.running=False
        class Tray:
            available=True;error=None;ready=threading.Event();ready.set()
            actions=queue.Queue();actions.put('install_update')
            def __init__(self):self.thread=self
            def start(self):pass
            def is_alive(self):return True
            def set_tooltip(self,text):pass
            def stop(self):calls.append('tray stopped')
        app=BackgroundApp(worker=Worker(),tray=Tray());app.updates.pending=Path('staged')
        with patch('release_app.launch_installer',side_effect=lambda *args:calls.append('installer')):app.run()
        self.assertEqual(calls,['saved','tray stopped','installer'])

if __name__=='__main__':unittest.main()
