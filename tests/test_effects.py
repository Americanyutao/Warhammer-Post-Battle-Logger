import copy
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest

from fixtures import BattleFixture
from aggregate import Battle
from combat_window import CombatWindow
from demo import frames
from effects import EffectTimeline
from logfile import LogWriter, read_log
from report import convert
from report_assets import effect_texts_for


BUFF = dict(key='ability:phase',name='Example buff',polarity='positive')
DEBUFF = dict(key='curse:phase',name='Example debuff',polarity='negative')


def byte_string(memory,address,text):
    raw=text.encode('utf-8')
    if len(raw)<=14:
        header=bytearray(16);header[:len(raw)]=raw;header[15]=0x80|len(raw)
        memory.write(address,header)
    else:
        data=memory.allocate(len(raw));memory.write(data,raw)
        memory.write(address,struct.pack('<IIQ',len(raw),len(raw),data))


def native_effect(f,polarity=0,ability_name=None,phase_name='Phase name',intensity=1.):
    m=f.memory
    key=m.allocate(16);byte_string(m,key,'test_ability')
    phase=m.allocate(0xc0);byte_string(m,phase+8,'test_phase')
    m.u(phase+0x1c,polarity)
    if phase_name is not None:
        name=m.allocate(16);m.string(name,phase_name);m.q(phase+0x68,name)
    ability=0
    if ability_name is not None:
        ability=m.allocate(0x180);name=m.allocate(16);m.string(name,ability_name);m.q(ability+0x168,name)
        m.write(ability+0x2c,b'\x01')  # Passive must not be filtered.
    raw=bytearray(struct.pack('<QQQ',key,phase,ability)+bytes(0x48-24))
    struct.pack_into('<f',raw,0x44,intensity)
    return raw


def install_effects(f,effects):
    raw=b''.join(effects);data=f.memory.allocate(max(8,len(raw)));f.memory.write(data,raw)
    f.memory.write(f.own[0]['address']+0x604,struct.pack('<IQ',len(effects),data))
    return data


class NativeEffectTests(unittest.TestCase):
    def read_effects(self,f):return f.reader.normalized(f.sample())['units'][0]['active_effects']

    def test_names_keys_polarity_and_passives(self):
        f=BattleFixture(1,0)
        install_effects(f,[native_effect(f,ability_name='Spirit Leech'),native_effect(f,1,phase_name='呪い'),native_effect(f,3,phase_name=None)])
        effects=self.read_effects(f)
        self.assertEqual([e['name'] for e in effects],['Spirit Leech','呪い','test_ability'])
        self.assertEqual([e['polarity'] for e in effects],['positive','negative','other'])
        self.assertEqual(effects[0]['key'],'test_ability:test_phase')
        self.assertEqual(effects[0]['intensity'],1.)
        self.assertEqual(len({e['instance_id'] for e in effects}),3)

    def test_per_entry_intensity_and_battle_scale(self):
        f=BattleFixture(1,0)
        install_effects(f,[native_effect(f,intensity=1.5),native_effect(f,intensity=0.),native_effect(f,intensity=float('nan'))])
        settings=struct.unpack('<Q',f.memory.read(f.roster+0x98,8))[0]
        f.memory.write(settings+0x100,struct.pack('<f',.75))
        frame=f.reader.normalized(f.sample())
        self.assertEqual([e['intensity'] for e in frame['units'][0]['active_effects']],[1.5,0.,None])
        self.assertEqual(frame['effect_damage_scale'],.75)
        f.memory.write(settings+0x100,struct.pack('<f',float('inf')))
        self.assertIsNone(f.reader.normalized(f.sample())['effect_damage_scale'])

    def test_empty_inactive_and_unreadable_are_distinct(self):
        f=BattleFixture(1,0);self.assertEqual(self.read_effects(f),[])
        f.memory.write(f.own[0]['address']+0x6fb,b'\0');self.assertIsNone(self.read_effects(f))
        f.memory.write(f.own[0]['address']+0x6fb,b'\1')
        f.memory.write(f.own[0]['address']+0x6f4,b'\0');self.assertIsNone(self.read_effects(f))
        f.memory.write(f.own[0]['address']+0x6f4,b'\1')
        f.memory.write(f.own[0]['address']+0x604,struct.pack('<IQ',1,1));self.assertIsNone(self.read_effects(f))

    def test_bounds_and_malformed_entry_do_not_report_partial_absence(self):
        f=BattleFixture(1,0);a=f.own[0]['address'];f.memory.u(a+0x604,257)
        self.assertIsNone(self.read_effects(f))
        install_effects(f,[native_effect(f),bytes(0x48)])
        self.assertIsNone(self.read_effects(f))

    def test_list_change_during_read_is_unknown(self):
        f=BattleFixture(1,0);data=install_effects(f,[native_effect(f)])
        def change(address,size):
            if address==data:f.memory.u(f.own[0]['address']+0x604,0)
        f.memory.after_read=change
        self.assertIsNone(self.read_effects(f))

    def test_entry_change_with_unchanged_header_is_unknown(self):
        f=BattleFixture(1,0);data=install_effects(f,[native_effect(f)])
        def change(address,size):
            if address==data:f.memory.u(data+0x38,777)
        f.memory.after_read=change
        self.assertIsNone(self.read_effects(f))

    def test_native_clock_drives_points_for_all_speeds_and_pause(self):
        f=BattleFixture(1,0);install_effects(f,[native_effect(f)])
        b=Battle(max_gap=80)
        times=[10,10.5,11.5,13.5,17.5,17.5,21.5]
        for t in times:
            f.memory.u(f.script+0x4a4,int((t+6.4)*1000));f.memory.write(f.roster+0xf8,struct.pack('<f',t));b.observe(f.reader.normalized(f.sample()))
        s=b.summary();points=s['units'][0]['effect_timeline']['samples']
        self.assertEqual([p[0] for p in points],[10,10.5,11.5,13.5,17.5,21.5])
        self.assertEqual(s['paused_samples'],1)


