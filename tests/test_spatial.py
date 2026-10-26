import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from spatial import SpatialTimeline
from aggregate import Battle
from demo import frames


class SpatialTests(unittest.TestCase):
    def test_full_resolution_counters_pause_and_gaps(self):
        b=Battle(max_gap=80)
        for i in range(600):
            f=next(frames(1,1));f['sim_s']=i*4
            f['units'][0].update(damage=i*10,gold_damage=i,kills=i//10,xyz=[i,0,i])
            b.observe(f)
        f=copy.deepcopy(f);f['units'][0]['damage']=6001;b.observe(f)
        f['sim_s']+=4;f['gap_before']={'dropped_records':1};b.observe(f)
        f.pop('gap_before');f['sim_s']+=4;f['units']=[];b.observe(f)
        u=b.summary()['units'][0];p=u['spatial_timeline']['samples']
        self.assertEqual(len(p),602);self.assertLess(len(u['history']),240)
        self.assertEqual(p[599]['damage'],6001)
        self.assertEqual(p[599]['kills'],59)
        self.assertNotEqual(p[599]['segment'],p[600]['segment'])
        self.assertIsNone(p[601]['xyz']);self.assertIsNone(p[601]['damage'])
        self.assertEqual(p[600]['damage_taken_estimate'],u['history'][-1]['damage_taken_estimate'])
        self.assertEqual(p[600]['healing_received_estimate'],u['history'][-1]['healing_received_estimate'])
        p[0]['xyz'][0]=-123
        self.assertEqual(b.summary()['units'][0]['spatial_timeline']['samples'][0]['xyz'][0],0)

    def test_deployment_is_not_a_position_observation_or_live_history(self):
        initial=next(frames(1,1));initial['sim_s']=5
        f=next(frames(1,1));f['sim_s']=6
        f['battle_clock']=dict(source='native_battle_ui_clock',elapsed_s=6)
        f['deployment_baseline']=dict(sim_s=5,battle_clock=dict(elapsed_s=5),units=initial['units'])
        b=Battle();b.observe(f)
        self.assertEqual([p['t'] for p in b.summary()['units'][0]['spatial_timeline']['samples']],[1])
        live=Battle(keep_history=False);live.observe(f)
        self.assertIsNone(live.summary()['units'][0]['spatial_timeline'])

    def test_validation_and_retention(self):
        t=SpatialTimeline();t.MAX_SAMPLES=2
        t.observe(0,dict(xyz=[1,2,3],damage=4,gold_damage=True,kills=float('nan')))
        t.observe(4,dict(xyz=[1,2],damage=float('inf')))
        t.observe(8,dict(xyz=[1,False,3]))
        s=t.summary();self.assertEqual(s['truncated_from_s'],8)
        self.assertEqual(len(s['samples']),2)
        self.assertEqual(s['samples'][0]['xyz'],[1,2,3])
        self.assertIsNone(s['samples'][0]['gold_damage']);self.assertIsNone(s['samples'][0]['kills'])
        self.assertIsNone(s['samples'][1]['xyz']);self.assertIsNone(s['samples'][1]['damage'])
