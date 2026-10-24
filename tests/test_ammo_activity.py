import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import unittest
from aggregate import Battle
from demo import frames

class AmmoActivityTests(unittest.TestCase):
    def test_ammo_expended_keeps_pool_scale_despite_casualties(self):
        fs=list(frames(1,2));b=Battle()
        for f,(models,ammo,secondary) in zip(fs,[(60,1080,12),(58,1021,10),(30,694,3)]):
            f['units'][0].update(models=models,primary_ammo=ammo,secondary_ammo=secondary)
            b.observe(f)
        u=b.summary()['units'][0]
        self.assertEqual((u['ammo']['primary']['initial'],u['ammo']['primary']['expended']),(1080,386))
        self.assertEqual(u['ammo']['secondary']['expended'],9)
        self.assertEqual(u['history'][-1]['primary_ammo_expended'],386)
        for key in ('distance_sampled','first_engagement','observed_model_losses','observed_model_rises'):
            self.assertNotIn(key,u)

    def test_missing_pool_does_not_become_zero_or_reset_initial(self):
        fs=list(frames(1,2));b=Battle()
        for f,ammo in zip(fs,[1080,694,None]):
            f['units'][0]['primary_ammo']=ammo;b.observe(f)
        u=b.summary()['units'][0]
        self.assertEqual(u['ammo']['primary']['expended'],386)
        self.assertEqual(u['ammo']['primary']['final_s'],1)
        self.assertIsNone(u['history'][-1]['primary_ammo_expended'])

    def test_replenishment_is_net_and_never_negative_fired(self):
        fs=list(frames(1,2));b=Battle()
        for f,ammo in zip(fs,[100,70,110]):
            f['units'][0]['primary_ammo']=ammo;b.observe(f)
        a=b.summary()['units'][0]['ammo']['primary']
        self.assertTrue(a['increase_observed']);self.assertIsNone(a['expended'])

    def test_retreat_union_does_not_double_count_overlap(self):
        fs=list(frames(1,3));b=Battle()
        for f in fs:
            f['units'][0].update(routing=True,shattered=True,withdrawing=True,firing=True,under_missile=True)
            b.observe(f)
        u=b.summary()['units'][0]
        self.assertEqual(u['state_seconds']['retreating_combined'],3)
        self.assertEqual(u['state_seconds']['under_missile'],3)
        self.assertEqual(u['state_seconds']['firing'],3)

    def test_unknown_retreat_state_does_not_prove_zero_time(self):
        fs=list(frames(1,1));b=Battle()
        for f in fs:
            f['units'][0].update(routing=False,shattered=None,withdrawing=False);b.observe(f)
        self.assertEqual(b.summary()['units'][0]['state_observed_seconds']['retreating_combined'],0)

    def test_death_flight_flag_clear_is_not_landing(self):
        fs=list(frames(1,1));b=Battle();fs[0]['units'][0]['flying']=True
        fs[1]['units'][0].update(flying=False,alive=False)
        for f in fs:b.observe(f)
        self.assertEqual(b.summary()['units'][0]['landings_observed'],0)

    def test_native_start_recovers_firing_before_first_sample(self):
        f=next(frames(1,1));f['units'][0].update(primary_ammo=694,primary_ammo_start=1080)
        b=Battle();b.observe(f);a=b.summary()['units'][0]['ammo']['primary']
        self.assertEqual(a['initial'],1080);self.assertEqual(a['expended'],386)
        self.assertEqual(a['initial_source'],'native_start')

    def test_native_reader_uses_existing_pool_start_slots(self):
        from fixtures import BattleFixture
        f=BattleFixture(1,0);u=f.own[0];m=f.memory
        m.u(u['adapter']+0x3d94,1080);m.u(u['adapter']+0x3da4,12)
        v=f.reader.normalized(f.sample())['units'][0]
        self.assertEqual((v['primary_ammo_start'],v['secondary_ammo_start']),(1080,12))

    def test_brief_flight_is_retained_after_timeline_downsampling(self):
        b=Battle()
        for i,f in enumerate(frames(1,600)):
            f['units'][0]['flying']=i==2
            b.observe(f)
        u=b.summary()['units'][0]
        self.assertTrue(u['ever_flying'])
        self.assertFalse(u['last']['flying'])
        self.assertEqual(u['landings_observed'],1)
