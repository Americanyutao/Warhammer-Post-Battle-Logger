import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fixtures import BattleFixture
from aggregate import Battle
from combat_window import CombatWindow
from demo import frames
from logfile import LogWriter
from memory import ReadError
from report import convert


class CombatWindowTests(unittest.TestCase):
    def test_native_phases_and_mid_read_transition(self):
        f=BattleFixture(1,0)
        for phase in (0,4,5,6,7,8,9):
            f.memory.u(f.roster+0xc8,phase)
            self.assertEqual(f.reader.normalized(f.sample())['battle_phase'],phase)
        f.memory.u(f.roster+0xc8,4)
        def change_phase(address,size):
            if address==f.own[0]['address']+0x610:
                f.memory.u(f.roster+0xc8,5)
        f.memory.after_read=change_phase
        with self.assertRaises(ReadError):f.reader.normalized(f.sample())

    def test_baseline_only_and_combat_positions_not_deployment(self):
        gate=CombatWindow();b=Battle()
        deployment=next(frames(1,1));deployment.update(battle_phase=0,sim_s=100)
        deployment['units'][0].update(primary_ammo=90,primary_ammo_start=100,
            hp_cached=8000,hp_max_cached=8000,healing_budget_remaining_hp=6000,xyz=[-9000,-9000,-9000],flying=True)
        self.assertIsNone(gate.accept(deployment))
        deployment.update(battle_phase=4,sim_s=300)
        deployment['units'][0]['primary_ammo']=80
        self.assertIsNone(gate.accept(deployment))
        # The pending snapshot is independent of subsequent source mutation.
        deployment['units'][0]['primary_ammo']=1
        combat=next(frames(1,1));combat.update(battle_phase=5,sim_s=0)
        combat['units'][0].update(primary_ammo=75,primary_ammo_start=100,
            hp_cached=7900,hp_max_cached=8000,healing_budget_remaining_hp=6000,xyz=[10,3,20])
        first=gate.accept(combat)
        self.assertNotIn('xyz',first['deployment_baseline']['units'][0])
        b.observe(first)
        combat=copy.deepcopy(combat);combat['sim_s']=1;combat['units'][0]['xyz']=[12,4,22]
        second=gate.accept(combat);self.assertNotIn('deployment_baseline',second);b.observe(second)
        s=b.summary();u=s['units'][0]
        self.assertEqual((s['samples'],s['start_s'],s['end_s']),(2,0,1))
        self.assertEqual(s['movement_bounds'],dict(xmin=10,xmax=12,zmin=20,zmax=22))
        self.assertEqual(s['elevation_min'],3)
        self.assertEqual(u['history'][0]['xyz'],[10,3,20])
        self.assertEqual(u['state_seconds']['idle'],1)
        self.assertEqual(u['landings_observed'],0);self.assertFalse(u['ever_flying'])
        self.assertFalse(u['first']['flying'])
        self.assertEqual(u['damage_taken_estimate'],100)
        self.assertEqual(u['ammo']['primary']['initial'],80)
        self.assertEqual(u['ammo']['primary']['expended'],5)
        self.assertEqual(u['initial_values_source'],'deployment')
        self.assertEqual(u['first']['hp_cached'],8000)

    def test_wounded_deployment_seeds_healing_before_first_combat_sample(self):
        gate=CombatWindow();b=Battle()
        deployment=next(frames(1,1));deployment.update(battle_phase=4,sim_s=100)
        deployment['units'][0].update(hp_cached=6000,hp_max_cached=8000,healing_budget_remaining_hp=6000)
        self.assertIsNone(gate.accept(deployment))
        combat=copy.deepcopy(deployment);combat.update(battle_phase=5,sim_s=0)
        combat['units'][0].update(hp_cached=5500,healing_budget_remaining_hp=5500)
        b.observe(gate.accept(combat));u=b.summary()['units'][0]
        self.assertEqual(u['initial_values_source'],'deployment')
        self.assertEqual(u['damage_taken_estimate'],1000)
        self.assertEqual(u['healing_received_estimate'],500)
        self.assertEqual(u['healing_budget_remaining_calculated'],5500)
        self.assertEqual(u['damage_taken_calculation']['baseline']['hp'],6000)

    def test_unknown_results_and_missing_clock_cannot_start_capture(self):
        gate=CombatWindow();frame=next(frames(1,1))
        for phase in (None,1,8,9):
            frame['battle_phase']=phase;self.assertIsNone(gate.accept(frame))
        frame.update(battle_phase=5,sim_s=None);self.assertIsNone(gate.accept(frame))
        frame['sim_s']=10;self.assertIsNotNone(gate.accept(frame))
        self.assertNotIn('deployment_baseline',frame)
        for phase in (None,6,7,8):
            frame['battle_phase']=phase;self.assertIsNotNone(gate.accept(frame))

    def test_results_retained_and_baseline_survives_encrypted_conversion(self):
        gate=CombatWindow();deployment=next(frames(1,1));deployment['battle_phase']=4
        deployment['units'][0].update(models=100,primary_ammo=90)
        self.assertIsNone(gate.accept(deployment))
        combat=next(frames(1,1));combat.update(battle_phase=5,sim_s=1)
        combat['units'][0].update(models=95,primary_ammo=80)
        records=[gate.accept(combat)]
        result=copy.deepcopy(combat);result.update(battle_phase=8,sim_s=2,battle_result=dict(outcome='Victory'))
        records.append(gate.accept(result))
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'boundary.wh3log';key=bytes(range(32))
            writer=LogWriter(source,key,dict(source='synthetic'));live=Battle()
            for frame in records:writer.write(frame);live.observe(frame)
            writer.close({})
            with patch('report.write_report') as write:convert(source,key)
            offline=write.call_args.args[1]
        self.assertEqual(offline['units'],live.summary()['units'])
        self.assertEqual(offline['units'][0]['initial_models_observed'],100)
        self.assertEqual(offline['units'][0]['ammo']['primary']['initial'],90)
        self.assertEqual(offline['battle_result']['outcome'],'Victory')
        self.assertEqual(len(offline['units'][0]['history']),2)

    def test_baselines_match_full_unit_identity_and_do_not_seed_summons(self):
        gate=CombatWindow();deployment=next(frames(1,1));deployment['battle_phase']=4
        deployment['units'][0].update(primary_ammo=100)
        gate.accept(deployment)
        combat=next(frames(1,1));combat['battle_phase']=5
        combat['units'][0].update(id='new-incarnation',spawned=True,primary_ammo=20)
        b=Battle();b.observe(gate.accept(combat));u=b.summary()['units'][0]
        self.assertEqual(u['initial_values_source'],'first_combat_observation')
        self.assertEqual(u['ammo']['primary']['initial'],20)

    def test_cancelled_deployment_creates_no_capture_or_stale_baseline(self):
        import queue
        from types import SimpleNamespace
        from worker import Worker
        from fixtures import PROFILE
        deployment=next(frames(1,1));deployment.update(battle_phase=4,sim_s=100)
        deployment['units'][0]['primary_ammo']=100
        result=next(frames(1,1));result['battle_phase']=8
        combat=next(frames(1,1));combat.update(battle_phase=5,sim_s=0)
        combat['units'][0]['primary_ammo']=20
        sequence=iter([(1,deployment),(None,None),(2,result),(None,None),(3,combat),(3,combat),(None,None)])
        project=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=project/'build') as temp:
            worker=Worker(temp,queue.Queue(1));worker.interval=.001
            class Reader:
                def __init__(self,*args):self.frame=None
                def sample(self):
                    if worker.late_start_request:worker.answer_late_start(worker.late_start_request,True)
                    # Neither deployment nor results-only sessions may open a file.
                    if self.frame is deployment or self.frame is result:
                        self_test.assertEqual(len(worker.recorders),0)
                    try:token,self.frame=next(sequence)
                    except StopIteration:
                        worker.stop_event.set();token,self.frame=None,None
                    return SimpleNamespace(token=(token,) if token else None,controller=1)
                def normalized(self,sample):return copy.deepcopy(self.frame)
            class Memory:
                def __init__(self,*args):self.calls=self.bytes_read=0;self.pid=1
                def alive(self):return True
                def close(self):pass
            self_test=self
            with patch('worker.WindowsAPI') as api,patch('worker.ProcessMemory',Memory),patch('worker.LoggerReader',Reader),patch('worker.load_profiles',return_value=[PROFILE]),patch('worker.select_profile',return_value=PROFILE):
                api.return_value.game_pids.return_value=[1];api.return_value.game_module.return_value={}
                worker.start();worker.join(10)
            self.assertFalse(worker.is_alive());self.assertEqual(len(worker.recorders),1)
            self.assertIsNone(worker.recorders[0].error)
            unit=worker.battle.summary()['units'][0]
            self.assertEqual(unit['ammo']['primary']['initial'],20)
            self.assertEqual(unit['initial_values_source'],'first_combat_observation')


if __name__=='__main__':unittest.main()
