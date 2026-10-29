import json
from pathlib import Path
import re
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from settings import Settings,load_report_options
from report_assets import assets_for
from report import convert
from recorder import Recorder
from demo import frames


class SettingsTests(unittest.TestCase):
    def test_tray_settings_opens_once_then_focuses_and_closes_on_exit(self):
        from release_app import BackgroundApp
        worker=MagicMock();worker.is_alive.return_value=True;worker.stop_event=threading.Event()
        tray=MagicMock();tray.available=True;tray.ready=threading.Event();tray.ready.set();tray.thread.is_alive.return_value=True
        tray.actions=queue.Queue()
        for action in ('settings','settings','exit'):tray.actions.put(action)
        with tempfile.TemporaryDirectory() as d,patch('release_app.MainMenu'),patch('release_app.ProgressWindow') as window:
            current=window.return_value.start.return_value;current.thread.is_alive.return_value=True
            BackgroundApp(root=d,worker=worker,tray=tray).run()
            self.assertEqual(window.call_count,1);current.focus.assert_called_once();current.close.assert_called_once()
            self.assertEqual(window.call_args.kwargs['settings'].root,Path(d))

    def test_default_invalid_and_saved_options(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);store=Settings(root)
            self.assertEqual(store.report_options(),dict(icons=True))
            for raw in ('bad json','null','[]','{"report_options":null}','{"report_options":{"icons":"false"}}'):
                (root/'settings.json').write_text(raw,encoding='utf-8')
                self.assertTrue(load_report_options(root)['icons'])
            (root/'settings.json').write_text('{"future":1,"report_options":{"future":2}}',encoding='utf-8')
            store.save(icons=False);self.assertFalse(Settings(root).report_options()['icons'])
            saved=json.loads((root/'settings.json').read_text(encoding='utf-8'))
            self.assertEqual((saved['future'],saved['report_options']['future']),(1,2))
            self.assertFalse((root/'settings.json.tmp').exists())
            with self.assertRaises(ValueError):store.save(icons=0)
            store.save(icons=True);self.assertTrue(store.report_options()['icons'])

    def test_small_report_only_embeds_shared_question_but_keeps_stats_and_values(self):
        units=[dict(id='a',name='Steam Tank',side='Allied',army='1',first={},last=dict(unit_key='wh_main_emp_veh_steam_tank'))]
        full=assets_for(units);small=assets_for(units,icons=False)
        self.assertEqual(set(small['images']),{small['stats']['other']})
        self.assertEqual(set(small['stats'].values()),set(small['images']))
        self.assertEqual(small['unit_cards']['a'],small['stats']['other'])
        for key in ('unit_values_by_id','unit_info','statline','effect_texts'):
            self.assertEqual(full[key],small[key])
        self.assertFalse(small['icons_enabled']);self.assertTrue(full['icons_enabled'])

    def test_saved_preference_is_used_by_manual_export_and_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);captures=root/'captures';captures.mkdir();path=captures/'sample.wh3log';key=bytes(range(32))
            Settings(root).save(icons=False)
            recorder=Recorder(path,key,dict(source='synthetic'))
            for f in frames(2,2):recorder.submit(f)
            recorder.finish({});recorder.join(10)
            self.assertTrue(recorder.done.is_set());self.assertIsNone(recorder.error)
            self.assertIsNone(recorder.report_path);self.assertFalse(path.with_suffix('.html').exists())
            original=path.read_bytes();small=convert(path,key,root/'small.html',report_options=load_report_options(root)).read_text(encoding='utf-8')
            full=convert(path,key,root/'full.html',report_options=dict(icons=True)).read_text(encoding='utf-8')
            read=lambda html:json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S)[1])
            self.assertEqual(len(read(small)['assets']['images']),1)
            self.assertEqual(read(full)['units'],read(small)['units'])
            self.assertLess(len(small),len(full));self.assertEqual(path.read_bytes(),original)
