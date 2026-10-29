import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from aggregate import Battle, Series
from demo import frames
from logfile import LogWriter, load_key, read_log
from report import convert, write_report
from recorder import Recorder
from worker import Worker
from fixtures import BattleFixture, PROFILE
from memory import WindowsAPI, ProcessMemory, load_profiles, select_profile, UnsupportedBuild


class AggregationTests(unittest.TestCase):
    def test_pause_and_speed_use_simulation_time(self):
        data=list(frames(1,2));b=Battle(max_gap=80)
        for f in data:f['units'][0]['melee']=True
        b.observe(data[0]);b.observe(data[0]);data[1]['sim_s']=8;b.observe(data[1])
        self.assertEqual(b.summary()['units'][0]['state_seconds']['melee'],8)
        self.assertEqual(b.paused_samples,1)

    def test_missing_units_break_duration_and_path_continuity(self):
        fs=list(frames(1,3));b=Battle()
        for f in fs:f['units'][0]['melee']=True
        b.observe(fs[0]);empty=copy.deepcopy(fs[1]);empty['units']=[];b.observe(empty);b.observe(fs[2])
        u=b.summary()['units'][0]
        self.assertNotIn('distance_sampled',u)
        self.assertEqual(u['state_seconds']['melee'],0)
        self.assertEqual(u['missing_samples'],1)

    def test_hp_and_models_are_observed_changes_not_true_damage(self):
        fs=list(frames(1,2));b=Battle()
        fs[0]['units'][0].update(hp_cached=1000,models=10)
        fs[1]['units'][0].update(hp_cached=800,models=10)
        fs[2]['units'][0].update(hp_cached=900,models=11)
        for f in fs:b.observe(f)
        u=b.summary()['units'][0]
        self.assertEqual((u['observed_hp_drops'],u['observed_hp_rises']),(200,100))
        self.assertNotIn('observed_model_losses',u);self.assertNotIn('observed_model_rises',u)
        self.assertIn('healing_applied',b.summary()['unsupported'])
        self.assertIn('exact_damage_taken',b.summary()['unsupported'])
        self.assertIsNone(u['damage_taken_estimate'])

    def test_damage_on_firing_transition_is_ambiguous(self):
        fs=list(frames(1,3));b=Battle()
        for i,f in enumerate(fs):f['units'][0].update(damage=i*100,firing=i>=2)
        for f in fs:b.observe(f)
        u=b.summary()['units'][0]
        self.assertEqual((u['damage_firing_estimate'],u['damage_other_state_estimate'],u['damage_ambiguous']),(100,100,100))

    def test_missing_clock_never_substitutes_wall_time(self):
        f=next(frames(1,1));b=Battle();f['sim_s']=None;b.observe(f)
        self.assertEqual(b.missing_clock,1);self.assertEqual(b.samples,0)

    def test_clock_rollback_rejected(self):
        fs=list(frames(1,1));b=Battle();b.observe(fs[1])
        with self.assertRaises(ValueError):b.observe(fs[0])

    def test_disappearing_unit_not_marked_dead(self):
        fs=list(frames(1,1));b=Battle();b.observe(fs[0]);fs[1]['units']=[];b.observe(fs[1])
        self.assertEqual(b.summary()['units'][0]['final_status'],'Last observed / missing')

    def test_counter_reset_marks_dps_unknown(self):
        fs=list(frames(1,1));b=Battle();fs[0]['units'][0]['damage']=100
        for f in fs:b.observe(f)
        self.assertIsNone(b.summary()['units'][0]['dps_since_attach'])

    def test_history_is_bounded_and_retains_endpoints(self):
        s=Series(limit=40)
        for i in range(20000):s.add(dict(t=i))
        self.assertLessEqual(len(s.points),40);self.assertEqual(s.points[0]['t'],0)
        self.assertEqual(s.points[-1]['t'],19999)

    def test_sampled_states_can_overlap(self):
        fs=list(frames(1,1));b=Battle()
        for f in fs:f['units'][0].update(firing=True,melee=True,flying=True)
        for f in fs:b.observe(f)
        self.assertEqual([b.summary()['units'][0]['state_seconds'][k] for k in ['firing','melee','flying']],[1,1,1])

    def test_unknown_or_missing_data_interrupts_engagement(self):
        fs=list(frames(1,4));b=Battle()
        for f in fs:f['units'][0].update(melee=True,firing=False)
        b.observe(fs[0]);b.observe(fs[1]);b.break_continuity();b.observe(fs[4])
        self.assertNotIn('first_engagement',b.summary()['units'][0])
        self.assertEqual(b.summary()['units'][0]['state_seconds']['melee'],1)

    def test_queue_gap_breaks_durations_paths_and_all_timelines(self):
        fs=list(frames(1,4));b=Battle()
        for i,f in enumerate(fs):f['units'][0].update(melee=True,damage=i*100)
        b.observe(fs[0]);b.observe(fs[1]);fs[4]['gap_before']={'dropped_records':2};b.observe(fs[4])
        s=b.summary();u=s['units'][0]
        self.assertEqual(u['state_seconds']['melee'],1)
        self.assertEqual(s['gaps'],1)
        self.assertEqual(u['damage_ambiguous'],300)
        for history in [u['history'],s['armies'][0]['history']]:
            self.assertEqual(history[-1]['t'],4)
            self.assertNotEqual(history[-1]['segment'],history[-2]['segment'])

    def test_missing_position_break_survives_history_downsampling(self):
        b=Battle()
        for i,f in enumerate(frames(1,600)):
            if i==2:f['units'][0]['xyz']=None
            b.observe(f)
        points=b.summary()['units'][0]['history']
        self.assertNotEqual(points[0]['position_segment'],points[-1]['position_segment'])

    def test_pause_does_not_create_winds_chart_gap(self):
        fs=list(frames(1,1));b=Battle()
        b.observe(fs[0]);b.observe(fs[0]);b.observe(fs[1])
        points=b.summary()['armies'][0]['history']
        self.assertEqual(points[0]['segment'],points[-1]['segment'])

    def test_paused_field_updates_replace_same_time_history(self):
        fs=list(frames(1,1));b=Battle()
        b.observe(fs[0]);paused=copy.deepcopy(fs[0])
        paused['units'][0].update(hp_cached=7000,melee=True)
        paused['armies'][0]['current']=25
        b.observe(paused)
        s=b.summary()
        self.assertEqual(len(s['units'][0]['history']),1)
        self.assertEqual(s['units'][0]['history'][0]['hp_cached'],7000)
        self.assertEqual(s['armies'][0]['history'][0]['current'],25)
        self.assertEqual(s['units'][0]['state_seconds']['melee'],0)

    def test_shattering_or_withdrawing_is_not_a_rally(self):
        for field in ('shattered','withdrawing'):
            fs=list(frames(1,1));b=Battle()
            fs[0]['units'][0]['routing']=True;fs[1]['units'][0][field]=True
            for f in fs:b.observe(f)
            self.assertEqual(b.summary()['units'][0]['rallies_observed'],0)

    def test_last_observed_values_survive_death_without_faking_fresh_cache(self):
        fs=list(frames(1,1));b=Battle()
        fs[0]['units'][0].update(melee=True,firing=False)
        fs[1]['units'][0].update(alive=False,hp_cached=0,hp_max_cached=None,models_initial=None,melee=None,firing=None)
        for f in fs:b.observe(f)
        u=b.summary()['units'][0]
        self.assertIsNone(u['last']['hp_max_cached'])
        self.assertEqual(u['last_observed']['hp_max_cached'],dict(value=8000,sim_s=0))
        self.assertNotIn('first_engagement',u)

    def test_duplicate_labels_preserve_raw_names_and_separate_sides(self):
        f=next(frames(3,1));b=Battle()
        for u in f['units']:u['name']='Crypt Ghouls'
        b.observe(f);us=b.summary()['units']
        self.assertEqual([u['display_name'] for u in us],['Crypt Ghouls #1','Crypt Ghouls','Crypt Ghouls #2'])
        self.assertTrue(all(u['name']=='Crypt Ghouls' for u in us))


class EncryptionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=PROJECT/'build');self.root=Path(self.temp.name)
        self.key=load_key(self.root/'logger.key',True);self.path=self.root/'battle.wh3log'
    def tearDown(self):self.temp.cleanup()
    def write(self):
        w=LogWriter(self.path,self.key,dict(source='test'));w.write(next(frames(2,1)));w.close(dict(done=True))
    def test_roundtrip_and_key_separate_from_file(self):
        self.write();raw=self.path.read_bytes()
        self.assertNotIn(b'Skeleton',raw);self.assertNotIn(self.key,raw)
        self.assertEqual([r['kind'] for r in read_log(self.path,self.key)],['header','sample','footer'])
    def test_wrong_key_rejected(self):
        self.write()
        with self.assertRaises(Exception):list(read_log(self.path,b'x'*32))
    def test_tampering_rejected(self):
        self.write();raw=bytearray(self.path.read_bytes());raw[35]^=1;self.path.write_bytes(raw)
        with self.assertRaises(Exception):list(read_log(self.path,self.key))
    def test_truncated_footer_rejected(self):
        self.write();self.path.write_bytes(self.path.read_bytes()[:-20])
        with self.assertRaises(ValueError):list(read_log(self.path,self.key))
    def test_missing_footer_rejected(self):
        w=LogWriter(self.path,self.key,{});w.write(next(frames(1,1)));w.stream.close()
        with self.assertRaisesRegex(ValueError,'incomplete'):list(read_log(self.path,self.key))
    def test_existing_capture_not_overwritten(self):
        self.write()
        with self.assertRaises(FileExistsError):LogWriter(self.path,self.key,{})
    def test_encrypted_log_rebuilds_report(self):
        self.write();out=convert(self.path,self.key)
        self.assertIn('Battle Report',out.read_text(encoding='utf-8'))
        self.assertIn('Hide graph explanations',out.read_text(encoding='utf-8'))

    def test_report_corrects_legacy_size_without_changing_capture(self):
        import re
        w=LogWriter(self.path,self.key,{})
        w.write(next(frames(1,1)));w.close(dict(encrypted_bytes=1,wall_seconds=10,process_cpu_seconds=.5))
        original=self.path.read_bytes();out=convert(self.path,self.key)
        data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',out.read_text(encoding='utf-8'),re.S).group(1))
        self.assertEqual(data['capture']['encrypted_bytes'],len(original))
        self.assertEqual(data['capture']['legacy_reported_encrypted_bytes'],1)
        self.assertNotIn('process_cpu_one_core_average_percent',data['capture']);self.assertNotIn('process_cpu_seconds',data['capture']);self.assertNotIn('performance',data)
        self.assertEqual(self.path.read_bytes(),original)

    def test_legacy_native_winds_reciprocal_migrates_only_in_report(self):
        import re
        frame=next(frames(1,1))
        for a in frame['armies']:
            a.pop('recharge_per_second');a.pop('recharge_seconds_per_point');a['recharge']=10.
        w=LogWriter(self.path,self.key,dict(source='external-native'));w.write(frame);w.close({})
        original=self.path.read_bytes();out=convert(self.path,self.key)
        data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',out.read_text(encoding='utf-8'),re.S).group(1))
        army=data['armies'][0]['last']
        self.assertEqual(army['recharge_per_second'],.1)
        self.assertEqual(army['recharge_seconds_per_point'],10.)
        self.assertEqual(army['recharge'],10.)
        self.assertIn('legacy',army['recharge_rate_source'])
        self.assertEqual(self.path.read_bytes(),original)
    def test_report_escapes_script_and_unit_names(self):
        f=next(frames(1,1));f['units'][0]['name']='</script><img onerror="alert(1)">'
        b=Battle();b.observe(f);write_report(self.root/'report.html',b.summary())
        text=(self.root/'report.html').read_text(encoding='utf-8')
        self.assertNotIn('</script><img',text);self.assertIn('\\u003c/script',text)
    def test_async_recorder_finishes_all_accepted_samples(self):
        r=Recorder(self.path,self.key,{},max_bytes=10000000)
        count=sum(r.submit(f) for f in frames(2,4))
        r.finish(dict(reason='test'));r.join(10)
        self.assertIsNone(r.error);self.assertFalse(r.is_alive())
        self.assertEqual(sum(x['kind']=='sample' for x in read_log(self.path,self.key)),count)
        self.assertIsNone(r.report_path);self.assertFalse(self.path.with_suffix('.html').exists())
    def test_capture_size_limit_is_recorded(self):
        r=Recorder(self.path,self.key,{},max_bytes=1)
        for f in frames(1,2):r.submit(f)
        r.finish({});r.join(10)
        footer=list(read_log(self.path,self.key))[-1]['summary']
        self.assertTrue(footer['size_limit_reached']);self.assertGreater(footer['dropped_records'],0)

    def test_overloaded_queue_marks_next_accepted_record(self):
        import queue
        with patch.object(Recorder,'start'):
            r=Recorder(self.path,self.key,{})
        r.queue=queue.Queue(maxsize=1)
        fs=list(frames(1,3))
        self.assertTrue(r.submit(fs[0]));self.assertFalse(r.submit(fs[1]));self.assertFalse(r.submit(fs[2]))
        r.queue.get_nowait();self.assertTrue(r.submit(fs[3]))
        self.assertEqual(r.queue.get_nowait()['gap_before'],{'dropped_records':2})
        self.assertNotIn('gap_before',fs[3])


