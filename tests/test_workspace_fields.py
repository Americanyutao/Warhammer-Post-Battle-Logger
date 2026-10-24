import copy
import struct
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from fixtures import BattleFixture
from aggregate import Battle
from logfile import LogWriter
from report import convert


class WorkspaceFieldsTests(unittest.TestCase):
    def test_rank_points_and_departure_are_separate_from_combat_cache(self):
        f=BattleFixture(1,0);m=f.memory;u=f.own[0]
        setup=m.allocate(0x530);m.q(u['address']+0x158,setup)
        m.u(setup+0x518,12);m.u(setup+0x51c,1)
        m.write(u['adapter']+0x3c10,struct.pack('<II',3,14500))
        m.write(u['result']+0xe2,b'\x01')
        m.write(u['address']+0x6fb,b'\x00')
        v=f.reader.normalized(f.sample())['units'][0]
        self.assertEqual((v['character_level'],v['fatigue_points'],v['left_battlefield']),(12,14500,True))
        self.assertIsNone(v['fatigue_state']);self.assertEqual(v['fatigue_state_native'],3);self.assertIsNone(v['awaiting_order_after_rally_raw'])
        m.write(u['address']+0x6fe,b'\x00')
        self.assertIsNone(f.reader.normalized(f.sample())['units'][0]['fatigue_points'])

    def test_results_use_native_local_index_and_require_results_phase(self):
        f=BattleFixture(1,0);m=f.memory
        result=m.allocate(16);m.q(f.roster+0xa0,result)
        decoy=m.allocate(16);m.q(f.roster+0x98,decoy);m.u(decoy+4,2)
        local=m.allocate(16);m.q(f.context+0x3a8,local);m.u(f.context+0x3b4,0);m.u(local+4,0)
        m.u(result+4,0);m.u(f.roster+0xc8,7)
        self.assertIsNone(f.reader.normalized(f.sample())['battle_result'])
        m.u(f.roster+0xc8,8)
        self.assertEqual(f.reader.normalized(f.sample())['battle_result']['outcome'],'Victory')
        m.u(result+4,1)
        self.assertEqual(f.reader.normalized(f.sample())['battle_result']['outcome'],'Defeat')
        m.u(result+4,0xffffffff)
        self.assertEqual(f.reader.normalized(f.sample())['battle_result']['outcome'],'Draw')
        m.u(result+4,0xfffffffe)
        self.assertIsNone(f.reader.normalized(f.sample())['battle_result'])

    def test_reads_initialized_fatigue_rules_without_defaulting_missing_rules(self):
        f=BattleFixture(1,0);m=f.memory;u=f.own[0]
        self.assertIsNone(f.reader.normalized(f.sample())['fatigue_rules'])
        entity=m.allocate(0x800);array=m.allocate(8);m.q(array,entity)
        m.u(u['adapter']+0x184,1);m.q(u['adapter']+0x188,array)
        parent=m.allocate(0x450);m.q(entity+0x58,parent)
        for offset in (0x440,8,0x430,0x20,0x187c8):
            size=0x18800 if offset==0x20 else 0xb00 if offset==0x187c8 else 0x450
            child=m.allocate(size);m.q(parent+offset,child);parent=child
        thresholds=[0,2800,6600,12600,18000,27000,30000]
        for i,value in enumerate(thresholds):m.u(parent+0x830+i*0x68,value)
        rules=f.reader.normalized(f.sample())['fatigue_rules']
        self.assertEqual(rules['thresholds'],thresholds);self.assertEqual(rules['maximum'],30000)
        m.u(parent+0x830+4*0x68,1)
        self.assertIsNone(f.reader.normalized(f.sample())['fatigue_rules'])

    def test_rally_idle_requires_both_flags_and_excludes_route_and_gaps(self):
        f=BattleFixture(1,0);m=f.memory;u=f.own[0]
        m.write(u['address']+0x725,b'\x01');m.write(u['address']+0x700,b'\x01')
        b=Battle(max_gap=2)
        for t in range(4):
            frame=f.reader.normalized(f.sample());frame['sim_s']=t
            if t==2:frame['units'][0]['routing']=True
            b.observe(frame)
        row=b.summary()['units'][0]
        self.assertEqual(row['state_seconds']['idle_after_rally'],2)
        self.assertEqual(row['state_observed_seconds']['idle_after_rally'],3)
        b.break_continuity();frame['sim_s']=10;b.observe(frame)
        self.assertEqual(b.summary()['units'][0]['state_seconds']['idle_after_rally'],2)

    def test_summary_retains_result_departure_and_fatigue_peak(self):
        f=BattleFixture(1,0);b=Battle();frame=f.reader.normalized(f.sample())
        frame.update(battle_result=dict(outcome='Victory'),fatigue_rules=dict(maximum=30000,thresholds=[0,2800,6600,12600,18000,27000,30000]))
        frame['units'][0].update(left_battlefield=True,fatigue_points=18001)
        b.observe(frame);next_frame=copy.deepcopy(frame);next_frame.update(sim_s=11,units=[],battle_result=None,fatigue_rules=None);b.observe(next_frame)
        s=b.summary();self.assertEqual(s['battle_result']['outcome'],'Victory')
        self.assertEqual(s['units'][0]['final_status'],'Dead / retreated')
        self.assertEqual(s['units'][0]['fatigue_points_peak'],18001)
        self.assertEqual(s['fatigue_rules']['maximum'],30000)

    def test_legacy_inactive_zeros_are_not_measurements(self):
        f=BattleFixture(1,0);b=Battle(dict(source='external-native',collector_revision=6))
        frame=f.reader.normalized(f.sample());b.observe(frame)
        last=copy.deepcopy(frame);last['sim_s']=11
        last['units'][0].update(alive=False,left_battlefield=True,hp_cached=0,models=0,cache_active=False)
        b.observe(last);u=b.summary()['units'][0]
        self.assertEqual(u['final_status'],'Dead / retreated')
        self.assertIsNone(u['last']['hp_cached']);self.assertIsNone(u['last']['models'])
        self.assertEqual(u['last_observed']['hp_cached']['value'],7500)
        self.assertEqual(u['last_observed']['models']['value'],115)
        self.assertEqual(u['observed_hp_drops'],0)
        self.assertIsNotNone(u['damage_taken_estimate'])
        self.assertIn('Last valid calculation',u['damage_taken_calculation']['reason'])

    def test_old_result_layout_is_not_silently_inverted(self):
        f=BattleFixture(1,0);frame=f.reader.normalized(f.sample());key=bytes(range(32))
        for corrected in (False,True):
            frame['battle_result']=dict(outcome='Victory',source='native_result')
            if corrected:frame['battle_result']['result_layout']='result_context_slot_8'
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'result-test.wh3log'
                writer=LogWriter(path,key,dict(source='external-native',collector_revision=6))
                writer.write(frame);writer.close({})
                with patch('report.write_report') as write:
                    convert(path,key)
                result=write.call_args.args[1]['battle_result']
                if corrected:self.assertEqual(result['outcome'],'Victory')
                else:self.assertIsNone(result)


if __name__=='__main__':unittest.main()
