import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from activities import ActivityTimeline
from aggregate import Battle
from demo import frames


class ActivityTests(unittest.TestCase):
    def test_full_resolution_pause_gap_missing_and_unknown(self):
        b=Battle(max_gap=80)
        for i in range(600):
            f=next(frames(1,1));f['sim_s']=i*4;f['units'][0].update(firing=i<3,idle=None)
            b.observe(f)
        f=copy.deepcopy(f);f['units'][0]['firing']=True;b.observe(f)
        f['sim_s']+=4;f['gap_before']={'dropped_records':1};f['units'][0]['firing']=False;b.observe(f)
        f=copy.deepcopy(f);f.pop('gap_before');f['sim_s']+=4;f['units']=[];b.observe(f)
        u=b.summary()['units'][0];samples=u['activity_timeline']['samples']
        self.assertEqual(len(samples),602);self.assertLess(len(u['history']),240)
        self.assertTrue(samples[599]['values']['firing']);self.assertFalse(samples[600]['values']['firing'])
        self.assertIsNone(samples[601]['values']);self.assertIsNone(samples[0]['values']['idle'])
        self.assertNotEqual(samples[599]['segment'],samples[600]['segment'])
        samples[0]['values']['firing']=False
        self.assertTrue(b.summary()['units'][0]['activity_timeline']['samples'][0]['values']['firing'])

    def test_deployment_is_not_an_activity_observation(self):
        initial=next(frames(1,1));initial['sim_s']=5
        f=next(frames(1,1));f['sim_s']=6
        f['battle_clock']=dict(source='native_battle_ui_clock',elapsed_s=6)
        f['deployment_baseline']=dict(sim_s=5,battle_clock=dict(elapsed_s=5),units=initial['units'])
        b=Battle();b.observe(f)
        self.assertEqual([p['t'] for p in b.summary()['units'][0]['activity_timeline']['samples']],[1])
        live=Battle(keep_history=False);live.observe(f)
        self.assertIsNone(live.summary()['units'][0]['activity_timeline'])

    def test_retention_bound_and_bool_validation(self):
        t=ActivityTimeline();t.MAX_SAMPLES=1
        t.observe(0,dict(idle=True,firing=1));t.observe(4,dict(idle=False))
        self.assertEqual(t.summary()['samples'][0]['values'],dict(idle=True,firing=None))
        self.assertEqual(t.summary()['truncated_from_s'],4)
