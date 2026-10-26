import copy
import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
from fixtures import BattleFixture
from aggregate import Battle
from demo import frames
from logfile import LogWriter
from report import convert
from statline import StatlineTimeline
from statline_reader import game_round


def install_statline(f,rules=()):
    m=f.memory;u=f.own[0]['address'];cache=m.allocate(0x308)
    m.q(u+0x1b0,cache)
    values={3:15,26:5,24:60,16:75,20:50,27:0,17:200,18:210,9:35,55:1,12:20,13:10,11:0,15:-20,14:15,10:5}
    for i,value in values.items():m.write(cache+0x68+i*12,struct.pack('<fff',value,0,-1000 if i in (15,24) else 0))
    record=m.allocate(0x510);land=m.allocate(0x190);entity=m.allocate(0x30)
    m.q(u+0x168,record);m.q(record+0x500,land);m.q(land+0x108,entity)
    m.write(entity+0x20,struct.pack('<ff',5,10))
    difficulty=m.allocate(0x38);m.q(f.my_army+0x38,difficulty);m.write(difficulty+0x34,struct.pack('<f',1.))
    override=f.reader.g['statline_database_override'];m.at(override,8)
    context=m.allocate(0x368);database=m.allocate(0x19d87);table=m.allocate(0x20)
    m.q(override,context);m.q(context+0x360,database);m.write(database+0x19d86,b'\1');m.q(database+0x14078,table)
    rows=[]
    for state,stat,value in rules:
        row=m.allocate(0x28);key=m.allocate(0x10);m.u(key+8,stat)
        m.write(row+0x18,struct.pack('<fiQ',value,state,key));rows.append(row)
    m.vector(table,0xc,0x10,rows)
    return dict(cache=cache,record=record,land=land,entity=entity,difficulty=difficulty,database=database,table=table)


class NativeStatlineTests(unittest.TestCase):
    def read(self,f):return f.reader.normalized(f.sample())['units'][0]['statline']

    def test_card_stats_resistances_speed_and_shields(self):
        f=BattleFixture(1,0);install_statline(f);v=self.read(f)
        self.assertEqual({k:v[k] for k in ('hp','hp_max','models','armour','leadership','speed','melee_attack','melee_defence','weapon_strength','charge_bonus')},
            dict(hp=7500,hp_max=8000,models=115,armour=20,leadership=60,speed=50,melee_attack=75,melee_defence=50,weapon_strength=410,charge_bonus=35))
        self.assertEqual([v[k] for k in ('spell_resistance','missile_resistance','fire_resistance','fire_weakness','physical_resistance','ward_save')],[20,10,0,20,15,5])

    def test_native_fatigue_and_difficulty_display_order(self):
        f=BattleFixture(1,0);a=install_statline(f,[(4,3,.9),(4,16,.75),(4,55,.85),(4,73,.9)])
        f.memory.u(f.own[0]['address']+0x6e4,4);f.memory.write(a['difficulty']+0x34,struct.pack('<f',1.2))
        v=self.read(f)
        self.assertAlmostEqual(v['armour'],18,places=5);self.assertEqual(v['melee_attack'],67)
        self.assertAlmostEqual(v['speed'],42.5,places=5);self.assertEqual(v['weapon_strength'],443)
        self.assertEqual(v['charge_bonus'],42);self.assertEqual(v['melee_defence'],60)

    def test_fatigue_immunity_and_flying_or_mounted_speed(self):
        f=BattleFixture(1,0);a=install_statline(f,[(4,16,.5)])
        f.memory.u(f.own[0]['address']+0x6e4,4)
        f.memory.q(a['cache']+0x30,1<<16)  # Attribute80: ignore melee-attack fatigue.
        f.memory.q(a['cache']+0x28,1<<32)
        v=self.read(f);self.assertEqual(v['melee_attack'],75);self.assertEqual(v['speed'],100)
        mount=f.memory.allocate(0x30);entity=f.memory.allocate(0x30)
        f.memory.q(a['land']+0x110,mount);f.memory.q(mount+0x28,entity);f.memory.write(entity+0x20,struct.pack('<ff',6,12))
        self.assertEqual(self.read(f)['speed'],120)

    def test_unbreakable_and_displayed_leadership_floor(self):
        f=BattleFixture(1,0);a=install_statline(f)
        f.memory.write(a['cache']+0x68+24*12,struct.pack('<fff',-100,0,-1000))
        self.assertEqual(self.read(f)['leadership'],-55)
        f.memory.write(f.own[0]['address']+0x727,b'\1')
        self.assertEqual(self.read(f)['leadership'],100)
        self.assertEqual(f.reader.normalized(f.sample())['units'][0]['leadership'],65)

    def test_unavailable_rules_fields_and_inactive_ticks_are_not_zero(self):
        f=BattleFixture(1,0);a=install_statline(f)
        f.memory.write(a['database']+0x19d86,b'\0');v=self.read(f)
        self.assertEqual(v['hp'],7500);self.assertIsNone(v['melee_attack'])
        f.memory.write(a['database']+0x19d86,b'\1')
        f.memory.write(a['cache']+0x68+16*12,struct.pack('<f',float('nan')))
        self.assertIsNone(self.read(f)['melee_attack']);self.assertEqual(self.read(f)['armour'],20)
        f.memory.write(f.own[0]['address']+0x6fb,b'\0');self.assertIsNone(self.read(f))

    def test_changed_cache_read_is_unknown(self):
        f=BattleFixture(1,0);a=install_statline(f)
        def change(address,size):
            if address==a['cache']:f.memory.write(a['cache']+0x68+16*12,struct.pack('<f',99))
        f.memory.after_read=change;self.assertIsNone(self.read(f))

    def test_native_rounding_uses_half_away_from_zero(self):
        self.assertEqual([game_round(x) for x in (-2.5,-.5,0,.5,2.5)],[-3,-1,0,1,3])


