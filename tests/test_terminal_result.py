import unittest
from terminal_result import resolve
from aggregate import Battle
import copy
from fixtures import BattleFixture

class TerminalResultTests(unittest.TestCase):
    def unit(self, **changes):
        u=dict(alive=False,left_battlefield=True,result_hp=350,result_models=13,
               result_initial_hp=8000,result_initial_models=120,result_exit_reason=2)
        u.update(changes)
        return u

    def confirmed(self,u):
        result,candidate=resolve(u,None,1)
        self.assertIsNone(result)
        return resolve(u,candidate,2)[0]

    def test_retreat_preserves_partial_model_health(self):
        result=self.confirmed(self.unit())
        self.assertEqual((result['status'],result['hp'],result['models']),('Retreated',350,13))

    def test_routed_unit_killed_is_dead(self):
        for reason in (0,3):
            result=self.confirmed(self.unit(result_hp=0,result_models=0,result_exit_reason=reason,routing=True))
            self.assertEqual((result['status'],result['hp'],result['models']),('Dead',0,0))

    def test_uninitialized_inconsistent_active_and_unknown_stay_unresolved(self):
        for change in [dict(result_initial_hp=0),dict(result_models=121),dict(result_hp=None),
                       dict(result_hp=0),dict(result_exit_reason=5),dict(result_exit_reason=4),
                       dict(result_exit_reason=0),dict(alive=True),dict(left_battlefield=False)]:
            self.assertIsNone(self.confirmed(self.unit(**change)),change)

    def test_paused_or_changing_result_not_confirmed(self):
        u=self.unit();_,pending=resolve(u,None,1)
        self.assertIsNone(resolve(u,pending,1)[0])
        self.assertIsNone(resolve(self.unit(result_hp=349),pending,2)[0])

    def test_result_fields_survive_inactive_ui_cache(self):
        f=BattleFixture(1,0);u=f.own[0];m=f.memory
        for offset,value in [(0xb4,350),(0xa0,13),(0xb0,8000),(0x9c,120),(0xe4,2)]:
            m.u(u['result']+offset,value)
        m.write(u['result']+0xe2,b'\x01');m.write(u['address']+0x6fb,b'\x00')
        v=f.reader.normalized(f.sample())['units'][0]
        self.assertEqual((v['result_hp'],v['result_models'],v['result_exit_reason']),(350,13,2))
        self.assertIsNone(v['hp_cached'])

    def test_aggregation_uses_final_hp_without_overwriting_raw_cache(self):
        f=BattleFixture(1,0);frame=f.reader.normalized(f.sample());b=Battle()
        frame['sim_s']=0;b.observe(frame)
        for t in (1,2):
            end=copy.deepcopy(frame);end['sim_s']=t
            end['units'][0].update(self.unit(),hp_cached=None,models=None)
            b.observe(end)
        u=b.summary()['units'][0]
        self.assertEqual(u['final_status'],'Retreated')
        self.assertEqual(u['terminal_result']['hp'],350)
        self.assertIsNone(u['last']['hp_cached'])
        self.assertEqual(u['history'][-1]['resolved_hp'],350)
        self.assertEqual(u['history'][-1]['resolved_models'],13)
        self.assertNotIn('_terminal_candidate',u)

    def test_gap_requires_new_confirmation(self):
        f=BattleFixture(1,0);frame=f.reader.normalized(f.sample());b=Battle()
        frame['units'][0].update(self.unit())
        for t in (0,10):
            frame['sim_s']=t;b.observe(frame)
        self.assertIsNone(b.summary()['units'][0]['terminal_result'])
        frame['sim_s']=11;b.observe(frame)
        self.assertEqual(b.summary()['units'][0]['final_status'],'Retreated')

    def test_results_screen_confirms_at_frozen_battle_time(self):
        # Real rev16 capture: death fields are incomplete during combat; the
        # final models arrive in phase8, and both results samples have equal t.
        f=BattleFixture(1,0);frame=f.reader.normalized(f.sample());b=Battle()
        frame.update(sim_s=250.,battle_phase=5)
        frame['units'][0].update(self.unit(result_hp=0,result_models=120,result_exit_reason=0))
        b.observe(frame);self.assertIsNone(b.summary()['units'][0]['terminal_result'])
        for _ in range(2):
            final=copy.deepcopy(frame);final.update(sim_s=255.30638122558594,battle_phase=8)
            final['units'][0].update(result_models=0)
            b.observe(final)
            unit=b.summary()['units'][0]
            self.assertEqual(unit['final_status'],'Dead')
            self.assertEqual((unit['terminal_result']['hp'],unit['terminal_result']['models']),(0,0))

    def test_single_saved_results_tick_confirms_retreat(self):
        f=BattleFixture(1,0);frame=f.reader.normalized(f.sample());b=Battle()
        frame.update(sim_s=505.0216064453125,battle_phase=8)
        frame['units'][0].update(self.unit(),hp_cached=None,models=None)
        b.observe(frame);unit=b.summary()['units'][0]
        self.assertEqual(unit['final_status'],'Retreated')
        self.assertEqual((unit['terminal_result']['hp'],unit['terminal_result']['models']),(350,13))

    def test_results_phase_still_rejects_unpopulated_or_contradictory_records(self):
        for change in [dict(result_initial_hp=0),dict(result_initial_models=0),dict(result_models=121),
                       dict(result_hp=None),dict(result_hp=0),dict(result_exit_reason=5),
                       dict(result_exit_reason=4),dict(result_exit_reason=0),dict(alive=True),dict(left_battlefield=False)]:
            self.assertIsNone(resolve(self.unit(**change),None,10,results_phase=True)[0],change)

    def test_paused_combat_does_not_use_results_confirmation(self):
        f=BattleFixture(1,0);frame=f.reader.normalized(f.sample());b=Battle()
        frame.update(sim_s=250.,battle_phase=5);frame['units'][0].update(self.unit())
        for _ in range(3):b.observe(frame)
        self.assertIsNone(b.summary()['units'][0]['terminal_result'])
