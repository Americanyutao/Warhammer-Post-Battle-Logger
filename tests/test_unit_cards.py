import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
P=Path(__file__).resolve().parents[1];sys.path[:0]=[str(P/'src'),str(P/'tools')]
from report_assets import assets_for,index_at,required_images
from unit_card_sources import portrait_entries

def unit(key,portrait=None):return dict(id=key,name='Custom character',side='Allied',army='1',first={},last=dict(unit_key=key,portrait_path=portrait))

class UnitCardTests(unittest.TestCase):
    def test_catalog_and_runtime_have_no_porthole_fallbacks(self):
        index=index_at(P/'assets/game-assets.json')
        for section in ('units','units_by_key'):
            self.assertFalse(any('porthole' in p for p in index[section].values()))
        self.assertFalse(any('porthole' in p for p in required_images(index)))
        keys=list(index['card_candidates_by_key'])
        self.assertGreaterEqual(len(keys),42)
        assets=assets_for([unit(k) for k in keys],embed_images=False)
        for key in keys:
            image=assets['unit_cards'][key]
            self.assertTrue(image.startswith(('ui/portraits/units/','ui/units/icons/')))
            self.assertTrue((P/'assets/game'/image).is_file())

    def test_named_and_mounted_characters_use_traced_cards(self):
        cases={'wh2_dlc09_skv_cha_tretch_craventail':'skv_tretch_craventail_0.png',
            'wh2_dlc11_cst_inf_count_noctilus_1':'cst_cha_count_noctilus_0.png',
            'wh2_dlc14_def_cha_master_4':'def_master_campaign_01_0.png',
            'wh_main_vmp_cha_banshee':'vmp_banshees_campaign_01_0.png'}
        assets=assets_for([unit(k) for k in cases],embed_images=False)
        for key,name in cases.items():self.assertTrue(assets['unit_cards'][key].endswith(name))

    def test_recorded_appearance_selects_exact_card_and_clears_default_note(self):
        key='wh3_dlc20_chs_cha_daemon_prince_msla'
        fallback=assets_for([unit(key)],embed_images=False)
        self.assertIn('Default appearance',fallback['unit_notes'][key])
        selected=assets_for([unit(key,'UI/Portraits/Portholes/no_culture/dae_sla_daemon_prince_3_0.png')],embed_images=False)
        self.assertEqual(selected['unit_cards'][key],'ui/portraits/units/no_culture/dae_sla_daemon_prince_3_0.png')
        self.assertNotIn(key,selected['unit_notes'])

    def test_portrait_settings_decoder_checks_framing_and_camera_variants(self):
        def text(s):
            data=s.encode();return struct.pack('<H',len(data))+data
        entry=text('art_set')+bytes(20)+text('')+bytes([1])+bytes(20)+text('')+struct.pack('<I',1)+text('variant')
        entry+=b''.join(text(s) for s in ('UI/Portraits/Portholes/card.png','','',''))
        data=struct.pack('<II',4,1)+entry
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'portrait.bin';path.write_bytes(data)
            self.assertEqual(portrait_entries(path)['art_set'][0][0],'variant')
            for bad in (data[:-1],data+b'x',struct.pack('<I',99)+data[4:]):
                path.write_bytes(bad)
                with self.assertRaises((ValueError,struct.error)):portrait_entries(path)

if __name__=='__main__':unittest.main()
