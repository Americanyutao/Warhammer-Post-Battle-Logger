"""Test native budget semantics, including the multi-model display clamp."""
import sys
from pathlib import Path
import struct
import unittest
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from fixtures import BattleFixture
from aggregate import Battle

class HealingBudgetTests(unittest.TestCase):
    def test_same_budget_for_single_and_multi_model_despite_display_clamp(self):
        f=BattleFixture()
        for i,count in enumerate((1,120)):
            unit=f.own[i]
            f.memory.u(unit['address']+0x634,count)
            f.memory.write(unit['address']+0x6cc,struct.pack('<f',1.6875 if count==1 else .9375))
        sample=f.sample()
        for u in sample.units[:2]:
            self.assertEqual(u.values['healing_budget_remaining_hp'],6000)
            self.assertEqual(u.values['healing_budget_remaining_fraction'],.75)
            self.assertEqual(u.values['healing_budget_ceiling_hp'],13500)
        self.assertNotEqual(sample.units[0].healing_cap,sample.units[1].healing_cap)

    def test_budget_consumption_preserved_in_history(self):
        f=BattleFixture();b=Battle();b.observe(f.reader.normalized(f.sample()))
        u=f.own[0];stats=f.reader.ptr(u['adapter']+0x3d48)
        f.memory.u(stats+0x264,5200);f.memory.u(f.script+0x4a4,11000);f.memory.write(f.roster+0xf8,struct.pack('<f',11.))
        b.observe(f.reader.normalized(f.sample()))
        row=b.summary()['units'][0]
        self.assertEqual(row['history'][-1]['healing_budget_remaining_hp'],5200)
        self.assertEqual(row['last_observed']['healing_budget_remaining_hp']['sim_s'],11)

    def test_unlimited_flag_is_not_a_zero_remaining_cap(self):
        f=BattleFixture();stats=f.reader.ptr(f.own[0]['adapter']+0x3d48)
        f.memory.write(stats+0x268,b'\x01')
        values=f.sample().units[0].values
        self.assertTrue(values['healing_budget_unlimited'])
        self.assertIsNone(values['healing_budget_remaining_hp'])
        self.assertIsNone(values['healing_budget_ceiling_hp'])

    def test_unreadable_budget_does_not_erase_spawn_flag_or_other_stats(self):
        f=BattleFixture();u=f.own[0]
        f.memory.write(u['adapter']+0x1b8,b'\x01')
        f.memory.q(u['adapter']+0x3d48,0)
        values=f.sample().units[0].values
        self.assertTrue(values['spawned'])
        self.assertIsNone(values['healing_budget_remaining_hp'])
        self.assertEqual(values['damage'],125)

    def test_inactive_cache_retains_native_budget_without_inventing_ceiling(self):
        f=BattleFixture();f.memory.write(f.own[0]['address']+0x6fb,b'\x00')
        values=f.sample().units[0].values
        self.assertEqual(values['healing_budget_remaining_hp'],6000)
        self.assertIsNone(values['healing_budget_ceiling_hp'])
        self.assertIsNone(values['healing_budget_remaining_fraction'])

if __name__=='__main__':unittest.main()