class NativeTests(unittest.TestCase):
    def test_winds_rate_and_interval_are_not_swapped(self):
        f=BattleFixture();f.memory.write(f.enemy_army+0xb4,struct.pack('<f',.1))
        sample=f.sample();army=sample.armies[-1]
        self.assertAlmostEqual(army.recharge_per_second,.1,places=6)
        self.assertAlmostEqual(army.recharge_seconds_per_point,10,places=5)
        normalized=f.reader.normalized(sample)['armies'][-1]
        self.assertAlmostEqual(normalized['recharge_per_second'],.1,places=6)
        self.assertAlmostEqual(normalized['recharge'],10,places=5)  # Legacy reciprocal preserved.

    def test_zero_recharge_is_a_known_zero_rate_not_an_infinite_interval(self):
        f=BattleFixture();f.memory.write(f.my_army+0xb4,struct.pack('<f',0))
        army=f.sample().armies[0]
        self.assertEqual(army.recharge_per_second,0)
        self.assertIsNone(army.recharge_seconds_per_point)

    def test_native_damage_sources_are_independent_of_unit_activity(self):
        f=BattleFixture();unit=f.own[0];m=f.memory
        counts=[0]*18
        for i,v in enumerate([100,200,300,20,10,5]):counts[i*3]=v
        counts[1]=11;counts[2]=22
        m.write(unit['result']+0x20,struct.pack('<18I',*counts));m.u(unit['result']+0xc4,635)
        m.write(unit['address']+0x6ff,b'\x00')
        u=f.sample().units[0].values
        self.assertEqual(u['damage_by_source']['missile']['enemy'],300)
        self.assertEqual(u['damage_by_source']['ability'],dict(enemy=100,self=11,ally=22))
        self.assertTrue(u['damage_sources_consistent'])
        self.assertFalse(u['firing'])

    def test_torn_source_table_is_unknown_while_native_total_remains(self):
        f=BattleFixture();unit=f.own[0];f.memory.u(unit['result']+0x20,1)
        u=f.sample().units[0].values
        self.assertEqual(u['damage'],125)
        self.assertFalse(u['damage_sources_consistent']);self.assertIsNone(u['damage_by_source'])

    def test_dead_unit_retains_native_source_counters(self):
        f=BattleFixture();unit=f.own[0]
        f.memory.write(unit['address']+0x6fb,b'\x00');f.memory.write(unit['address']+0x6fe,b'\x00')
        u=f.sample().units[0].values
        self.assertEqual(u['damage_by_source']['melee']['enemy'],125)
        self.assertIsNone(u['hp_cached'])
        self.assertIsNone(u['hp_max_cached'])

    def test_adjacent_fields_and_native_damage(self):
        f=BattleFixture();s=f.sample();u=s.units[0]
        self.assertEqual(u.values['damage'],125)
        self.assertEqual(u.values['kills'],4)
        self.assertEqual(u.values['hp_cached'],7500)
        self.assertEqual(u.values['models'],115)
        self.assertEqual(u.values['healing_ceiling_fraction_raw'],.75)
        frame=f.reader.normalized(s)
        self.assertEqual(frame['sim_s'],10.)
        self.assertFalse(frame['units'][0]['out_of_opponents_vision'])
        self.assertTrue(frame['units'][0]['controlled'])
        self.assertFalse(frame['units'][-1]['controlled'])

    def test_visibility_lists_read_once_per_alliance_and_hidden_data_retained(self):
        f=BattleFixture(40,40);s=f.sample();before=f.memory.calls
        frame=f.reader.normalized(s)
        self.assertEqual(len(frame['units']),80)
        # Two adapter reads/unit, plus two pointer hops and two stable vector reads/alliance, plus roots.
        self.assertLess(f.memory.calls-before,200)
        self.assertTrue(all(u['out_of_opponents_vision'] is False for u in frame['units']))
    def test_unknown_cache_does_not_create_zero_durations(self):
        f=BattleFixture();f.memory.write(f.own[0]['address']+0x6fb,b'\x00')
        u=f.sample().units[0]
        self.assertIsNone(u.values['firing']);self.assertIsNone(u.values['hp_cached'])
        self.assertEqual(u.values['damage'],125)
    def test_bad_float_unavailable(self):
        f=BattleFixture();f.memory.write(f.own[0]['address']+0x6c4,struct.pack('<f',float('nan')))
        self.assertIsNone(f.sample().units[0].values['primary_ammo_fraction'])
    def test_missing_name_preserves_native_counters(self):
        f=BattleFixture();unit=f.own[0]
        f.memory.write(unit['result']+0x68,struct.pack('<IIQ',3000,3000,0))
        sample=f.sample().units[0]
        self.assertEqual(sample.values['damage'],125)
        self.assertTrue(sample.name.startswith('Unit'))
    def test_unit_identity_mutation_rejected(self):
        f=BattleFixture();addr=f.own[0]['address']
        def mutate(address,size):
            if address==addr+0x598:f.memory.u(addr+0x614,999)
        f.memory.after_read=mutate
        s=f.sample();self.assertGreater(s.errors,0)
    def test_hidden_enemy_does_not_filter_cumulative_counters(self):
        f=BattleFixture();addr=f.enemy[0]['address'];f.memory.write(addr+0x6f5,b'\x01')
        s=f.sample();self.assertEqual(s.units[-1].values['damage'],90)
        self.assertTrue(f.reader.normalized(s)['units'][-1]['out_of_opponents_vision'])
    def test_both_profile_anchor_sets_match_their_executable(self):
        sys.path.insert(0,str(PROJECT/'tools'))
        from native_evidence import Image
        for profile in load_profiles(PROJECT/'profiles'):
            path=(PROJECT.parent/'decompile project/Warhammer3.exe') if 'saved' in profile['name'].lower() or profile['pe_timestamp']==1791416583 else Path('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
            im=Image(path)
            try:
                for a in profile['anchors']:
                    raw=bytes.fromhex(a['hex']);self.assertEqual(im.read(int(a['address'],0),len(raw)),raw,a['address'])
            finally:im.stream.close()
    def test_unknown_build_rejected_before_battle_offsets(self):
        with patch('memory.verify_build') as verify:
            with self.assertRaises(UnsupportedBuild):select_profile(None,{},[PROFILE],(1,1))
            verify.assert_not_called()


class RateTests(unittest.TestCase):
    def test_default_and_slower_options(self):
        import queue
        w=Worker(PROJECT,queue.Queue(1));self.assertEqual(w.interval,1.)
        for rate,interval in [(1,1),(.5,2),(.2,5)]:w.set_rate(rate);self.assertEqual(w.interval,interval)
        with self.assertRaises(ValueError):w.set_rate(2)

    def test_worker_finalizes_two_battles_and_shutdown(self):
        import queue
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir=PROJECT/'build') as temp:
            w=Worker(Path(temp),queue.Queue(1));w.interval=.001
            raw=list(frames(2,1))
            for frame in raw:frame['battle_phase']=5
            deployment=copy.deepcopy(raw[0]);deployment.update(battle_phase=4,sim_s=300)
            result=copy.deepcopy(raw[1]);result['battle_phase']=8
            sequence=iter([(1,deployment),(1,deployment),(1,raw[0]),(1,result),(None,None),(2,raw[0]),(2,raw[0]),(2,raw[1]),(None,None)])
            class Reader:
                def __init__(self,*args):self.frame=None
                def sample(self):
                    if w.late_start_request:w.answer_late_start(w.late_start_request,True)
                    try:token,self.frame=next(sequence)
                    except StopIteration:
                        w.stop_event.set();token,self.frame=None,None
                    return SimpleNamespace(token=(token,) if token else None,controller=1)
                def normalized(self,sample):return copy.deepcopy(self.frame)
            class Memory:
                def __init__(self,*args):self.calls=self.bytes_read=0;self.pid=1
                def alive(self):return True
                def close(self):pass
            with patch('worker.WindowsAPI') as api, patch('worker.ProcessMemory',Memory),patch('worker.LoggerReader',Reader),patch('worker.load_profiles',return_value=[PROFILE]),patch('worker.select_profile',return_value=PROFILE):
                api.return_value.game_pids.return_value=[1]
                api.return_value.game_module.return_value={}
                w.start();w.join(10)
            self.assertFalse(w.is_alive());self.assertEqual(len(w.recorders),2)
            for r in w.recorders:
                self.assertIsNone(r.error);self.assertTrue(r.done.is_set());self.assertIsNone(r.report_path)
                self.assertFalse(r.path.with_suffix('.html').exists())
                records=list(read_log(r.path,load_key(Path(temp)/'captures/logger.key')))
                samples=[a for a in records if a['kind']=='sample']
                self.assertEqual(len(samples),2)
                self.assertTrue(all(a['battle_phase'] in (5,8) for a in samples))
                self.assertEqual(samples[0]['sim_s'],0)
                self.assertEqual('deployment_baseline' in samples[0],r is w.recorders[0])
                self.assertNotIn('deployment_baseline',samples[1])

    def test_ui_default_is_private_and_rates_are_slower_options(self):
        import tkinter as tk
        from app import App
        from types import SimpleNamespace
        root=tk.Tk();root.withdraw()
        try:
            with patch('app.Worker') as worker:
                worker.return_value.is_alive.return_value=False
                app=App(root)
                self.assertEqual(app.rate.get(),1.)
                self.assertFalse(app.debug.get())
                self.assertFalse(app.topmost.get())
                with patch.object(root,'attributes') as attributes:
                    app.pin_button.invoke();attributes.assert_called_with('-topmost',True)
                    self.assertTrue(app.topmost.get())
                    app.pin_button.invoke();attributes.assert_called_with('-topmost',False)
                    self.assertFalse(app.topmost.get())
                app.rate.set(.2);app.set_rate();worker.return_value.set_rate.assert_called_with(.2)
                app.close();self.assertTrue(worker.return_value.stop_event.set.called)
        finally:
            root.destroy()
            del app
            import gc
            gc.collect()


if __name__=='__main__':unittest.main()
