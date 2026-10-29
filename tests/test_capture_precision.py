import copy
import json
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import patch
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'src'))
from capture_precision import release_record,POLICY
from logfile import LogWriter,read_log
from log_migration import migrate_log
from recorder import Recorder
from worker import Worker
from report_library import ReportLibrary
from report_assets import required_images,index_at
from explorer import open_folder

class PrecisionTests(unittest.TestCase):
    def test_explorer_is_revealed_after_preparing_out_of_foreground(self):
        with patch('explorer.folder_windows',side_effect=[{}, {123:'shareables'}]),patch('explorer.os.startfile') as launch,patch('explorer.time.sleep'),patch('explorer.reveal') as show:
            path=P/'build/shareables';open_folder(path)
            launch.assert_called_once_with(str(path.resolve()),show_cmd=7);show.assert_called_once_with(123)
    def frame(self):
        return dict(kind='sample',schema=1,sim_s=1.123456789,model_s=1.123456,performance={'cpu_window_percent':10},
            units=[dict(id='u',hp_cached=12345,health_percent=.123456789,xyz=[1.123456,-2.123456,3.123456],
                regen_base_raw=.0000016666667,healing_ceiling_fraction_raw=1.123456789,healing_budget_remaining_hp=123,
                statline=dict(speed=42.7500038,hp=12345,armour=27.0000019),
                active_effects=[dict(intensity=.003333333333)],future_field=.123456789,unknown=None,alive=True)],
            armies=[dict(current=1.123456,recharge_per_second=.123456789)],effect_damage_scale=.123456789,
            battle_clock=dict(elapsed_s=1.123456,remaining_s=3598.876544,limit_s=3600.0))

    def test_explicit_rounding_preserves_exceptions_unknowns_and_original_input(self):
        frame=self.frame();frame['deployment_baseline']=copy.deepcopy(frame);before=copy.deepcopy(frame)
        out=release_record(frame);unit=out['units'][0]
        self.assertEqual(frame,before);self.assertEqual(out['sim_s'],1.1235);self.assertEqual(out['model_s'],1.123)
        self.assertEqual(unit['xyz'],[1.1235,-2.1235,3.1235]);self.assertEqual(unit['statline']['speed'],42.75)
        for key in ('regen_base_raw','active_effects','future_field','unknown','alive','hp_cached'):self.assertEqual(unit[key],frame['units'][0][key])
        self.assertEqual(out['effect_damage_scale'],frame['effect_damage_scale']);self.assertNotIn('performance',out)
        self.assertNotIn('performance',out['deployment_baseline'])
        legacy=dict(frame['units'][0]);legacy.pop('healing_budget_remaining_hp')
        self.assertEqual(release_record(dict(kind='sample',units=[legacy]))['units'][0]['healing_ceiling_fraction_raw'],legacy['healing_ceiling_fraction_raw'])

    def test_release_recorder_omits_diagnostics_and_debug_keeps_them(self):
        for debug in (False,True):
            with self.subTest(debug=debug),tempfile.TemporaryDirectory() as d:
                path=Path(d)/'log.wh3log';recorder=Recorder(path,bytes(32),{},diagnostics=debug)
                recorder.submit(self.frame());recorder.finish(dict(wall_seconds=10,process_cpu_seconds=1,reason='done'));recorder.join(5)
                self.assertIsNone(recorder.error);records=list(read_log(path,bytes(32)))
                self.assertEqual('performance' in records[1],debug);self.assertEqual('io_seconds' in records[-1]['summary'],debug)
                self.assertEqual('process_cpu_seconds' in records[-1]['summary'],debug)
                self.assertEqual(records[0]['metadata']['diagnostics'],debug)

    def test_release_worker_does_not_create_resource_monitor(self):
        with patch('worker.ResourceMonitor',side_effect=AssertionError('Debug only')):
            worker=Worker(P,queue.Queue(1),preview=False)
            self.assertIsNone(worker.monitor);self.assertEqual(worker.stats,{})

    def test_existing_recording_migration_verifies_expected_rounded_records(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log.wh3log';writer=LogWriter(path,bytes(32),{})
            writer.write(self.frame());writer.close({'process_cpu_seconds':5,'reason':'done'})
            before=list(read_log(path,bytes(32)));result=migrate_log(path,bytes(32),precision=True)
            self.assertTrue(result['verified']);self.assertEqual(list(read_log(path,bytes(32))),[release_record(r) for r in before])
            self.assertIsNone(migrate_log(path,bytes(32),precision=True))

    def test_shareable_relocation_preserves_conflicting_exports(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'shareables').mkdir();(root/'captures/shareables').mkdir(parents=True)
            (root/'shareables/Battle.html').write_text('old');(root/'captures/shareables/Battle.html').write_text('new')
            moved=ReportLibrary(root).move_shareables();self.assertEqual(len(moved),1)
            self.assertEqual((root/'captures/shareables/Battle.html').read_text(),'new')
            self.assertEqual((root/'captures/shareables/Battle (export 1).html').read_text(),'old')
            self.assertFalse((root/'shareables').exists())

    def test_asset_pruning_keeps_every_catalog_card_and_dynamic_card_folder(self):
        index=index_at(P/'assets/game-assets.json');keep=required_images(index)
        for key in ('stats','units','units_by_key'):self.assertTrue(set(index[key].values())<=keep)
        self.assertTrue(all(name in keep for name in index['provenance'] if name.startswith('ui/portraits/units/')))
        self.assertFalse(any('porthole' in name for name in keep),'Only actual unit-card folders may be bundled.')
        self.assertTrue(any(name not in keep for name in index['provenance']))

if __name__=='__main__':unittest.main()
