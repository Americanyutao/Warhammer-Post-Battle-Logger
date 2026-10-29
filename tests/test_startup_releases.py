import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import unittest
import threading
from unittest.mock import MagicMock,patch

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
import release_notes
from release_notes import cached_notes,save_notes,summarize_notes,fetch_release
from updater import StartupReleaseCheck,UpdateChecker
from version import VERSION


class ReleaseNoteTests(unittest.TestCase):
    def test_menu_yes_starts_download_and_no_keeps_current_app_running(self):
        from release_app import BackgroundApp
        for accepted in (False,True):
            with self.subTest(accepted=accepted),tempfile.TemporaryDirectory() as d,patch('release_app.MainMenu') as menus,patch('release_app.CaptureMaintenance'):
                worker=MagicMock();worker.is_alive.return_value=True;worker.stop_event=threading.Event()
                tray=MagicMock();tray.available=True;tray.ready=threading.Event();tray.ready.set()
                tray.actions=queue.Queue();release=('v99.0.0',{'metadata':'verified'})
                tray.actions.put(('startup_update_available',release))
                def answer(tag,callback):callback(accepted);tray.actions.put('exit')
                menus.return_value.offer_update.side_effect=answer
                app=BackgroundApp(d,worker=worker,tray=tray)
                with patch.object(app.updates,'start') as start:app.run()
                if accepted:start.assert_called_once_with(release=release,download_approved=True)
                else:start.assert_not_called()
                menus.return_value.offer_update.assert_called_once()

    def test_summary_keeps_bullet_meaning_without_markdown_or_html(self):
        body='## Version\n\n- **Unit stats:** preserve [timelines](https://example.invalid).\n- <b>Updates</b>: clearer progress.\n\n```\n- hidden code\n```'
        self.assertEqual(summarize_notes(body),'• Unit stats: preserve timelines.\n\n• Updates: clearer progress.')
        self.assertLessEqual(len(summarize_notes('\n'.join('- '+('word '*200) for i in range(20)))),1800)
        self.assertNotIn('hidden code',summarize_notes(body))
        self.assertIn('No patch notes',summarize_notes(None))

    def test_release_response_is_bounded_stable_and_matches_installed_tag(self):
        for data in ({'tag_name':'v'+VERSION,'draft':True},{'tag_name':'v'+VERSION,'prerelease':True},
                     {'tag_name':'v99.0.0'},[],{'tag_name':'not-a-version'}):
            with self.subTest(data=data),patch('release_notes.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaises(ValueError):fetch_release('v'+VERSION)
        with patch('release_notes.MAX_RELEASE',8),patch('release_notes.urllib.request.urlopen',return_value=io.BytesIO(b' '*9)):
            with self.assertRaises(ValueError):fetch_release()

    def test_offline_cache_is_version_specific_and_handles_invalid_data(self):
        with tempfile.TemporaryDirectory() as d:
            save_notes(d,'Installed-version notes');self.assertEqual(cached_notes(d),'Installed-version notes')
            path=Path(d)/'state/release-notes.json'
            for data in ('[]','bad json',json.dumps(dict(version='0.0.1',summary='wrong version')),json.dumps(dict(version=VERSION,summary='x'*1801))):
                path.write_text(data);self.assertIsNone(cached_notes(d))

    def test_startup_loads_installed_notes_and_offers_newer_version_without_downloading(self):
        with tempfile.TemporaryDirectory() as d:
            menu=MagicMock();actions=queue.Queue();release=('v99.0.0',{'verified':'metadata'})
            worker=StartupReleaseCheck(d,menu,actions)
            with patch('updater.fetch_release',side_effect=[{'body':'- New charts'}, {'tag_name':'v99.0.0'}]),patch('updater.latest_release',return_value=release),patch('updater.stage_update') as download:
                worker.run()
            menu.set_release_notes.assert_called_once_with('• New charts')
            self.assertEqual(cached_notes(d),'• New charts')
            self.assertEqual(actions.get_nowait(),('startup_update_available',release));download.assert_not_called()

    def test_offline_boot_uses_cache_and_shows_no_error_or_update_dialog(self):
        with tempfile.TemporaryDirectory() as d:
            save_notes(d,'Cached notes');menu=MagicMock();actions=queue.Queue()
            with patch('updater.fetch_release',side_effect=OSError('offline')),patch('updater.message') as message:
                StartupReleaseCheck(d,menu,actions).run()
            menu.set_release_notes.assert_called_once_with('Cached notes');self.assertTrue(actions.empty());message.assert_not_called()

    def test_current_version_and_stopped_checks_do_not_offer_updates(self):
        with tempfile.TemporaryDirectory() as d:
            menu=MagicMock();actions=queue.Queue();worker=StartupReleaseCheck(d,menu,actions)
            with patch('updater.fetch_release',return_value={'tag_name':'v'+VERSION,'body':'- Notes'}):worker.run()
            self.assertTrue(actions.empty())
            menu.reset_mock();worker.stop()
            with patch('updater.fetch_release',return_value={'tag_name':'v'+VERSION,'body':'- Notes'}):worker.run()
            menu.set_release_notes.assert_not_called();self.assertTrue(actions.empty())

    def test_yes_authorization_skips_second_download_question_but_keeps_install_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d)/'app';stage.mkdir()
            checker=UpdateChecker(queue.Queue());asset={'manifest':{},'size':10}
            def checked(*args,**kwargs):(stage.parent/'install-check.json').write_text(json.dumps(dict(version='99.0.0')))
            with patch('updater.sys.frozen',True,create=True),patch('updater.ProgressWindow'),patch('updater.read_manifest',return_value={}),patch('updater.validate_manifest',return_value=[]),patch('updater.plan_update',return_value=([],[])),patch('updater.range_groups',return_value=[]),patch('updater.stage_update',return_value=stage) as download,patch('updater.subprocess.run',side_effect=checked),patch('updater.message',return_value=False) as question:
                checker.run(release=('v99.0.0',asset),download_approved=True)
                download.assert_called_once();question.assert_called_once()
                self.assertIn('Save, install and restart',question.call_args.args[0])
                self.assertIsNone(checker.pending)


if __name__=='__main__':unittest.main()
