import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch,MagicMock
from urllib.request import Request,urlopen
from urllib.error import HTTPError

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from demo import frames
from logfile import LogWriter,load_key
from recorder import Recorder
from report import convert
from report_data import read_summary
from report_library import ReportLibrary
from viewer_server import ViewerSession
from viewer_cache import ViewerCache,cleanup_stale_caches,remove_cache
from viewer_manager import ViewerManager,viewer_command
from viewer_preferences import ViewerPreferences


class ViewerTests(unittest.TestCase):
    def recording(self,root,complete=True):
        path=Path(root)/'captures/test.wh3log';key=load_key(path.parent/'logger.key',True)
        writer=LogWriter(path,key,dict(source='synthetic'))
        for frame in frames(2,6):writer.write(frame)
        if complete:writer.close({})
        else:writer.stream.close()
        return path,key

    def test_recording_finishes_without_rendering_or_creating_html(self):
        with tempfile.TemporaryDirectory() as d,patch('report_assets.assets_for',side_effect=AssertionError('No report asset work during recording')):
            path=Path(d)/'captures/log.wh3log';recorder=Recorder(path,bytes(32),{})
            for frame in frames(2,3):recorder.submit(frame)
            recorder.finish({});recorder.join(10)
            self.assertIsNone(recorder.error);self.assertIsNone(recorder.report_path)
            self.assertFalse(path.with_suffix('.html').exists())
            self.assertEqual(read_summary(path,bytes(32))['samples'],4)

    def test_shared_assets_are_not_read_or_base64_encoded_when_opening(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d);original=path.read_bytes();read_bytes=Path.read_bytes
            def guarded(path):
                if path.suffix.lower()=='.png':raise AssertionError('PNG read while constructing report data')
                return read_bytes(path)
            with patch.object(Path,'read_bytes',guarded):session=ViewerSession(path,key,d).load_now()
            data=json.loads(session.payload)
            assets=json.loads(session.assets_payload)
            self.assertTrue(assets['images'])
            self.assertTrue(all(url.startswith(session.prefix+'assets/game/') for url in assets['images'].values()))
            self.assertNotIn(b'data:image',session.payload)
            self.assertEqual(data['units'],read_summary(path,key)['units'])
            self.assertEqual(path.read_bytes(),original);self.assertFalse(path.with_suffix('.html').exists())

    def test_server_exposes_only_current_data_renderer_and_whitelisted_assets(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d)
            with ViewerSession(path,key,d) as session:
                self.assertTrue(session.ready.wait(10));self.assertIsNone(session.error)
                with urlopen(session.url) as response:
                    shell=response.read();self.assertNotIn(b'__DATA__',shell)
                    self.assertEqual(response.headers['Cache-Control'],'no-store')
                with urlopen(session.origin+session.prefix+'summary.json') as response:data=json.load(response)
                with urlopen(session.origin+session.prefix+'assets.json') as response:assets=json.load(response)
                image=next(iter(assets['images'].values()))
                with urlopen(session.origin+image) as response:self.assertEqual(response.read(8),b'\x89PNG\r\n\x1a\n')
                for relative in ('/wrong/index.html',session.prefix+'logger.key',session.prefix+'assets/game/../../logger.key'):
                    with self.assertRaises(HTTPError) as error:urlopen(session.origin+relative)
                    self.assertEqual(error.exception.code,404)
                with self.assertRaises(HTTPError) as error:urlopen(Request(session.url,headers={'Host':'untrusted.example'}))
                self.assertEqual(error.exception.code,403)
            self.assertIsNone(session.payload);self.assertFalse(session.images)

    def test_interrupted_capture_opens_without_rewriting_or_exporting(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d,False);path.write_bytes(path.read_bytes()+b'\x30\x00');original=path.read_bytes()
            session=ViewerSession(path,key,d).load_now();data=json.loads(session.payload)
            self.assertTrue(data['capture']['incomplete']);self.assertTrue(data['recording_warnings'])
            self.assertIsNone(data['battle_result']);self.assertEqual(path.read_bytes(),original)
            self.assertFalse(path.with_suffix('.html').exists())
            with self.assertRaises(Exception):ViewerSession(path,bytes(32),d).load_now()

    def test_shell_opens_before_decode_and_core_data_precedes_assets(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d);reading=threading.Event();allow_read=threading.Event();assets_started=threading.Event();allow_assets=threading.Event()
            from viewer_server import assets_for
            def read(*args,**kwargs):
                reading.set();allow_read.wait(10)
                return read_summary(*args,**kwargs)
            def asset_work(*args,**kwargs):
                assets_started.set();allow_assets.wait(10)
                return assets_for(*args,**kwargs)
            try:
                with patch('viewer_server.read_summary',side_effect=read),patch('viewer_server.assets_for',side_effect=asset_work):
                    with ViewerSession(path,key,d,autoload=False) as session:
                        with urlopen(session.url) as response:self.assertIn(b'Opening recording',response.read())
                        self.assertFalse(reading.is_set())
                        with urlopen(session.origin+session.prefix+'summary.json') as response:self.assertEqual(response.status,202)
                        session.start_loading();self.assertTrue(reading.wait(5))
                        with urlopen(session.url) as response:self.assertEqual(response.status,200)
                        allow_read.set();self.assertTrue(assets_started.wait(5));self.assertTrue(session.core_ready.is_set());self.assertFalse(session.ready.is_set())
                        with urlopen(session.origin+session.prefix+'summary.json') as response:self.assertTrue(json.load(response)['units'])
                        with urlopen(session.origin+session.prefix+'loading.json') as response:self.assertEqual(json.load(response)['stage'],'assets')
                        allow_assets.set();self.assertTrue(session.ready.wait(10));self.assertIsNone(session.error)
            finally:allow_read.set();allow_assets.set()

    def test_close_cancels_decode_and_releases_session_data(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d);started=threading.Event()
            def read(*args,**kwargs):
                started.set();self.assertTrue(kwargs['cancel'].wait(5));raise InterruptedError('Report closed.')
            with patch('viewer_server.read_summary',side_effect=read):
                with ViewerSession(path,key,d) as session:self.assertTrue(started.wait(5))
            self.assertFalse(session.loader.is_alive());self.assertIsNone(session.payload);self.assertIsNone(session.key)

    def test_library_lists_logs_without_html_and_export_remains_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d);(path.parent/'legacy.html').write_text('retained',encoding='utf-8')
            library=ReportLibrary(d);self.assertEqual([e['name'] for e in library.entries()],['test'])
            self.assertFalse(path.with_suffix('.html').exists())
            output=Path(d)/'captures/shareables/test.html'
            with patch('report_library.open_folder') as explorer:
                library.export_html(path);self.assertTrue(output.exists(),library.status)
                before=output.read_bytes();library.export_html(path)
                self.assertEqual(output.read_bytes(),before)
                self.assertEqual(len(list(output.parent.glob('*.html'))),1)
                self.assertEqual(explorer.call_count,2)
                explorer.assert_called_with(str(output.parent.resolve()))
            self.assertEqual((path.parent/'legacy.html').read_text(encoding='utf-8'),'retained')

    def test_browser_cache_is_removed_but_user_choices_are_retained(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d);store=ViewerPreferences(d,path)
            store.save('graphs','["damage","models","hp_cached","healing_cap_remaining"]')
            with ViewerCache(d) as cache:
                (cache.path/'browser').mkdir();(cache.path/'browser/test').write_text('temporary',encoding='utf-8')
                cleanup_stale_caches(d)
                self.assertTrue(cache.path.exists(),'An active viewer cache must not be removed.')
            self.assertFalse(cache.path.exists());self.assertIn('graphs',store.load())
            with self.assertRaises(ValueError):remove_cache(Path(d),Path(d))

    def test_stale_cache_cleanup_respects_live_and_inaccessible_processes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'cache/report-viewer';path=root/'view-stale';path.mkdir(parents=True)
            (path/'owner.json').write_text(json.dumps(dict(schema=1,pid=123,stamp=456)),encoding='utf-8')
            for state in (None,456):
                with patch('viewer_cache.process_stamp',return_value=state):cleanup_stale_caches(d)
                self.assertTrue(path.exists())
            with patch('viewer_cache.process_stamp',return_value=789):cleanup_stale_caches(d)
            self.assertFalse(path.exists())

    def test_preference_writes_require_current_origin_and_token(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d)
            with ViewerSession(path,key,d) as session:
                url=session.origin+session.prefix+'preferences.json'
                body=json.dumps(dict(name='hide_explanations',value='true')).encode()
                with self.assertRaises(HTTPError) as error:urlopen(Request(url,data=body))
                self.assertEqual(error.exception.code,403)
                headers={'Origin':session.origin,'X-WH3-Viewer':session.token,'Content-Type':'application/json'}
                with urlopen(Request(url,data=body,headers=headers)) as response:self.assertEqual(response.status,204)
                with urlopen(url) as response:self.assertEqual(json.load(response)['hide_explanations'],'true')
                bad=json.dumps(dict(name='../logger.key',value='true')).encode()
                with self.assertRaises(HTTPError) as error:urlopen(Request(url,data=bad,headers=headers))
                self.assertEqual(error.exception.code,400)

    def test_capture_launch_uses_app_process_and_duplicate_focus(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.recording(d);process=MagicMock();process.poll.return_value=None;process.pid=123
            with patch('viewer_manager.subprocess.Popen',return_value=process) as launch,patch('viewer_manager.viewer_windows',return_value=(MagicMock(),[1])):
                manager=ViewerManager(d);manager.open(path);manager.open(path)
                self.assertEqual(launch.call_count,1)
                args=launch.call_args.args[0];self.assertIn('--view-log',args);self.assertIn(str(path.resolve()),args)
            with patch('viewer_manager.FROZEN',True):self.assertNotIn('release_app.py',viewer_command(path,d))


class CommunityLinkTests(unittest.TestCase):
    def test_only_the_two_community_links_open_in_the_default_browser(self):
        from report_viewer import NativePopouts,COMMUNITY_LINKS
        from types import SimpleNamespace
        controller=NativePopouts(None,None)
        with patch('report_viewer.webbrowser.open') as browser:
            for uri in COMMUNITY_LINKS:
                event=SimpleNamespace(Uri=uri,Handled=False)
                controller.open(None,event)
                self.assertTrue(event.Handled);browser.assert_called_with(uri)
            self.assertEqual(browser.call_count,2)
            for uri in ('https://example.com','file:///C:/Windows/notepad.exe','https://discord.com/invite/v27y7AW7Kz/extra'):
                event=SimpleNamespace(Uri=uri,Handled=False)
                controller.open(None,event);self.assertTrue(event.Handled)
            self.assertEqual(browser.call_count,2)


if __name__=='__main__':unittest.main()
