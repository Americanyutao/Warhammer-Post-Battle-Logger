import copy
import json
from pathlib import Path
import struct
import unittest
from fixtures import BattleFixture
from aggregate import Battle
from combat_window import CombatWindow
from demo import frames
from report_assets import effect_texts_for,readable_effect_name
from memory import ReadError


class BattleClockTests(unittest.TestCase):
    def frame(self,elapsed,model=999):
        f=next(frames(1,1));f['sim_s']=elapsed;f['model_s']=model
        f['battle_clock']=dict(source='native_battle_ui_clock',elapsed_s=elapsed,limit_s=3600,remaining_s=3600-elapsed)
        return f

    def test_sixty_minute_countdown_at_fifty_nine_minutes_is_sixty_elapsed(self):
        fixture=BattleFixture(1,0);m=fixture.memory
        m.u(fixture.script+0x4a4,66400);m.write(fixture.roster+0xf8,struct.pack('<f',60))
        frame=fixture.reader.normalized(fixture.sample())
        self.assertEqual(frame['model_s'],66.4)
        self.assertEqual(frame['sim_s'],60)
        self.assertEqual(frame['battle_clock']['limit_s'],3600)
        self.assertEqual(frame['battle_clock']['remaining_s'],3540)

    def test_deployment_origin_and_fractional_spacing_are_preserved(self):
        gate=CombatWindow();deployment=self.frame(0,6.4);deployment['battle_phase']=4
        self.assertIsNone(gate.accept(deployment))
        b=Battle()
        for t in (.5,1.5,3.5,7.5,7.5,11.5):
            f=self.frame(t,6.4+t);f['battle_phase']=5;b.observe(gate.accept(f))
        s=b.summary()
        self.assertEqual(s['timeline_start_s'],0)
        self.assertEqual(s['time_reference']['initial_remaining_s'],3600)
        self.assertEqual([p['t'] for p in s['units'][0]['history']],[.5,1.5,3.5,7.5,11.5])
        self.assertEqual(s['paused_samples'],1)

    def test_initial_minus_current_countdown_uses_saved_deployment_reading(self):
        gate=CombatWindow();deployment=self.frame(5);deployment['battle_phase']=4
        self.assertIsNone(gate.accept(deployment))
        combat=self.frame(65);combat['battle_phase']=5;b=Battle();b.observe(gate.accept(combat))
        s=b.summary();self.assertEqual(s['units'][0]['history'][0]['t'],60)
        self.assertEqual(s['time_reference']['initial_remaining_s'],3595)

    def test_late_start_does_not_relabel_sixty_seconds_as_zero(self):
        b=Battle();b.observe(self.frame(60));s=b.summary()
        self.assertEqual(s['start_s'],60);self.assertEqual(s['timeline_start_s'],0)

    def test_legacy_capture_uses_deployment_baseline_without_modifying_raw_sample(self):
        raw=next(frames(1,1));raw['sim_s']=7.4;raw['deployment_baseline']=dict(sim_s=6.4,units=[],armies=[])
        b=Battle(dict(source='external-native',collector_revision=13));b.observe(raw)
        second=copy.deepcopy(raw);second.pop('deployment_baseline');second['sim_s']=11.4;b.observe(second)
        s=b.summary();self.assertAlmostEqual(s['start_s'],1);self.assertAlmostEqual(s['end_s'],5)
        self.assertEqual(s['timeline_start_s'],0);self.assertEqual(raw['sim_s'],7.4)
        self.assertIn('Estimated',s['time_reference']['precision'])

    def test_unknown_legacy_origin_does_not_get_fabricated(self):
        raw=next(frames(1,1));raw['sim_s']=75
        b=Battle(dict(source='external-native',collector_revision=13));b.observe(raw)
        self.assertEqual(b.summary()['start_s'],75)
        self.assertFalse(b.summary()['time_reference']['battle_origin_known'])

    def test_unlimited_and_scenario_override_keep_the_same_elapsed_source(self):
        f=BattleFixture(1,0);m=f.memory;settings=f.reader.ptr(f.roster+0x98)
        m.write(settings+0xf4,struct.pack('<f',0))
        clock=f.reader.battle_clock((f.engine,f.context,f.roster,f.my_army))
        self.assertIsNone(clock['remaining_s']);self.assertEqual(clock['elapsed_s'],10)
        override=m.allocate(0x30);m.q(f.context+0x645d0,override);m.write(f.context+0x645e0,b'\1');m.u(override+0x24,120000)
        clock=f.reader.battle_clock((f.engine,f.context,f.roster,f.my_army))
        self.assertEqual(clock['remaining_s'],110)

    def test_invalid_ui_clock_stays_unknown_instead_of_using_model_clock(self):
        f=BattleFixture(1,0);f.memory.write(f.roster+0xf8,struct.pack('<f',float('nan')))
        frame=f.reader.normalized(f.sample());self.assertIsNone(frame['sim_s']);self.assertEqual(frame['model_s'],10)

    def test_phase_transition_during_clock_read_is_rejected(self):
        f=BattleFixture(1,0);f.memory.u(f.roster+0xc8,5);sample=f.sample()
        def transition(address,size):
            if address==f.roster+0xf8:f.memory.u(f.roster+0xc8,8)
        f.memory.after_read=transition
        with self.assertRaises(ReadError):f.reader.normalized(sample)


class EffectCatalogTests(unittest.TestCase):
    def test_full_catalog_and_contact_groups_are_bundled(self):
        p=Path(__file__).resolve().parents[1]/'assets/effect-texts.json'
        j=json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(j['coverage']['abilities'],len(j['abilities']))
        self.assertEqual(j['coverage']['phases'],len(j['phases']))
        self.assertGreaterEqual(len(j['abilities']),3179);self.assertGreaterEqual(len(j['phases']),2526)
        self.assertTrue(j['contact_groups'])
        self.assertEqual(j['phases']['wh2_dlc09_unit_passive_guardian']['name'],'Guardian')
        self.assertTrue(all(len(v)==64 for v in j['source_hashes'].values()))

    def test_unknown_ids_and_formatting_never_become_display_names(self):
        root=Path(__file__).resolve().parents[1]/'assets'
        effects=[dict(key='unknown:wh_mod_buff',name='wh_mod_buff',polarity='positive'),
                 dict(key='unknown:wh_mod_debuff',name='{{tr:missing}}',polarity='negative')]
        resolved=effect_texts_for([dict(effect_timeline=dict(effects=effects))],root)
        self.assertEqual([v['name'] for v in resolved.values()],['Unidentified buff','Unidentified debuff'])
        self.assertEqual(readable_effect_name('[[col:red]]Poison![[/col]]'),'Poison!')
        for value in ('wh_main_spell_foo','custom_mod_phase',None,'{{tr:missing}}','0x12345678','12345'):
            self.assertIsNone(readable_effect_name(value))

    def test_every_bundled_phase_has_a_readable_display_fallback(self):
        root=Path(__file__).resolve().parents[1]/'assets'
        index=json.loads((root/'effect-texts.json').read_text(encoding='utf-8'))
        effects=[dict(key=key+':'+key,name=key,polarity=phase['polarity']) for key,phase in index['phases'].items()]
        texts=effect_texts_for([dict(effect_timeline=dict(effects=effects))],root)
        self.assertEqual(len(texts),len(index['phases']))
        self.assertTrue(all(readable_effect_name(t['name']) for t in texts.values()))


if __name__=='__main__':unittest.main()
