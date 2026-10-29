import copy
import json
from pathlib import Path
import queue
import re
import struct
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from demo import frames
from fixtures import PROFILE
from logfile import LogWriter,load_key,read_log
from memory import ReadError
from recorder import Recorder
from report import convert
from report_data import read_summary
from report_library import ReportLibrary
from worker import Worker


class RecordingLifecycleTests(unittest.TestCase):
    def frame(self,phase=5,t=10):
        frame=next(frames(1,1));frame.update(battle_phase=phase,sim_s=t)
        return frame

    def run_worker(self,root,steps,choice=True,timeout=30):
        worker=Worker(root,queue.Queue(1),preview=False);worker.interval=.001;worker.data_timeout=timeout
        sequence=iter(steps);requests=[]
        class Memory:
            def __init__(self,*args):self.calls=self.bytes_read=0;self.pid=123;self.running=True
            def alive(self):return self.running
            def close(self):pass
        class Reader:
            def __init__(self,memory,*args):self.memory=memory
            def sample(self):
                if worker.late_start_request:
                    requests.append(worker.late_start_request)
                    worker.answer_late_start(worker.late_start_request,choice)
                step=next(sequence,'stop')
                if step=='stop':worker.stop_event.set();self.frame=None
                elif step=='exit':self.memory.running=False;self.frame=self_test.frame(t=14)
                elif isinstance(step,Exception):raise step
                else:self.frame=copy.deepcopy(step)
                return SimpleNamespace(token=(1,),controller=1)
            def normalized(self,sample):return self.frame
        self_test=self
        with patch('worker.WindowsAPI') as api,patch('worker.ProcessMemory',Memory),patch('worker.LoggerReader',Reader),patch('worker.load_profiles',return_value=[PROFILE]),patch('worker.select_profile',return_value=PROFILE):
            api.return_value.game_pids.side_effect=lambda:[123] if not worker.memory or worker.memory.alive() else []
            api.return_value.game_module.return_value={}
            worker.start();worker.join(15)
        self.assertFalse(worker.is_alive(),worker.status)
        return worker,requests

    def test_late_start_yes_records_warning_and_no_discards_whole_battle(self):
        for accepted in (True,False):
            with self.subTest(accepted=accepted),tempfile.TemporaryDirectory() as d:
                worker,requests=self.run_worker(d,[self.frame(),self.frame(t=11),self.frame(t=12)],choice=accepted)
                self.assertEqual(len(requests),1)
                self.assertEqual(len(worker.recorders),int(accepted))
                if accepted:
                    recorder=worker.recorders[0];self.assertIsNone(recorder.error)
                    records=list(read_log(recorder.path,recorder.key))
                    self.assertTrue(records[0]['metadata']['started_mid_battle'])
                    self.assertEqual([r['sim_s'] for r in records if r['kind']=='sample'],[11,12])
                    self.assertTrue(read_summary(recorder.path,recorder.key)['recording_warnings'])
                    self.assertFalse(recorder.path.with_suffix('.html').exists())
                else:self.assertFalse(list(Path(d).rglob('*.wh3log')))

    def test_normal_deployment_and_next_battle_after_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            worker,requests=self.run_worker(d,[self.frame(),self.frame(),None,self.frame(4),self.frame(t=11)],choice=False)
            self.assertEqual(len(requests),1);self.assertEqual(len(worker.recorders),1)
            self.assertFalse(worker.recorders[0].metadata['started_mid_battle'])

    def test_read_failure_and_empty_unit_stream_finish_and_do_not_restart_same_battle(self):
        empty=self.frame(t=12);empty['units']=[]
        for missing in (ReadError('game stopped responding'),empty):
            with self.subTest(missing=type(missing).__name__),tempfile.TemporaryDirectory() as d:
                worker,_=self.run_worker(d,[self.frame(4),self.frame(),missing,self.frame(t=13)],timeout=0)
                self.assertEqual(len(worker.recorders),1)
                recorder=worker.recorders[0];self.assertIsNone(recorder.error)
                records=list(read_log(recorder.path,recorder.key))
                self.assertEqual(records[-1]['summary']['reason'],'unit_data_timeout')
                self.assertIsNone(recorder.report_path);self.assertFalse(recorder.path.with_suffix('.html').exists())
                self.assertEqual(len([r for r in records if r['kind']=='sample']),1)

    def test_paused_readable_frames_do_not_trigger_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            worker,_=self.run_worker(d,[self.frame(4),self.frame(),self.frame(),self.frame()],timeout=0)
            records=list(read_log(worker.recorders[0].path,worker.recorders[0].key))
            self.assertEqual(records[-1]['summary']['reason'],'battle_roster_unavailable')
            self.assertEqual(len([r for r in records if r['kind']=='sample']),1)

    def test_game_process_exit_seals_recording_without_html(self):
        with tempfile.TemporaryDirectory() as d:
            worker,_=self.run_worker(d,[self.frame(4),self.frame(),'exit'])
            recorder=worker.recorders[0]
            self.assertIsNone(recorder.error);self.assertTrue(recorder.path.is_file())
            self.assertFalse(recorder.path.with_suffix('.html').exists())
            self.assertEqual(list(read_log(recorder.path,recorder.key))[-1]['summary']['reason'],'game_process_exit')

    def test_timeout_uses_elapsed_wall_time_from_last_unit_sample(self):
        worker=Worker(P,queue.Queue(1));worker.recorder=MagicMock();worker.battle=MagicMock()
        worker.wall_start=worker.cpu_start=0;worker.last_unit_data=100;worker.window_identity=(1,2,3)
        worker.unit_data_missing(129,'gap');self.assertIsNotNone(worker.recorder)
        recorder=worker.recorder;worker.unit_data_missing(130,'gap')
        self.assertIsNone(worker.recorder);self.assertEqual(worker.suppressed,(1,2,3))
        self.assertEqual(recorder.finish.call_args.args[0]['reason'],'unit_data_timeout')

    def test_paused_first_sample_is_checkpointed_for_crash_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'captures/paused.wh3log';key=bytes(32)
            recorder=Recorder(path,key,{})
            try:
                recorder.submit(self.frame())
                deadline=time.monotonic()+4
                while time.monotonic()<deadline:
                    if path.is_file() and path.stat().st_size>=24 and any(r['kind']=='sample' for r in read_log(path,key,recover_tail=True)):break
                    time.sleep(.05)
                else:self.fail('The paused first sample was not checkpointed.')
            finally:
                recorder.finish({});recorder.join(10)
            self.assertIsNone(recorder.error)

    def test_restart_saves_before_return_and_relaunch_preserves_options(self):
        from release_app import BackgroundApp,restart_command
        calls=[];worker=MagicMock();worker.stop_event=threading.Event();worker.join.side_effect=lambda:calls.append('saved')
        tray=MagicMock();tray.actions=queue.Queue();tray.actions.put('restart')
        tray.stop.side_effect=lambda:calls.append('tray stopped')
        with tempfile.TemporaryDirectory() as d,patch('release_app.MainMenu') as menu:
            self.assertTrue(BackgroundApp(d,worker=worker,tray=tray).run())
            menu.return_value.close.assert_called_once()
        self.assertTrue(worker.stop_event.is_set());self.assertEqual(calls,['saved','tray stopped'])
        with patch('release_app.FROZEN',True):
            self.assertEqual(restart_command(Path('data'),.5,123)[1:],['--data-dir','data','--rate','0.5','--pid','123'])


