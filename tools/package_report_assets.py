"""Keep the complete extracted unit PNG library and database-backed name index."""
import hashlib
import csv
import json
from pathlib import Path
import shutil
import re
from collections import defaultdict
P=Path(__file__).resolve().parents[1]
ROOT=P.parent/'Local-files'
STATS={'ammo':'icon_stat_ammo.png','firing':'icon_status_firing.png','hp':'icon_stat_health.png','healing':'stat_healing_received.png',
 'damage':'icon_stat_damage.png','gold':'icon_treasury.png','barrier':'icon_barrier_replenish.png',
 'status':'icon_stat_morale.png','movement':'icon_stat_speed.png','models':'icon_entity_small.png',
 'missile':'icon_stat_ranged_damage.png','ability':'icon_magic_pool.png',
 'melee':'icon_stat_attack.png','charge':'battle_charge.png','other':'icon_question_mark.png',
 'kills':'icon_kills.png','fatigue':'icon_status_fatigue.png','winds':'icon_magic_pool.png','trade':'icon_trade.png'}
UNITS={
 'Necrarch Vampire Lord':'ui/portraits/units/no_culture/vmp_bloodline_necrarch_lord_campaign_01_0.png',
 'Lahmian Handmaidens (Death)':'ui/units/icons/wh3_dlc29_vmp_inf_lahmian_handmaidens_death.png',
 'Sylvanian Crossbowmen':'ui/units/icons/wh2_dlc11_vmp_crossbowmen.png',
 'Fell Bats':'ui/units/icons/wh_main_vmp_fell_bats.png',
 'Varghulf':'ui/units/icons/wh_main_vmp_varghulf.png',
 'Zombie Dragon':'ui/units/icons/wh3_dlc29_vmp_mon_zombie_dragon.png',
 'The Claw of Nagash (Mortis Engine)':'ui/units/icons/wh_dlc04_vmp_claw_of_nagash.png',
 'Claw of Nagash (Mortis Engine)':'ui/units/icons/wh_dlc04_vmp_claw_of_nagash.png',
 'Crypt Ghouls':'ui/units/icons/wh_main_vmp_crypt_ghoul.png',
 'Black Knights':'ui/units/icons/wh_main_vmp_black_knights.png',
 'Skeleton Warriors':'ui/units/icons/wh2_dlc09_tmb_skeleton_warriors.png',
 '{{tr:land_units_onscreen_name_wh2_dlc09_tmb_inf_skeleton_warriors_0_summoned}}':'ui/units/icons/wh2_dlc09_tmb_skeleton_warriors.png',
 'Zombies':'ui/units/icons/wh_main_vmp_zombies.png',
 'Skeleton Warriors (Swords)':'ui/units/icons/wh_main_vmp_skeleton_warrior_sword.png',
 'Skeletons':'ui/units/icons/wh_main_vmp_skeleton_warrior_sword.png'}

def table(relative):
    with (ROOT/relative).open(encoding='utf-8-sig',newline='') as f:
        return [r for r in csv.DictReader(f,delimiter='\t') if r and not next(iter(r.values()),'').startswith('#')]


def normalized_key(key):
    key=re.sub(r'^wh[23]?_(?:main|dlc\d+|pro\d+|twa\d+)_','',key.lower())
    key=re.sub(r'^wh[23]?_','',key)
    if key.startswith('dae_') and key.split('_')[1] in ['chs','nur','kho','sla','tze']:key=key[4:]
    key=re.sub(r'_(?:cha|ch|inf|cav|art|mon|veh)_','_',key)
    key=re.sub(r'_(?:campaign|battle)_\d+(?:_\d+)?$','',key)
    key=re.sub(r'_\d+$','',key)
    marked=re.match(r'^chs_(.+?)_m(kho|nur|sla|tze)(?:_.*)?$',key)
    if marked:key=marked[2]+'_'+marked[1]
    key=key.replace('cst_vampire_fleet_','cst_fleet_')
    if key.endswith('_captains'):key=key[:-1]
    return key


def name_key(text):
    return re.sub(r'[^\w]+',' ',text.casefold()).strip().removeprefix('the ')