class StatlineTimelineTests(unittest.TestCase):
    def frame(self,t,values):
        f=next(frames(1,1));f['sim_s']=t;f['units'][0]['statline']=values;return f

    def test_deployment_initial_line_at_zero_preserves_recorded_combat_time(self):
        initial=self.frame(5,dict(armour=15,melee_attack=75,hp=6000,hp_max=8000))
        first=self.frame(6.25,dict(armour=45,melee_attack=95,hp=5900,hp_max=8000))
        first['battle_clock']=dict(source='native_battle_ui_clock',elapsed_s=6.25,limit_s=3600,remaining_s=3593.75)
        first['deployment_baseline']=dict(sim_s=5,battle_clock=dict(elapsed_s=5,limit_s=3600,remaining_s=3595),units=initial['units'])
        b=Battle();b.observe(first);b.observe(self.frame(7.5,dict(armour=5,melee_attack=60)))
        timeline=b.summary()['units'][0]['statline_timeline']
        self.assertEqual([p['t'] for p in timeline['samples']],[0,1.25,2.5])
        self.assertEqual(timeline['baseline']['source'],'deployment')
        self.assertEqual(timeline['baseline']['values']['armour'],15)
        self.assertEqual(timeline['samples'][1]['values']['armour'],45)
        self.assertEqual(timeline['samples'][0]['values']['hp'],6000)
        self.assertIsNone(timeline['baseline']['values']['speed'])
        # These snapshots do not add deployment activity or a combat sample.
        self.assertEqual(b.summary()['samples'],2)
        self.assertEqual(b.summary()['units'][0]['history'][0]['t'],1.25)

    def test_late_start_and_unknown_initial_never_fabricate_a_zero_sample(self):
        t=StatlineTimeline(dict(armour=float('nan'),hp=None))
        t.observe(60,None);t.observe(61,dict(armour=75));t.observe(62,dict(armour=95,speed=50))
        s=t.summary();self.assertEqual([p['t'] for p in s['samples']],[60,61,62])
        self.assertEqual((s['baseline']['t'],s['baseline']['source']),(61,'first_sample'))
        self.assertEqual(s['baseline']['values']['armour'],75)
        self.assertIsNone(s['baseline']['values']['speed'])

    def test_paused_first_available_sample_is_refined_then_frozen(self):
        t=StatlineTimeline();t.observe(0,None);t.observe(1,dict(armour=15))
        t.observe(1,dict(armour=20));t.observe(2,dict(armour=45))
        self.assertEqual(t.summary()['baseline']['values']['armour'],20)
        self.assertEqual(len(t.samples),3)
        t=StatlineTimeline(dict(armour=15));t.observe(0,dict(armour=45))
        self.assertEqual(t.summary()['baseline']['values']['armour'],15)

    def test_gaps_and_partial_fields_do_not_reset_or_patch_the_baseline(self):
        b=Battle();b.observe(self.frame(60,dict(armour=45)))
        gap=self.frame(90,dict(armour=15,speed=50));gap['gap_before']={'dropped_records':1};b.observe(gap)
        s=b.summary()['units'][0]['statline_timeline']
        self.assertEqual(s['baseline']['t'],60);self.assertEqual(s['baseline']['values']['armour'],45)
        self.assertIsNone(s['baseline']['values']['speed'])
        s['baseline']['values']['armour']=999
        self.assertEqual(b.summary()['units'][0]['statline_timeline']['baseline']['values']['armour'],45)

    def test_per_tick_health_state_and_budget_survive_capture_conversion(self):
        b=Battle();f=self.frame(0,dict(hp=6000,hp_max=8000,models=30,models_max=32,armour=15))
        f['units'][0].update(healing_budget_remaining_hp=4500,healing_budget_unlimited=False,routing=True)
        b.observe(f)
        first=b.summary()['units'][0]['statline_timeline']['samples'][0]
        self.assertEqual(first['values']['healing_budget_remaining_hp'],4500)
        self.assertTrue(first['state']['routing']);self.assertFalse(first['state']['healing_budget_unlimited'])
        last=self.frame(1,None);last['battle_phase']=8
        last['units'][0].update(alive=False,left_battlefield=True,result_hp=0,result_models=0,result_initial_hp=8000,result_initial_models=32,result_exit_reason=3,healing_budget_remaining_hp=3000)
        b.observe(last);point=b.summary()['units'][0]['statline_timeline']['samples'][-1]
        self.assertEqual(point['state']['terminal_status'],'Dead')
        self.assertEqual(point['state']['healing_budget_remaining_hp'],3000)
        self.assertIsNone(point['values'])

    def test_all_ticks_survive_decimation_pause_speed_gap_and_unknown(self):
        b=Battle(max_gap=80)
        for i in range(1000):b.observe(self.frame(i*4,dict(hp=8000-i,armour=15 if i!=123 else 45)))
        b.observe(self.frame(3996,dict(hp=7000,armour=90)))
        f=self.frame(4000,None);f['gap_before']={'dropped_records':1};b.observe(f)
        missing=self.frame(4004,{});missing['units']=[];b.observe(missing)
        u=b.summary()['units'][0];p=u['statline_timeline']['samples']
        self.assertLess(len(u['history']),240);self.assertEqual(len(p),1002)
        self.assertEqual(p[123]['t'],492);self.assertEqual(p[123]['values']['armour'],45)
        self.assertEqual(p[999]['values']['armour'],90);self.assertIsNone(p[1000]['values']);self.assertIsNone(p[1001]['values'])
        self.assertNotEqual(p[999]['segment'],p[1000]['segment'])

    def test_legacy_and_live_do_not_invent_history(self):
        f=next(frames(1,1));f['units'][0].pop('statline',None);b=Battle();b.observe(f)
        self.assertEqual(b.summary()['units'][0]['statline_timeline']['samples'],[])
        live=Battle(keep_history=False);live.observe(self.frame(0,dict(armour=15)))
        self.assertIsNone(live.summary()['units'][0]['statline_timeline'])

    def test_retention_bound_and_nonfinite_values(self):
        t=StatlineTimeline();t.MAX_SAMPLES=1;t.observe(0,dict(armour=float('nan'),hp=0));t.observe(4,{})
        self.assertIsNone(t.summary()['samples'][0]['values']['armour']);self.assertEqual(t.summary()['samples'][0]['values']['hp'],0)
        self.assertEqual(t.summary()['truncated_from_s'],4)

    def test_encrypted_report_roundtrip_and_original_stat_icon_order(self):
        b=Battle(max_gap=80)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'statline.wh3log';key=bytes(range(32));w=LogWriter(p,key,dict(source='synthetic',maximum_interval_s=80))
            for f in [self.frame(0,dict(armour=15)),self.frame(4,dict(armour=45)),self.frame(8,None)]:b.observe(f);w.write(f)
            w.close({});html=convert(p,key).read_text(encoding='utf-8')
            data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S)[1])
            self.assertEqual(data['units'][0]['statline_timeline'],b.summary()['units'][0]['statline_timeline'])
            self.assertEqual(data['units'][0]['activity_timeline'],b.summary()['units'][0]['activity_timeline'])
            self.assertEqual([r['key'] for r in data['assets']['statline']['rows']],['hp','models','armour','leadership','speed','melee_attack','melee_defence','weapon_strength','charge_bonus','spell_resistance','missile_resistance','fire_resistance','physical_resistance','ward_save'])
            self.assertTrue(all('statline:'+r['key'] in data['assets']['stats'] for r in data['assets']['statline']['rows']))


if __name__=='__main__':unittest.main()
