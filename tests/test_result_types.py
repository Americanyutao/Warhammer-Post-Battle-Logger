import copy
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fixtures import BattleFixture
from aggregate import Battle
from demo import frames
from logfile import LogWriter,read_log
from report import convert
from result_types import TYPES


def setup(code=1,key='decisive_victory',outcome='Victory'):
    f=BattleFixture(1,0);m=f.memory
    result=m.allocate(0x40);m.q(f.roster+0xa0,result)
    entries=m.allocate(0xc0);m.q(result+0x30,entries)
    local=m.allocate(16);m.q(f.context+0x3a8,local);m.u(f.context+0x3b4,0);m.u(local+4,1)
    # Local native alliance 1 is not the local-player array index 0.
    m.u(result+4,0xffffffff if outcome=='Draw' else 1 if outcome=='Victory' else 0)
    record=m.allocate(0x30);m.q(record+0x10,0x1234)  # Opaque interned key, never dereferenced.
    record_code=next((c for c,item in TYPES.items() if item[0]==key),11)
    m.u(record+0x18,record_code)
    m.u(entries+0x60+0x4c,code);m.q(entries+0x60+0x58,record)
    m.u(f.roster+0xc8,8)
    return f,result,entries,record


class ResultTypeTests(unittest.TestCase):
    def test_all_native_ordinary_result_types_use_the_local_alliance(self):
        for code,(key,outcome,label) in TYPES.items():
            with self.subTest(code=code):
                f,_,_,_=setup(code,key,outcome)
                r=f.reader.normalized(f.sample())['battle_result']
                self.assertEqual(r['outcome'],outcome)
                self.assertEqual(r['result_type_code'],code)
                self.assertEqual(r['result_type_key'],key)
                self.assertEqual(r['result_type_label'],label)
                self.assertTrue(r['result_type_confirmed'])

    def test_incomplete_unknown_or_conflicting_classification_keeps_overall_winner(self):
        for code,key,outcome in [(0,'','Victory'),(99,'unknown','Victory'),
            (9,'successful_challenge','Victory'),(1,'pyrrhic_victory','Victory'),
            (1,'decisive_victory','Defeat')]:
            with self.subTest(code=code,key=key,outcome=outcome):
                f,_,_,_=setup(code,key,outcome)
                r=f.reader.normalized(f.sample())['battle_result']
                self.assertEqual(r['outcome'],outcome);self.assertEqual(r['result_type_code'],code)
                self.assertFalse(r['result_type_confirmed']);self.assertIsNone(r['result_type_label'])
        f,result,entries,_=setup();f.memory.q(entries+0x60+0x58,0)
        r=f.reader.normalized(f.sample())['battle_result']
        self.assertFalse(r['result_type_confirmed']);self.assertEqual(r['outcome'],'Victory')
        f.memory.q(result+0x30,0)
        r=f.reader.normalized(f.sample())['battle_result']
        self.assertEqual(r['outcome'],'Victory');self.assertIsNone(r['result_type_code'])

    def test_changed_classification_is_not_confirmed_and_changed_winner_is_retried(self):
        for target in ('type','winner'):
            f,result,entries,record=setup();m=f.memory
            def change(address,size):
                if address==record+0x18:
                    m.u(entries+0x60+0x4c,3) if target=='type' else m.u(result+4,0)
            m.after_read=change
            r=f.reader.normalized(f.sample())['battle_result']
            if target=='winner':self.assertIsNone(r)
            else:self.assertFalse(r['result_type_confirmed'])

    def test_classification_is_not_read_before_results(self):
        f,_,_,record=setup();f.memory.u(f.roster+0xc8,5);seen=[]
        f.memory.after_read=lambda address,size:seen.append(address)
        self.assertIsNone(f.reader.normalized(f.sample())['battle_result'])
        self.assertNotIn(record+0x18,seen)

    def test_raw_flag_survives_encryption_and_report_keeps_last_confirmed_classification(self):
        f,_,_,_=setup();result=f.reader.normalized(f.sample())['battle_result']
        first=next(frames(1,1));first['battle_result']=result
        last=copy.deepcopy(first);last['sim_s']=1
        last['battle_result']=dict(outcome='Victory',result_type_code=1,result_type_confirmed=False)
        b=Battle()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'typed.wh3log';key=bytes(range(32));writer=LogWriter(path,key,dict(source='synthetic'))
            for frame in (first,last):b.observe(frame);writer.write(frame)
            writer.close({})
            self.assertEqual(list(read_log(path,key))[1]['battle_result']['result_type_code'],1)
            with patch('report.write_report') as write:convert(path,key)
            self.assertEqual(write.call_args.args[1]['battle_result'],b.summary()['battle_result'])
        self.assertEqual(b.summary()['battle_result']['result_type_label'],'Decisive Victory')
        last['sim_s']=2;last['battle_result']=dict(outcome='Defeat');b.observe(last)
        self.assertEqual(b.summary()['battle_result']['outcome'],'Defeat')


if __name__=='__main__':unittest.main()
