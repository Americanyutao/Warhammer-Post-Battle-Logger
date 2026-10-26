"""Check verified numeric fields, graph extrema and the healing identity."""
import json
from pathlib import Path
import struct
import sys
import unittest
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from fixtures import BattleFixture
from damage_taken import DamageTaken
from aggregate import Battle
from demo import frames


class ReportFieldsTests(unittest.TestCase):
    def test_flat_ammo_is_not_reconstructed_from_percentages(self):
        f=BattleFixture();u=f.own[0]
        f.memory.write(u['address']+0x6c4,struct.pack('<f',.125))
        values=f.sample().units[0].values
        self.assertEqual(values['primary_ammo'],20)
        self.assertEqual(values['primary_ammo_max'],40)
        self.assertEqual(values['secondary_ammo'],5)
        self.assertEqual(values['secondary_ammo_max'],10)
        self.assertEqual(values['primary_ammo_fraction'],.125)

    def test_leadership_keeps_negative_values_and_does_not_use_morale_enum(self):
        f=BattleFixture();u=f.own[0];morale=f.reader.ptr(u['address']+0x160)
        f.memory.write(morale+0x48,struct.pack('<i',-35))
        f.memory.u(u['address']+0x6f0,7)
        sample=f.sample().units[0].values
        self.assertEqual(sample['leadership'],-35)
        self.assertEqual(sample['morale_state'],7)
        self.assertTrue(sample['shattered'])

    def test_unreadable_leadership_does_not_erase_ammo_or_damage(self):
        f=BattleFixture();f.memory.q(f.own[0]['address']+0x160,0)
        values=f.sample().units[0].values
        self.assertIsNone(values['leadership'])
        self.assertEqual(values['primary_ammo'],20)
        self.assertEqual(values['damage'],125)

    def test_numeric_fields_survive_normalization_and_history(self):
        f=BattleFixture();b=Battle();b.observe(f.reader.normalized(f.sample()))
        p=b.summary()['units'][0]['history'][0]
        self.assertEqual(p['primary_ammo'],20)
        self.assertEqual(p['leadership'],65)

    def test_global_elevation_floor_includes_enemy_and_discarded_history_points(self):
        b=Battle()
        for i,frame in enumerate(frames(2,600)):
            frame['units'][0]['xyz']=[-300,50,400]
            frame['units'][1]['xyz']=[900 if i==77 else 0,-123 if i==77 else 40,-800 if i==77 else 0]
            b.observe(frame)
        s=b.summary()
        self.assertEqual(s['elevation_min'],-123)
        self.assertEqual(s['movement_bounds'],dict(xmin=-300,xmax=900,zmin=-800,zmax=400))
        self.assertLess(len(s['units'][1]['history']),601)

    def test_healing_formula_matches_damage_and_healing_in_same_interval(self):
        e=DamageTaken()
        e.observe(0,dict(hp_cached=8000,hp_max_cached=8000,healing_budget_remaining_hp=6000))
        e.observe(1,dict(hp_cached=7800,hp_max_cached=8000,healing_budget_remaining_hp=5200))
        self.assertEqual(e.amount,1000)
        self.assertEqual(e.healing,800)
        self.assertEqual(e.summary()['healing_received_estimate'],800)

    def test_below_maximum_baseline_does_not_turn_missing_hp_into_negative_healing(self):
        e=DamageTaken()
        e.observe(0,dict(hp_cached=6000,hp_max_cached=8000,healing_budget_remaining_hp=6000))
        e.observe(1,dict(hp_cached=6500,hp_max_cached=8000,healing_budget_remaining_hp=5500))
        self.assertEqual(e.amount,0)
        self.assertEqual(e.healing,500)

    def test_unit_value_reference_keeps_ambiguous_lord_mount_costs(self):
        refs=json.loads((P/'assets/unit-values.json').read_text(encoding='utf-8'))
        costs={r['value'] for r in refs['names']['Necrarch Vampire Lord'] if not r['summoned_variant']}
        self.assertGreater(len(costs),1)
        self.assertIn(650,costs)
        self.assertIn(1950,costs)

if __name__=='__main__':unittest.main()