class RecoveryTests(unittest.TestCase):
    def make_log(self,root,name='interrupted',complete=False):
        key=load_key(Path(root)/'captures/logger.key',True)
        path=Path(root)/'captures'/f'{name}.wh3log';writer=LogWriter(path,key,{})
        for frame in frames(1,1):writer.write(frame)
        if complete:writer.close({})
        else:writer.flush(durable=True);writer.stream.close()
        return path,key

    def test_missing_footer_and_torn_tail_recover_without_modifying_log(self):
        for tail in (b'',b'\x20\x00',struct.pack('<I',50)+b'incomplete'):
            with self.subTest(tail=tail),tempfile.TemporaryDirectory() as d:
                path,key=self.make_log(d);path.write_bytes(path.read_bytes()+tail);original=path.read_bytes()
                with self.assertRaises(ValueError):list(read_log(path,key))
                library=ReportLibrary(d);library.build_missing()
                html=Path(d)/'captures/shareables'/(path.stem+'.html');self.assertTrue(html.is_file(),library.status)
                data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html.read_text(encoding='utf-8'),re.S)[1])
                self.assertTrue(data['capture']['incomplete']);self.assertTrue(data['recording_warnings'])
                self.assertIsNone(data['battle_result']);self.assertEqual(path.read_bytes(),original)
                self.assertFalse(html.with_suffix('.html.tmp').exists())

    def test_authentication_damage_and_wrong_keys_are_never_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            path,key=self.make_log(d);raw=bytearray(path.read_bytes());raw[-1]^=1;path.write_bytes(raw)
            with self.assertRaises(Exception):convert(path,key,recover_tail=True)
            self.assertFalse(path.with_suffix('.html').exists())
            with self.assertRaises(Exception):convert(path,bytes(32),recover_tail=True)

    def test_only_missing_closed_reports_built_and_key_is_not_created_by_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            active,_=self.make_log(d,'active');complete,_=self.make_log(d,'complete',True)
            existing,_=self.make_log(d,'existing');existing.with_suffix('.html').write_text('keep',encoding='utf-8')
            library=ReportLibrary(d);library.build_missing(active=[active])
            self.assertFalse(active.with_suffix('.html').exists());self.assertTrue((Path(d)/'captures/shareables'/(complete.stem+'.html')).exists())
            self.assertEqual(existing.with_suffix('.html').read_text(encoding='utf-8'),'keep')
            self.assertEqual(len(library.entries()),3)
            (Path(d)/'captures/logger.key').unlink();library.build_missing()
            self.assertFalse((Path(d)/'captures/logger.key').exists())

    def test_empty_interrupted_capture_is_not_presented_as_battle(self):
        with tempfile.TemporaryDirectory() as d:
            key=load_key(Path(d)/'captures/logger.key',True);path=Path(d)/'captures/empty.wh3log'
            writer=LogWriter(path,key,{});writer.stream.close()
            library=ReportLibrary(d);library.build_missing()
            self.assertFalse(path.with_suffix('.html').exists());self.assertIn('could not be recovered',library.status)


if __name__=='__main__':unittest.main()
