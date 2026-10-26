import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from recorder import Recorder
from logfile import read_log
from demo import frames
from report_assets import effect_texts_for,assets_for,index_at


class ReportPolishTests(unittest.TestCase):
    def test_staged_effects_include_their_parent_names(self):
        keys=['wh3_dlc29_item_passive_blood_dragon_standard:wh3_dlc29_item_passive_blood_dragon_standard',
              'wh2_dlc10_lord_passive_blood_frenzy:wh2_dlc10_lord_passive_blood_frenzy_1']
        units=[dict(effect_timeline=dict(effects=[dict(key=k) for k in keys]))]
        result=effect_texts_for(units,P/'assets')
        self.assertEqual(result[keys[0]]['name'],'Blood Dragon Standard \u2014 Stage One')
        self.assertEqual(result[keys[1]]['name'],'Blood Frenzy \u2014 Stage One')
        catalog=index_at(P/'assets/effect-texts.json')
        effects=[]
        for phase,definition in catalog['phases'].items():
            if definition.get('name') not in ['Stage One','Stage Two','Stage Three','Stage Four']:continue
            for ability in definition.get('ability_keys',[]):
                name=catalog['abilities'].get(ability,{}).get('name')
                if name:effects.append(dict(key=ability+':'+phase))
        self.assertGreater(len(effects),20)
        result=effect_texts_for([dict(effect_timeline=dict(effects=effects))],P/'assets')
        for effect in effects:self.assertIn(' \u2014 Stage ',result[effect['key']]['name'])
        for key in ['wh2_dlc10_quest_passive_primal_rampage_ii_hidden','wh3_dlc24_unit_abilities_tide_of_transformation_2']:
            effect=dict(key=key+':'+key)
            text=effect_texts_for([dict(effect_timeline=dict(effects=[effect]))],P/'assets')[effect['key']]['name']
            self.assertIn(' \u2014 Stage ',text)

    def test_race_labels_use_verified_unit_types(self):
        unit=dict(id='test',name='Archers',side='Allied',army='1',first={},last=dict(unit_key='wh2_main_hef_inf_archers_0'))
        result=assets_for([unit],icons=False)
        self.assertEqual(result['unit_info']['test']['culture'],'hef')
        self.assertEqual(result['race_names']['names']['hef'],'High Elves')

    def test_paused_samples_coalesce_latest_without_losing_baseline_or_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.wh3log';key=bytes(range(32))
            r=Recorder(path,key,{})
            f=next(frames(1,1));f['deployment_baseline']=dict(sim_s=0,units=copy.deepcopy(f['units']))
            f['battle_result']=dict(outcome='Victory',result_type_confirmed=True)
            first=copy.deepcopy(f)
            self.assertTrue(r.submit(f))
            for i in range(3):
                f=copy.deepcopy(f);f.pop('deployment_baseline',None);f['units'][0]['hp_cached']=7000+i
                f['battle_result']=dict(outcome='Victory',result_type_confirmed=False)
                self.assertTrue(r.submit(f))
            next_frame=copy.deepcopy(f);next_frame['sim_s']=1
            self.assertTrue(r.submit(next_frame));r.finish({});r.join(10)
            self.assertIsNone(r.error)
            records=list(read_log(path,key));samples=[x for x in records if x['kind']=='sample']
            self.assertEqual([s['sim_s'] for s in samples],[0,1])
            self.assertEqual(samples[0]['units'][0]['hp_cached'],7002)
            self.assertEqual(samples[0]['deployment_baseline'],first['deployment_baseline'])
            self.assertTrue(samples[0]['battle_result']['result_type_confirmed'])
            self.assertEqual(records[-1]['summary']['paused_samples_coalesced'],3)

    def test_same_timestamp_gap_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'test.wh3log';key=bytes(range(32));r=Recorder(path,key,{})
            f=next(frames(1,1));r.submit(f)
            f=copy.deepcopy(f);f['gap_before']=dict(dropped_records=2);r.submit(f)
            f=copy.deepcopy(f);f.pop('gap_before');r.submit(f)
            r.finish({});r.join(10);self.assertIsNone(r.error)
            samples=[x for x in read_log(path,key) if x['kind']=='sample']
            self.assertEqual(len(samples),2)
            self.assertEqual(samples[1]['gap_before'],dict(dropped_records=2))
