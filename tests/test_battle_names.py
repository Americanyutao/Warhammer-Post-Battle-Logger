import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'src'))
from battle_names import validate_name,unique_capture_path
from report_library import ReportLibrary
from viewer_preferences import ViewerPreferences
from logfile import LogWriter,load_key
from demo import frames

class BattleNameTests(unittest.TestCase):
    def test_timestamp_collisions_do_not_overwrite_and_invalid_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            first=unique_capture_path(d,'battle-20261028-120000');first.parent.mkdir();first.write_bytes(b'first')
            second=unique_capture_path(d,first.stem);self.assertEqual(second.stem,first.stem+' (1)');second.write_bytes(b'second')
            self.assertEqual(unique_capture_path(d,first.stem).stem,first.stem+' (2)')
        for name in ('','../escape','a/b','CON','NUL.txt','trail.',' leading','a:b','a\x00b'):
            with self.subTest(name=name),self.assertRaises(ValueError):validate_name(name)
        self.assertEqual(validate_name('My battle — 勝利'),'My battle — 勝利')

    def test_rename_moves_exports_preferences_and_corrections_without_touching_log_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'captures';folder.mkdir();source=folder/'old.wh3log';source.write_bytes(b'unchanged encrypted content')
            (root/'captures/shareables').mkdir(parents=True);(root/'captures/shareables/old.html').write_text('shareable')
            source.with_suffix('.html').write_text('legacy export')
            prefs=ViewerPreferences(root,source);prefs.save('unit_values','{"u":1500}')
            (root/'report-corrections.json').write_text(json.dumps({source.name:{'outcome':'Victory'},'other.wh3log':{'outcome':'Draw'}}))
            destination=ReportLibrary(root).rename(source,'My named battle')
            self.assertEqual(destination.read_bytes(),b'unchanged encrypted content');self.assertFalse(source.exists())
            self.assertEqual((root/'captures/shareables/My named battle.html').read_text(),'shareable')
            self.assertTrue(destination.with_suffix('.html').exists())
            self.assertEqual(ViewerPreferences(root,destination).load()['unit_values'],'{"u":1500}')
            corrections=json.loads((root/'report-corrections.json').read_text());self.assertIn(destination.name,corrections);self.assertNotIn(source.name,corrections)
            self.assertIn('other.wh3log',corrections)

    def test_busy_battle_cannot_be_renamed_and_failed_move_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'captures';folder.mkdir();source=folder/'old.wh3log';source.write_bytes(b'keep');source.with_suffix('.html').write_text('html')
            library=ReportLibrary(root)
            with self.assertRaises(ValueError):library.rename(source,'new',{source.resolve()})
            rename=Path.rename
            def fail_html(path,target):
                if path.suffix=='.html':raise PermissionError('locked')
                return rename(path,target)
            with patch.object(Path,'rename',fail_html),self.assertRaises(PermissionError):library.rename(source,'new')
            self.assertEqual(source.read_bytes(),b'keep');self.assertTrue(source.with_suffix('.html').exists());self.assertFalse((folder/'new.wh3log').exists())

    def test_legacy_suffix_cleanup_preserves_custom_names_and_resolves_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'captures';folder.mkdir()
            for name in ('battle-20261028-120000-1234abcd','battle-20261028-120000-1234abce','My battle'):(folder/(name+'.wh3log')).write_bytes(name.encode())
            library=ReportLibrary(d);changes=library.clean_legacy_names()
            self.assertEqual(len(changes),2);self.assertTrue((folder/'battle-20261028-120000.wh3log').exists());self.assertTrue((folder/'battle-20261028-120000 (1).wh3log').exists());self.assertTrue((folder/'My battle.wh3log').exists())
            self.assertEqual(library.clean_legacy_names(),[])

    def test_packaged_export_is_windowless_and_waits_before_opening_folder(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=P/'build') as temp:
            root=Path(temp);source=root/'captures/Named battle.wh3log';source.parent.mkdir();source.write_bytes(b'fixture')
            output=source.parent/'shareables/Named battle.html'
            def generate(command,**options):
                self.assertIn('--export-log',command);self.assertIn(str(source.resolve()),command)
                self.assertEqual(options['creationflags'],0x08000000)
                output.write_text('finished export',encoding='utf-8');return SimpleNamespace(returncode=0)
            with patch('report_library.FROZEN',True),patch('report_library.subprocess.run',side_effect=generate) as process,patch('report_library.convert') as inline,patch('report_library.open_folder') as explorer:
                library=ReportLibrary(root);library.export_html(source)
                process.assert_called_once();inline.assert_not_called();explorer.assert_called_once_with(str(output.parent.resolve()))
            with patch('report_library.FROZEN',True),patch('report_library.subprocess.run',return_value=SimpleNamespace(returncode=1)),patch('report_library.open_folder') as explorer:
                library.export_html(source);explorer.assert_not_called();self.assertIn('Could not export HTML',library.status)

    def test_export_named_battle_has_matching_filename_and_title_and_opens_explorer(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'captures/old.wh3log';key=load_key(source.parent/'logger.key',True)
            writer=LogWriter(source,key,{})
            for frame in frames(1,2):writer.write(frame)
            writer.close({});library=ReportLibrary(root);source=library.rename(source,'Custom battle')
            with patch('report_library.open_folder') as explorer:
                library.export_html(source);output=root/'captures/shareables/Custom battle.html'
                self.assertTrue(output.exists(),library.status)
                data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',output.read_text(encoding='utf-8'),re.S)[1])
                self.assertEqual(data['report_filename'],'Custom battle')
                explorer.assert_called_once_with(str((root/'captures/shareables').resolve()))
            with patch('report_library.convert',side_effect=OSError('failed')),patch('report_library.open_folder') as explorer:
                library.export_html(source);explorer.assert_not_called()

if __name__=='__main__':unittest.main()