def main():
    target=P/'assets/game';target.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema=2,stats={},units={},units_by_key={},name_units={},provenance={},labels={},unit_notes={},unit_info={},localization={})
    localization={}
    for name in ['land_units','agent_subtypes','agent_localisations','names']:
        with (ROOT/('text/db/'+name+'__.loc.tsv')).open(encoding='utf-8-sig',newline='') as f:
            for r in csv.reader(f,delimiter='\t'):
                if len(r)>1 and not r[0].startswith('#'):localization[r[0]]=r[1]
    def resolve(text):
        seen=set()
        for _ in range(16):
            if text in seen:return ''
            seen.add(text)
            if not re.search(r'{{tr:([^}]+)}}',text):return text
            missing=False
            def replace(m):
                nonlocal missing
                if m[1] not in localization:missing=True;return m[0]
                return localization[m[1]]
            text=re.sub(r'{{tr:([^}]+)}}',replace,text)
            if missing:return ''
        return ''
    manifest['localization']={k:resolve(v) for k,v in localization.items() if v}
    manifest['localization']={k:v for k,v in manifest['localization'].items() if v}
    stems=defaultdict(list);portraits=defaultdict(list)
    sources=[p for rel in ['ui/units','ui/portraits'] for p in (ROOT/rel).rglob('*.png')]
    def copy(source,asset):
        destination=target/asset;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        manifest['provenance'][asset]=dict(source=source.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    for source in sorted(sources):
        asset=source.relative_to(ROOT).as_posix();copy(source,asset);stems[source.stem].append(asset)
        if '_mask' not in source.stem:portraits[normalized_key(source.stem)].append(asset)
    for key,file in STATS.items():copy(ROOT/'ui/skins/default'/file,file);manifest['stats'][key]=file
    def rank(asset):
        groups=('/units/icons/','/portraits/units/','/units/infopics/',
                '/units/minspec_portholes/','/portraits/portholes/','/portraits/faction_leaders/')
        return (next((i for i,group in enumerate(groups) if group in asset),len(groups)),
                '/no_culture/' not in asset,'_mask' in asset,asset)
    def card(*keys):
        for key in keys:
            if not key or key in ['placeholder','a_character_placeholder']:continue
            if stems.get(key):return min(stems[key],key=rank)
            if portraits.get(normalized_key(key)):return min(portraits[normalized_key(key)],key=rank)
        return None
    mains=table('db/main_units_tables/data__.tsv');lands={r['key']:r for r in table('db/land_units_tables/data__.tsv')}
    variants=defaultdict(list)
    for r in table('db/unit_variants_tables/data__.tsv'):variants[r['unit']].append(r)
    aliases=defaultdict(set);prices={};price_keys={};missing=[]
    special={'wh3_dlc29_chs_cha_glottkin':'ui/portraits/units/no_culture/chs_otto_0.png'}
    for r in mains:
        key=r['unit'];land=r.get('land_unit','')
        # Variant cards are keyed by land-unit records, including vehicle crews.
        # Retain main-key variants too for records where both keys are identical.
        v=sorted(variants[key]+(variants[land] if land!=key else []),key=lambda x:(bool(x['faction']),x['faction']))
        candidates=[x['unit_card'] for x in v]+[key,land]+[x['variant'] for x in v]
        image=special.get(key) or card(*candidates)
        loc_keys=['land_units_onscreen_name_'+x for x in [land,key,*[x['name'] for x in v]] if x]
        names={resolve(localization.get(k,'')) for k in loc_keys}-{''}
        culture=normalized_key(key).split('_')[0]
        image=image or card(*[culture+'_'+name_key(n).replace(' ','_') for n in sorted(names)])
        if image:manifest['units_by_key'][key]=image
        else:missing.append(key)
        for name in names:aliases[name].add(key)
        for loc in loc_keys:
            if loc in manifest['localization']:
                token='{{tr:'+loc+'}}';aliases[token].add(key);manifest['labels'][token]=manifest['localization'][loc]
        landrow=lands.get(land,{})
        manifest['unit_info'][key]=dict(land_key=land,culture=normalized_key(key).split('_')[0],
            caste=r.get('caste',''),artillery=landrow.get('category')=='artillery',engine=landrow.get('engine',''),configured_engines=int(landrow.get('num_engines') or 0))
        try:cost=int(r['multiplayer_cost'])
        except (ValueError,TypeError,KeyError):continue
        if cost<0:continue
        price=dict(unit_key=key,value=cost,summoned_variant=any(t in key for t in ('summoned','raise_legion','the_awakening')))
        price_keys[key]=price
        for name in names:prices.setdefault(name,[]).append(price)
    # DB-linked duplicates (mounts, scripted variants and campaign upgrades) can
    # share the same original card without guessing a different unit family.
    for _ in range(3):
        changed=False
        for key in list(missing):
            info=manifest['unit_info'][key]
            peers=[k for k in manifest['units_by_key'] if manifest['unit_info'][k]['land_key']==info['land_key']]
            if not peers:
                peers=[k for name,ks in aliases.items() if key in ks and not name.startswith('{{tr:')
                       for k in ks if k in manifest['units_by_key'] and manifest['unit_info'][k]['culture']==info['culture']]
            images={manifest['units_by_key'][k] for k in peers}
            if len(images)==1:
                manifest['units_by_key'][key]=images.pop();missing.remove(key);changed=True
        if not changed:break
    for alias,keys in aliases.items():
        manifest['name_units'][alias]=sorted(keys)
        images={manifest['units_by_key'][k] for k in keys if k in manifest['units_by_key']}
        if len(images)==1:manifest['units'][alias]=images.pop()
    # Keep previously reviewed choices, flagged when the old capture lacks a type.
    for alias,relative in UNITS.items():
        if relative in manifest['provenance']:
            manifest['units'][alias]=relative
            if alias.startswith('{{tr:'):manifest['unit_notes'][alias]='Provisional card matched from the translated unit name.'
    manifest['normalized_names']=defaultdict(list)
    for alias in aliases:
        if not alias.startswith('{{tr:'):manifest['normalized_names'][name_key(alias)].append(alias)
    db=ROOT/'db/main_units_tables/data__.tsv'
    (P/'assets/unit-values.json').write_text(json.dumps(dict(names=prices,by_unit_key=price_keys,
        source='db/main_units_tables/data__.tsv:multiplayer_cost',sha256=hashlib.sha256(db.read_bytes()).hexdigest()),indent=2)+'\n',encoding='utf-8')
    manifest['library_summary']=dict(unit_pngs=len(sources),unit_records=len(mains),mapped_unit_records=len(manifest['units_by_key']),unmapped_unit_keys=missing,
        note='Every PNG under ui/units and ui/portraits retained, including portholes and info pictures; reports embed only needed assets. Main-unit to land-unit variant links supply the original configured cards.')
    (P/'assets/game-assets.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest['library_summary'].items() if k!='unmapped_unit_keys'},ensure_ascii=True));print('Unmapped records:',len(missing))


if __name__=='__main__':main()
