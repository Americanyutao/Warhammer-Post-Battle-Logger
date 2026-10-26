"""Copy the original stat icons and unit-card bar scales, with source hashes."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
P=Path(__file__).resolve().parents[1]
ROOT=P.parent/'Local-files'
ROWS=[('hp','Current HP','stat_health'),('models','Models','stat_men_count'),
      ('armour','Armour','stat_armour'),('leadership','Leadership','stat_morale'),
      ('speed','Speed','scalar_speed'),('melee_attack','Melee Attack','stat_melee_attack'),
      ('melee_defence','Melee Defence','stat_melee_defence'),('weapon_strength','Weapon Strength','stat_weapon_damage'),
      ('charge_bonus','Charge Bonus','stat_charge_bonus'),('spell_resistance','Spell resistance','stat_resistance_magic'),
      ('missile_resistance','Missile resistance','stat_resistance_missile'),('fire_resistance','Fire resistance','stat_resistance_flame'),
      ('physical_resistance','Physical resistance','stat_resistance_physical'),('ward_save','Ward save','stat_resistance_all')]


def main():
    hashes={}
    def table(name):
        file=ROOT/'db'/name/'data__.tsv';hashes[str(file.relative_to(ROOT))]=hashlib.sha256(file.read_bytes()).hexdigest()
        with file.open(encoding='utf-8-sig',newline='') as f:return [r for r in csv.DictReader(f,delimiter='\t') if not r['stat' if name.endswith('castes_tables') else 'key'].startswith('#')]
    definitions={r['key']:r for r in table('ui_unit_stats_tables')}
    castes={}
    for r in table('ui_unit_stat_to_unit_castes_tables'):castes.setdefault(r['stat'],{})[r['unit_caste']]=float(r['max_value_override'])
    file=P/'assets/game-assets.json';manifest=json.loads(file.read_text(encoding='utf-8'));rows=[]
    for key,label,stat in ROWS:
        d=dict(icon='ui/skins/default/icon_entity_small.png',max_value=1,min_value=0) if key=='models' else definitions[stat];source=ROOT/d['icon']
        if key=='models':source=ROOT/'ui/skins/default/icon_entity_small.png'
        asset='statline_'+key+'.png';shutil.copy2(source,P/'assets/game'/asset)
        manifest['stats']['statline:'+key]=asset
        manifest['provenance'][asset]=dict(source=source.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        rows.append(dict(key=key,label=label,max=float(d['max_value']),min=float(d['min_value']),caste_max=castes.get(stat,{}),percent='resistance' in key or key=='ward_save'))
    source=ROOT/'ui/skins/default/icon_status_route_24px.png';asset='statline_retreat.png'
    shutil.copy2(source,P/'assets/game'/asset)
    manifest['stats']['statline:retreat']=asset
    manifest['provenance'][asset]=dict(source=source.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    file.write_bytes((json.dumps(manifest,indent=2)+'\n').encode('utf-8'))
    (P/'assets/statline.json').write_bytes((json.dumps(dict(schema=1,rows=rows,source_hashes=hashes),indent=2)+'\n').encode('utf-8'))
    print('Packaged14 original stat icons and unit-card bar scales.')


if __name__=='__main__':main()
