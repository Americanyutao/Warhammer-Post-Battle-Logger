import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aggregate import Battle
from demo import frames
from recharge import RechargeStats


class RechargeTests(unittest.TestCase):
    def test_average_uses_battle_time_and_pause_replaces_pending_rate(self):
        stats=RechargeStats()
        for t,rate in [(0,.1),(4,.9),(4,.3),(12,.2)]:stats.observe(t,dict(maximum=100,recharge_per_second=rate),1)
        result=stats.summary()
        self.assertEqual(result['highest'],.3);self.assertEqual(result['lowest'],.1)
        self.assertAlmostEqual(result['average'],2.8/12)
        self.assertEqual(result['covered_seconds'],12);self.assertEqual(result['observed_samples'],3)
        self.assertEqual(result['average_method'],'battle_time_weighted')
        self.assertEqual(result,stats.summary())

    def test_unknown_initialization_gaps_and_zero_rate(self):
        stats=RechargeStats()
        for t,rate,maximum,segment in [(0,5,0,1),(4,.1,100,1),(8,None,100,1),(12,.2,100,1),(16,0,100,2),(20,.3,100,2)]:
            stats.observe(t,dict(maximum=maximum,recharge_per_second=rate),segment)
        result=stats.summary()
        self.assertEqual(result['highest'],.3);self.assertEqual(result['lowest'],0)
        self.assertEqual(result['average'],0);self.assertEqual(result['covered_seconds'],4)
        unknown=RechargeStats();unknown.observe(0,dict(recharge_per_second=float('nan')),1)
        self.assertIsNone(unknown.summary()['average'])
        unknown.observe(4,dict(recharge_per_second=True),1);self.assertIsNone(unknown.summary()['highest'])

    def test_full_resolution_extrema_survive_history_downsampling_and_live_mode(self):
        for keep in [True,False]:
            b=Battle(keep_history=keep)
            for i in range(600):
                f=next(frames(1,1));f['sim_s']=i
                f['armies'][0]['recharge_per_second']=.8 if i==337 else .1
                b.observe(f)
            army=b.summary()['armies'][0]
            self.assertEqual(army['recharge_stats']['highest'],.8)
            self.assertEqual(army['recharge_stats']['lowest'],.1)
            self.assertAlmostEqual(army['recharge_stats']['average'],(.8+.1*598)/599)
            self.assertLess(len(army['history']),240)
