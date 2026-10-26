"""Validate the requested ceiling formula and its comparability guards."""
import sys
from pathlib import Path
import unittest
import struct
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from damage_taken import DamageTaken
from aggregate import Battle
from fixtures import BattleFixture


def unit(hp=8000,budget=6000,maximum=8000,**extra):
    return dict(hp_cached=hp,healing_budget_remaining_hp=budget,
        healing_budget_unlimited=False,hp_max_cached=maximum,**extra)


class DamageTakenTests(unittest.TestCase):
    def test_summon_damage_before_first_sample_is_included(self):
        e=DamageTaken();e.observe(10,unit(hp=7000,budget=5800,spawned=True))
        self.assertEqual(e.basis['ceiling_hp'],14000)
        self.assertTrue(e.basis['assumed_summon_start'])
        self.assertEqual(e.amount,1200)
        self.assertEqual(e.healing,200)
        e.observe(11,unit(hp=6500,budget=5600,spawned=True))
        self.assertEqual(e.amount,1900)
        self.assertEqual(e.healing,400)

    def test_summon_waits_for_maximum_hp(self):
        e=DamageTaken();e.observe(10,unit(maximum=None,spawned=True))
        self.assertIsNone(e.basis)
        e.observe(11,unit(hp=7000,spawned=True))
        self.assertEqual(e.amount,1000)

    def test_damage_and_healing_in_same_tick(self):
        e=DamageTaken();e.observe(0,unit())
        # 1,000 damage followed by 800 healing: net HP loss only 200.
        e.observe(1,unit(hp=7800,budget=5200))
        self.assertEqual(e.amount,1000)
        self.assertEqual(e.fraction,.125)

    def test_death_without_healing_matches_175_to_75_percent(self):
        e=DamageTaken();e.observe(0,unit())
        e.observe(10,unit(hp=0,maximum=None))
        self.assertEqual(e.amount,8000)
        self.assertEqual(e.fraction,1)
        self.assertEqual(e.summary()['damage_taken_calculation']['current_ceiling_hp'],6000)

    def test_full_healing_budget_then_death_exceeds_maximum_hp(self):
        e=DamageTaken();e.observe(0,unit())
        e.observe(10,unit(hp=0,budget=0))
        self.assertEqual(e.amount,14000)
        self.assertEqual(e.fraction,1.75)

    def test_healing_alone_does_not_increase_taken(self):
        e=DamageTaken();e.observe(0,unit(hp=5000))
        e.observe(1,unit(hp=5800,budget=5200))
        self.assertEqual(e.amount,0)
        self.assertEqual(e.healing,800)
        self.assertEqual(e.summary()['healing_budget_remaining_calculated'],5200)

    def test_wounded_start_with_damage_and_healing(self):
        e=DamageTaken();e.observe(0,unit(hp=6000))
        # 1,000 incoming damage and 500 healing, starting below maximum HP.
        e.observe(1,unit(hp=5500,budget=5500))
        self.assertEqual(e.amount,1000)
        self.assertEqual(e.healing,500)
        self.assertEqual(e.remaining_budget,5500)
        self.assertEqual(e.basis['hp'],6000)

    def test_initial_capacity_modifier_is_preserved(self):
        # Capacity is captured, rather than assuming a 75% budget.
        for initial_budget in (0,800,12000):
            e=DamageTaken();e.observe(0,unit(hp=6000,budget=initial_budget))
            e.observe(1,unit(hp=5000,budget=initial_budget))
            self.assertEqual((e.amount,e.healing,e.remaining_budget),(1000,0,initial_budget))

    def test_no_healing_spending_then_normal_healing(self):
        e=DamageTaken();e.observe(0,unit(hp=6000))
        # A prevented heal changes neither HP nor budget; later damage still counts.
        e.observe(1,unit(hp=6000));e.observe(2,unit(hp=5000))
        self.assertEqual((e.amount,e.healing),(1000,0))
        e.observe(3,unit(hp=5500,budget=5500))
        self.assertEqual((e.amount,e.healing,e.remaining_budget),(1000,500,5500))

    def test_minor_cache_recovery_below_baseline_does_not_discard_estimate(self):
        e=DamageTaken();e.observe(0,unit())
        e.observe(1,unit(hp=5000));self.assertEqual(e.amount,3000)
        # HP cache and native budget need not update at the same instant.
        e.observe(2,unit(hp=5010,budget=5995))
        self.assertIsNone(e.invalid)
        self.assertEqual(e.amount,2995)

    def test_multi_model_uses_unclamped_budget(self):
        e=DamageTaken();e.observe(0,unit(models_initial=120,healing_ceiling_fraction_raw=1))
        e.observe(1,unit(hp=7000,models_initial=120,healing_ceiling_fraction_raw=.8))
        self.assertEqual(e.amount,1000)
        self.assertEqual(e.basis['method'],'hp_plus_remaining_budget')

    def test_legacy_fraction_only_supported_for_single_entities(self):
        for count in (1,120):
            e=DamageTaken();e.observe(0,dict(models_initial=count,hp_max_cached=8000,healing_ceiling_fraction_raw=1.75))
            e.observe(1,dict(models_initial=count,hp_max_cached=8000,healing_ceiling_fraction_raw=.75))
            if count==1:self.assertEqual(e.amount,8000)
            else:self.assertIsNone(e.amount)

    def test_missing_current_values_are_not_filled_with_last_ceiling(self):
        e=DamageTaken();e.observe(0,unit());e.observe(1,unit(hp=7000))
        self.assertEqual(e.amount,1000)
        e.observe(2,unit(hp=None))
        self.assertIsNone(e.amount)
        e.observe(3,unit(hp=6500))
        self.assertEqual(e.amount,1500)

    def test_budget_increase_or_maximum_change_invalidates_comparison(self):
        for changed in (unit(budget=6500),unit(maximum=9000)):
            e=DamageTaken();e.observe(0,unit());e.observe(1,changed)
            self.assertIsNone(e.amount)
            self.assertIsNotNone(e.invalid)
            e.observe(2,unit());self.assertIsNone(e.amount)

    def test_unlimited_budget_is_not_a_measurable_damage_counter(self):
        e=DamageTaken();e.observe(0,unit());u=unit();u['healing_budget_unlimited']=True
        e.observe(1,u);self.assertIsNone(e.amount)

    def test_capacity_changes_while_hp_missing_are_not_overlooked(self):
        for changed in (unit(hp=None,budget=7000),unit(hp=None,maximum=9000)):
            e=DamageTaken();e.observe(0,unit());e.observe(1,changed)
            e.observe(2,unit(hp=7000,budget=5000))
            self.assertIsNone(e.amount)
            self.assertIsNotNone(e.invalid)

    def test_waits_for_native_baseline_and_does_not_fallback_to_clamped_field(self):
        e=DamageTaken();e.observe(0,unit(hp=None,models_initial=1,healing_ceiling_fraction_raw=1.75))
        self.assertIsNone(e.basis)
        e.observe(5,unit(hp=7000));e.observe(8,unit(hp=6500))
        self.assertEqual(e.amount,500)
        self.assertEqual(e.basis['sim_s'],5)

    def test_ceiling_increase_does_not_become_negative_damage(self):
        e=DamageTaken();e.observe(0,unit(hp=5000));e.observe(1,unit(hp=6000))
        self.assertIsNone(e.amount)
        self.assertIn('rose',e.reason)

    def test_native_aggregation_publishes_estimate_and_timeline(self):
        f=BattleFixture();b=Battle();b.observe(f.reader.normalized(f.sample()))
        f.memory.u(f.own[0]['address']+0x6b0,7300)
        stats=f.reader.ptr(f.own[0]['adapter']+0x3d48)
        f.memory.u(stats+0x264,5200);f.memory.u(f.script+0x4a4,11000);f.memory.write(f.roster+0xf8,struct.pack('<f',11.))
        b.observe(f.reader.normalized(f.sample()))
        row=b.summary()['units'][0]
        self.assertEqual(row['damage_taken_estimate'],1000)
        self.assertEqual(row['history'][-1]['damage_taken_estimate'],1000)
        self.assertEqual(row['damage_taken_calculation']['as_of_s'],11)

if __name__=='__main__':unittest.main()