class EffectTimelineTests(unittest.TestCase):
    def frame(self,t,effects):
        frame=next(frames(1,1));frame['sim_s']=t;frame['units'][0]['active_effects']=effects
        return frame

    def test_detected_ticks_only_with_unknown_absent_missing_and_queue_gap(self):
        b=Battle(max_gap=80)
        for t,effects in [(0,[BUFF]),(.5,[]),(1.5,None),(3.5,[BUFF,DEBUFF])]:b.observe(self.frame(t,effects))
        empty=self.frame(7.5,[]);empty['units']=[];b.observe(empty)
        last=self.frame(11.5,[DEBUFF]);last['gap_before']={'dropped_records':3};b.observe(last)
        timeline=b.summary()['units'][0]['effect_timeline']
        self.assertEqual(timeline['samples'],[[0,[0]],[.5,[]],[1.5,None],[3.5,[0,1]],[7.5,None],[11.5,[1]]])
        self.assertEqual(timeline['effects'],[BUFF,DEBUFF])

    def test_paused_samples_replace_without_adding_duration_or_ghost_rows(self):
        timeline=EffectTimeline();timeline.observe(10,[BUFF]);timeline.observe(10,[DEBUFF,DEBUFF])
        self.assertEqual(timeline.summary()['effects'],[DEBUFF,DEBUFF])
        self.assertEqual(timeline.summary()['samples'],[[10,[0,1]]])
        self.assertEqual(timeline.summary()['segments'],[0])

    def test_distinct_stacks_keep_per_tick_intensity_and_paused_replacement(self):
        timeline=EffectTimeline()
        a=dict(BUFF,instance_id='a',intensity=1.)
        b=dict(BUFF,instance_id='b',intensity=1.5)
        timeline.observe(0,[a,b],1,.75)
        timeline.observe(1,[dict(a,intensity=2.),b],1,1.)
        timeline.observe(1,[dict(a,intensity=0.)],1,.5)
        result=timeline.summary()
        self.assertEqual(result['effects'],[BUFF,BUFF])
        self.assertEqual(result['samples'],[[0,[0,1]],[1,[0]]])
        self.assertEqual(result['values'],[{'0':dict(intensity=1.,damage_scale=.75),'1':dict(intensity=1.5,damage_scale=.75)},
            {'0':dict(intensity=0.,damage_scale=.5)}])

    def test_aggregate_preserves_unknown_intensity_instead_of_assuming_one(self):
        b=Battle()
        first=self.frame(0,[dict(BUFF,intensity=1.5)]);first['effect_damage_scale']=.75
        b.observe(first);b.observe(self.frame(1,[dict(BUFF,intensity=float('nan'))]))
        values=b.summary()['units'][0]['effect_timeline']['values']
        self.assertEqual(values,[{'0':dict(intensity=1.5,damage_scale=.75)},{'0':dict(intensity=None,damage_scale=None)}])

    def test_effect_segments_preserve_recording_gaps_without_splitting_speed_changes(self):
        b=Battle(max_gap=80)
        b.observe(self.frame(0,[BUFF]));b.observe(self.frame(4,[BUFF]))
        gap=self.frame(8,[BUFF]);gap['gap_before']={'dropped_records':3};b.observe(gap)
        b.observe(self.frame(12,[BUFF]))
        timeline=b.summary()['units'][0]['effect_timeline']
        self.assertEqual(timeline['segments'],[1,1,2,2])

    def test_game_english_text_and_modifiers_are_bundled_only_for_used_effects(self):
        root=Path(__file__).resolve().parents[1]/'assets'
        leech='wh_main_spell_death_spirit_leech:wh_main_spell_death_spirit_leech'
        poison='wh_main_unit_contact_poison:wh_main_unit_contact_poison'
        units=[dict(effect_timeline=dict(effects=[dict(key=leech,name='Localized name'),dict(key=poison,name='Raw name')]))]
        result=effect_texts_for(units,root)
        self.assertEqual(set(result),{leech,poison})
        self.assertEqual(result[leech]['name'],'Spirit Leech')
        self.assertNotIn('description',result[leech])
        self.assertEqual(result[leech]['source_label'],'Spell')
        self.assertEqual(result[leech]['health']['damage'],67)
        self.assertIn(dict(label='Speed',how='mult',value=.85),result[poison]['modifiers'])
        self.assertNotIn('[[',json.dumps(result))
        self.assertEqual(effect_texts_for([dict(effect_timeline=dict(effects=[dict(key='mod:unknown',name='Mod effect')]))],root)['mod:unknown'],dict(name='Mod effect',source_label='',health={},modifiers=[],details=[]))

    def test_healing_damage_and_swarm_mechanics_from_game_catalog(self):
        root=Path(__file__).resolve().parents[1]/'assets'
        index=json.loads((root/'effect-texts.json').read_text(encoding='utf-8'))
        for key,heal in [('wh_main_unit_passive_regeneration',.001),('wh_dlc04_unit_passive_the_reliquary_binding',.0005),
                         ('wh_main_lore_passive_the_curse_of_undeath',.001),('wh_main_lord_passive_the_hunger',.001)]:
            self.assertEqual(index['phases'][key]['health']['heal_fraction'],heal)
            self.assertEqual(index['phases'][key]['health']['interval_s'],1)
            self.assertNotIn('description',index['phases'][key])
        mortis=index['phases']['wh_dlc04_unit_passive_the_reliquary_corruption']['health']
        self.assertEqual((mortis['damage'],mortis['max_entities'],mortis['interval_s']),(8,4,1))
        swarm=index['phases']['wh_main_hero_passive_swarm_of_flies']
        self.assertIn(dict(label='Melee Attack',how='add',value=-5.),swarm['modifiers'])

    def test_game_text_references_and_formatting_become_plain_text(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        from package_effect_texts import plain_text
        loc={'base':'[[col:red]]Poison![[/col]]','nested':'{{tr:base}}','loop':'{{tr:loop}}'}
        self.assertEqual(plain_text('{{tr:nested}}\\n[[img:icon]][[/img]]Speed &amp; strength',loc),'Poison!\nSpeed & strength')
        self.assertEqual(plain_text('{{tr:loop}}',loc),'')

    def test_winds_effects_preserve_game_recharge_and_reserve_units(self):
        from report_assets import effect_texts_for
        root=Path(__file__).resolve().parents[1]/'assets'
        keys=['wh_main_character_abilities_arcane_conduit',
              'wh2_main_character_passive_grand_arcane_conduit',
              'wh2_main_spell_dark_magic_power_of_darkness',
              'wh2_main_item_passive_supreme_spellshield']
        entries=effect_texts_for([dict(effect_timeline=dict(effects=[dict(key=k) for k in keys]))],root)
        self.assertIn(dict(label='Winds of Magic recharge',how='add',value=40.,unit='%'),entries[keys[0]]['modifiers'])
        self.assertIn(dict(label='Winds of Magic recharge',how='add',value=60.,unit='%'),entries[keys[1]]['modifiers'])
        self.assertIn(dict(label='Spell Mastery',how='mult',value=1.15),entries[keys[1]]['modifiers'])
        self.assertIn(dict(label='Winds of Magic reserves',how='add',value=.7,unit=' Winds/s'),entries[keys[2]]['modifiers'])
        self.assertIn(dict(label='Winds of Magic reserves',how='add',value=-.05,unit=' Winds/s'),entries[keys[3]]['modifiers'])

    def test_brief_effect_survives_numeric_history_decimation(self):
        b=Battle(max_gap=80)
        for i in range(1000):b.observe(self.frame(i,[BUFF] if i==123 else []))
        u=b.summary()['units'][0]
        self.assertLess(len(u['history']),240)
        self.assertEqual(len(u['effect_timeline']['samples']),1000)
        self.assertEqual(u['effect_timeline']['samples'][123],[123,[0]])

    def test_legacy_logs_do_not_claim_no_effects_and_live_does_not_keep_history(self):
        b=Battle();old=self.frame(0,[]);del old['units'][0]['active_effects'];b.observe(old)
        self.assertEqual(b.summary()['units'][0]['effect_timeline']['samples'],[])
        live=Battle(keep_history=False);live.observe(self.frame(0,[BUFF]))
        self.assertIsNone(live.summary()['units'][0]['effect_timeline'])

    def test_deployment_does_not_seed_effect_presence(self):
        window=CombatWindow();deployment=self.frame(0,[BUFF]);deployment['battle_phase']=4
        self.assertIsNone(window.accept(deployment))
        combat=self.frame(1,[]);combat['battle_phase']=5
        b=Battle();b.observe(window.accept(combat))
        self.assertEqual(b.summary()['units'][0]['effect_timeline']['effects'],[])

    def test_retention_limit_is_explicit_and_does_not_drop_earlier_ticks(self):
        timeline=EffectTimeline();timeline.MAX_SAMPLES=2
        for i in range(4):timeline.observe(i,[BUFF])
        summary=timeline.summary();self.assertEqual(summary['truncated_from_s'],2)
        self.assertEqual(summary['samples'],[[0,[0]],[1,[0]]])

    def test_encrypted_capture_report_preserves_full_effect_ticks(self):
        data=[self.frame(t,e) for t,e in [(0,[dict(BUFF,instance_id='a',intensity=1.5)]),(.5,None),(1.5,[]),(5.5,[DEBUFF])]]
        data[0]['effect_damage_scale']=.75
        b=Battle(max_gap=80)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'effects.wh3log';key=bytes(range(32))
            writer=LogWriter(path,key,dict(source='synthetic',maximum_interval_s=80))
            for frame in data:b.observe(frame);writer.write(frame)
            writer.close({})
            report=convert(path,key).read_text(encoding='utf-8')
            payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',report,re.S)[1])
            self.assertEqual(payload['units'][0]['effect_timeline'],b.summary()['units'][0]['effect_timeline'])
            self.assertEqual([r['sim_s'] for r in read_log(path,key) if r['kind']=='sample'],[0,.5,1.5,5.5])


if __name__=='__main__':unittest.main()
