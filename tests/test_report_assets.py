"""Whole-library resolution, translation references and native identity failures."""
import json
from pathlib import Path
import struct
import sys
import unittest
P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'src'),str(P/'tests')]
from report_assets import assets_for, index_at
from fixtures import BattleFixture
from aggregate import Battle
from demo import frames


def unit(name,key=None,uid='test',portrait=None):
    return dict(id=uid,name=name,side='Allied',army='1',first={},last=dict(unit_key=key,portrait_path=portrait))


class ReportAssetsTests(unittest.TestCase):
    def test_character_defaults_use_database_caste_without_inferring_custom_names(self):
        a=assets_for([unit('Imrik','wh2_dlc15_hef_cha_imrik_0','lord'),
            unit('Gutrot Spume','wh3_dlc29_chs_cha_gutrot_spume','hero'),
            unit('Archers','wh2_main_hef_inf_archers_0','infantry'),unit('Unknown custom hero',uid='unknown')])
        self.assertTrue(a['unit_info']['lord']['character']);self.assertTrue(a['unit_info']['hero']['character'])
        self.assertFalse(a['unit_info']['infantry']['character']);self.assertNotIn('unknown',a['unit_info'])

    def test_full_original_library_is_kept_locally(self):
        index=index_at(P/'assets/game-assets.json')
        actual={p.relative_to(P.parent/'Local-files').as_posix() for folder in ['ui/units','ui/portraits']
                for p in (P.parent/'Local-files'/folder).rglob('*.png')}
        self.assertGreater(len(actual),3000)
        self.assertTrue(actual.issubset(index['provenance']))
        self.assertTrue(all((P/'assets/game'/path).is_file() for path in actual))

    def test_vehicle_cards_follow_land_unit_driver_variants(self):
        a=assets_for([unit('Steam Tank','wh_main_emp_veh_steam_tank','normal'),
            unit('Steam Tank','wh2_dlc13_emp_veh_steam_tank_imperial_supply','supply')])
        for uid in ('normal','supply'):
            self.assertEqual(a['unit_cards'][uid],'ui/units/icons/wh_main_emp_steamtank.png')
            self.assertTrue(a['images'][a['unit_cards'][uid]].startswith('data:image/png;base64,'))

    def test_legendary_hero_nested_translation_resolves(self):
        name='{{tr:land_units_onscreen_name_wh3_dlc29_chs_cha_gutrot_spume_warshrine}}'
        a=assets_for([unit(name)])
        self.assertEqual(a['labels'][name],'Gutrot Spume')
        self.assertIn('chs_gutrot_spume',a['unit_cards']['test'])

    def test_same_display_name_can_use_different_unit_cards(self):
        a=assets_for([unit('Archers','wh2_main_hef_inf_archers_0','elf'),unit('Archers','wh2_dlc13_emp_inf_archers_0','empire')])
        self.assertIn('elf',a['unit_cards']);self.assertIn('empire',a['unit_cards'])
        self.assertNotEqual(a['unit_cards']['elf'],a['unit_cards']['empire'])
        self.assertEqual(a['unit_values_by_id']['elf'][0]['unit_key'],'wh2_main_hef_inf_archers_0')
        self.assertEqual(a['unit_values_by_id']['empire'][0]['unit_key'],'wh2_dlc13_emp_inf_archers_0')

    def test_custom_character_uses_native_portrait_and_only_needed_images(self):
        a=assets_for([unit('Custom hero',portrait='ui/portraits/portholes/no_culture/dae_chs_harald_hammerstorm_0.png')])
        self.assertIn('harald_hammerstorm',a['unit_cards']['test'])
        self.assertLessEqual(len(a['images']),len(set(a['stats'].values()))+1)

    def test_unknown_old_custom_name_does_not_get_an_invented_identity(self):
        a=assets_for([unit('Unknown custom hero')])
        self.assertNotIn('test',a['unit_cards'])
        self.assertIn('unavailable',a['unit_notes']['test'])

    def test_native_identity_and_portrait_survive_normalization(self):
        f=BattleFixture();m=f.memory;u=f.own[0]
        def text(at,value):
            data=value.encode('utf-8');ptr=m.allocate(len(data)+1);m.write(ptr,data+b'\0')
            m.write(at,struct.pack('<IIQ',len(data),len(data),ptr))
        record=m.allocate(0x400);setup=m.allocate(0x510)
        m.q(u['address']+0x168,record);m.q(u['address']+0x158,setup)
        key='wh3_pro11_chs_cha_harald_hammerstorm'
        portrait='ui/portraits/portholes/no_culture/dae_chs_harald_hammerstorm_0.png'
        text(record+0x3e0,key);text(setup+0x4e8,portrait)
        values=f.reader.normalized(f.sample())['units'][0]
        self.assertEqual(values['unit_key'],key);self.assertEqual(values['portrait_path'],portrait)
        self.assertEqual(values['damage'],125)

    def test_unreadable_identity_does_not_erase_stats(self):
        f=BattleFixture();u=f.reader.normalized(f.sample())['units'][0]
        self.assertIsNone(u['unit_key']);self.assertEqual(u['damage'],125)
        self.assertIsNotNone(u['hp_cached'])

    def test_initial_models_waits_for_first_readable_count(self):
        b=Battle();fs=list(frames(1,2))
        fs[0]['units'][0].update(models=None,models_initial=None)
        fs[1]['units'][0].update(models=3,models_initial=4)
        fs[2]['units'][0].update(models=21,models_initial=32)
        for f in fs:b.observe(f)
        u=b.summary()['units'][0]
        self.assertEqual((u['initial_models_observed'],u['initial_models_maximum']),(3,4))


if __name__=='__main__':unittest.main()
