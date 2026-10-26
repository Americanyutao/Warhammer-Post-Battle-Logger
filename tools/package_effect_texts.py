"""Bundle English effect text and listed modifiers from the game export."""
import csv
from collections import defaultdict
import hashlib
import html
import json
from pathlib import Path
import re

P=Path(__file__).resolve().parents[1]
ROOT=P.parent/'Local-files'


def plain_text(text,localization,seen=()):
    def translate(match):
        key=match[1]
        return '' if key in seen else plain_text(localization.get(key,''),localization,(*seen,key))
    if len(seen)>16:return ''
    text=re.sub(r'{{tr:([^}]+)}}',translate,text)
    text=re.sub(r'\[\[[^\]]*\]\]','',text)
    text=re.sub(r'\\+n','\n',text).replace('||','\n')
    return '\n'.join(re.sub(r'[^\S\n]+',' ',line).strip() for line in html.unescape(text).splitlines()).strip()


def build_index():
    csv.field_size_limit(8*1024*1024)
    sources={}
    def table(relative):
        path=ROOT/relative;sources[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
        with path.open(encoding='utf-8-sig',newline='') as stream:
            return [r for r in csv.DictReader(stream,delimiter='\t',quoting=csv.QUOTE_NONE) if not next(iter(r.values()),'').startswith('#')]
    loc={}
    for name in ('unit_abilities','special_ability_phases','unit_abilities_additional_ui_effects',
                 'unit_stat_localisations','unit_attributes','special_ability_groups','unit_ability_source_types','ancillaries'):
        loc.update({r['key']:r['text'] for r in table('text/db/'+name+'__.loc.tsv')})
    def text(key):return plain_text(loc.get(key,''),loc)
    ability_records={r['key']:r for r in table('db/unit_abilities_tables/data__.tsv')}
    ability_keys=set(ability_records)|{r['key'] for r in table('db/unit_special_abilities_tables/data__.tsv')}
    ability_keys.update(k.removeprefix('unit_abilities_onscreen_name_') for k in loc if k.startswith('unit_abilities_onscreen_name_'))
    abilities={}
    for key in sorted(ability_keys):
        source_type=ability_records.get(key,{}).get('source_type','')
        abilities[key]=dict(name=text('unit_abilities_onscreen_name_'+key),
            source_type=source_type,source_label=text('unit_ability_source_types_name_'+source_type))
    parents=defaultdict(set)
    for r in table('db/special_ability_to_special_ability_phase_junctions_tables/data__.tsv'):
        parents[r['phase']].add(r['special_ability'])
    details=defaultdict(list)
    modifiers=defaultdict(list)
    for r in table('db/special_ability_phase_stat_effects_tables/data__.tsv'):
        label=text('unit_stat_localisations_onscreen_name_'+r['stat'])
        if not label:continue
        # Literal configured add/multiply modifiers, not inferred live values.
        if r['how'] not in ('add','mult'):continue
        modifiers[r['phase']].append(dict(label=label,how=r['how'],value=float(r['value'])))
    for r in table('db/special_ability_phase_attribute_effects_tables/data__.tsv'):
        label=text('unit_attributes_bullet_text_'+r['attribute'])
        if label:details[r['phase']].append(('Removes: ' if r['attribute_type']=='negative' else '')+label.split('\n')[0])
    for r in table('db/special_ability_phases_to_additional_ui_effects_junctions_tables/data__.tsv'):
        label=text('unit_abilities_additional_ui_effects_localised_text_'+r['effect'])
        if label:details[r['special_ability_phase']].append(label)
    phases={}
    for r in table('db/special_ability_phases_tables/data__.tsv'):
        key=r['id'];linked=[abilities[a] for a in sorted(parents[key]) if a in abilities]
        # The game's tooltip_special_ability_phase uses ManaRegenMod * 100
        # for Power Recharge (%) and ManaMaxDepletionMod for Reserves/s.
        # IntensifiedValueText applies the observed phase intensity at display.
        for field,label,scale,unit in (
                ('mana_regen_mod','Winds of Magic recharge',100,'%'),
                ('mana_max_depletion_mod','Winds of Magic reserves',1,' Winds/s')):
            value=float(r[field])
            if value:modifiers[key].append(dict(label=label,how='add',value=value*scale,unit=unit))
        direct=abilities.get(key,{})
        names={a['name'] for a in linked if a['name']}
        phases[key]=dict(ability_keys=sorted(parents[key]),name=text('special_ability_phases_onscreen_name_'+key) or direct.get('name') or (next(iter(names)) if len(names)==1 else ''),
            details=list(dict.fromkeys(details[key])),modifiers=modifiers[key],polarity=r['effect_type'],
            health=dict(interval_s=float(r['hp_change_frequency']),damage=int(r['damage_amount']),
                max_entities=int(r['max_damaged_entities']),heal_fraction=float(r['heal_amount']),
                barrier_heal_fraction=float(r['barrier_heal_amount']),duration_s=float(r['duration']),
                resurrect=r['resurrect']=='true'))
    # Later stages sometimes omit a direct junction. Reuse only the same
    # stage-family's verified junctions, keeping hidden phases separate.
    stage_family=lambda key:re.sub(r'_(?:[ivx]+|[0-9]+)(?=_hidden$|$)','',key,flags=re.I)
    family_parents=defaultdict(set)
    for key,phase in phases.items():
        if re.match(r'^(Stage|Phase)\s+',phase['name'],re.I):family_parents[stage_family(key)].update(phase['ability_keys'])
    for key,phase in phases.items():
        if not phase['ability_keys'] and re.match(r'^(Stage|Phase)\s+',phase['name'],re.I):
            phase['family_ability_keys']=sorted(family_parents[stage_family(key)])
    contact_groups=defaultdict(list)
    for r in table('db/special_ability_contact_phase_groups_tables/data__.tsv'):
        contact_groups[r['contact_phase_group_id']].append(r['contact_phase_id'])
    index=dict(schema=3,language='English',source_hashes=sources,abilities=abilities,phases=phases,
        contact_groups=dict(sorted(contact_groups.items())),
        coverage=dict(abilities=len(abilities),phases=len(phases),
            phase_names=sum(bool(v['name']) for v in phases.values()),
            phases_with_effects=sum(bool(v['details'] or v['modifiers'] or v['health']['damage'] or v['health']['heal_fraction'] or v['health']['barrier_heal_fraction']) for v in phases.values())))
    (P/'assets/effect-texts.json').write_bytes((json.dumps(index,ensure_ascii=False,separators=(',',':'))+'\n').encode('utf-8'))
    return index


if __name__=='__main__':
    index=build_index()
    print(f"Packaged {len(index['abilities'])} ability texts and {len(index['phases'])} phase definitions from game files.")
