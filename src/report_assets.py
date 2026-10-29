"""Resolve the full local game library; embed only this battle's used PNGs."""
import base64
from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re
from urllib.parse import quote
from paths import resource_path

CARD_FOLDERS=('ui/portraits/units/','ui/units/icons/')

def required_images(index):
    return set(index['stats'].values())|{p for key in ('units','units_by_key') for p in index.get(key,{}).values() if p.startswith(CARD_FOLDERS)}|{p for p in index['provenance'] if p.startswith(CARD_FOLDERS)}


def name_key(text):
    return re.sub(r'[^\w]+',' ',text.casefold()).strip().removeprefix('the ')


def captured(unit, field):
    return unit.get('last',{}).get(field) or unit.get('last_observed',{}).get(field,{}).get('value') or unit.get('first',{}).get(field)


@lru_cache(maxsize=4)
def read_index(path, modified_ns, size):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def index_at(path):
    stamp=path.stat()
    return read_index(str(path),stamp.st_mtime_ns,stamp.st_size)


def readable_effect_name(text):
    if not isinstance(text,str):return None
    text=re.sub(r'\[\[[^\]]*\]\]','',text).strip()
    if not text or re.search(r'{{|[<>]|\bwh[23]?_|[a-z0-9]+_[a-z0-9_]+',text,re.I):return None
    if not any(c.isalpha() for c in text) or re.fullmatch(r'(?:0x)?[a-f0-9]{8,}',text,re.I):return None
    if any(ord(c)<32 for c in text):return None
    return text


def effect_texts_for(units,root):
    index=index_at(root/'effect-texts.json')
    result={}
    for u in units:
        for effect in (u.get('effect_timeline') or {}).get('effects',[]):
            key=effect['key'];ability_key,separator,phase_key=key.partition(':')
            if not separator:phase_key=key
            ability=index['abilities'].get(ability_key,{})
            phase=index['phases'].get(phase_key,{})
            phase_name=readable_effect_name(phase.get('name'))
            parent=readable_effect_name(ability.get('name')) or readable_effect_name(effect.get('name'))
            stage=bool(phase_name and re.match(r'^(?:stage|phase)\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|[ivxlcdm]+|[0-9]+)\b',phase_name,re.I))
            if stage:
                if not parent:
                    names={readable_effect_name(index['abilities'].get(k,{}).get('name')) for k in phase.get('ability_keys',[])+phase.get('family_ability_keys',[])}-{None}
                    if len(names)==1:parent=names.pop()
                name=parent+' \u2014 '+phase_name if parent and parent!=phase_name else phase_name
            else:name=parent or phase_name
            polarity=effect.get('polarity') or phase.get('polarity')
            fallback='Unidentified '+{'positive':'buff','negative':'debuff'}.get(polarity,'effect')
            result[key]=dict(name=name or fallback,
                source_label=ability.get('source_label',''),health=phase.get('health',{}),
                modifiers=phase.get('modifiers',[]),details=phase.get('details',[]))
    return result


def assets_for(units,icons=True,*,embed_images=True,image_prefix='assets/game/'):
    root=resource_path('assets')
    index=index_at(root/'game-assets.json')
    prices=index_at(root/'unit-values.json')
    library=index['provenance'];paths={p.lower():p for p in library}
    labels={};candidates={};army_votes=defaultdict(Counter)
    for u in units:
        name=u['name'];label=name
        for _ in range(16):
            new=re.sub(r'{{tr:([^}]+)}}',lambda m:index.get('localization',{}).get(m[1],m[0]),label)
            if new==label:break
            label=new
        aliases=index.get('normalized_names',{}).get(name_key(label),[])
        if '\ufffd' in label and len(aliases)==1:label=aliases[0]
        if label!=name:labels[name]=label
        keys=index.get('name_units',{}).get(name) or index.get('name_units',{}).get(label) or sorted({k for a in aliases for k in index.get('name_units',{}).get(a,[])})
        candidates[u['id']]=keys
        key=captured(u,'unit_key')
        cultures={index.get('unit_info',{}).get(k,{}).get('culture') for k in ([key] if key else keys)}-{None,''}
        if len(cultures)==1:army_votes[(u['side'],str(u['army']))][next(iter(cultures))]+=1
    cards={};by_id={};notes={};info={};unit_values={};values_by_id={}
    for u in units:
        name=u['name'];uid=u['id'];key=captured(u,'unit_key');keys=candidates[uid]
        image=None;note=index.get('unit_notes',{}).get(name,'')
        portrait=captured(u,'portrait_path')
        if portrait:
            path=portrait.replace('\\','/').lower().replace('/portholes/','/units/')
            image=paths.get(path) if path.startswith(CARD_FOLDERS) else None
            if image:note=''
        if not image and key:
            image=index.get('units_by_key',{}).get(key)
            note=index.get('unit_key_notes',{}).get(key,note)
        if key:keys=[key]
        if not image:
            image=index['units'].get(name) or index['units'].get(labels.get(name,''))
            if not image:
                images={index.get('units_by_key',{}).get(k) for k in keys}-{None}
                if len(images)==1:image=images.pop()
                elif len(images)>1:
                    votes=army_votes[(u['side'],str(u['army']))].most_common()
                    if votes and votes[0][1]>=3 and (len(votes)==1 or votes[0][1]-votes[1][1]>=3):
                        subset=[k for k in keys if index['unit_info'].get(k,{}).get('culture')==votes[0][0]]
                        images={index['units_by_key'].get(k) for k in subset}-{None}
                        if len(images)==1:
                            image=images.pop();keys=subset
                            note='Provisional card selected from matching unit names and army roster.'
        if image and not image.startswith(CARD_FOLDERS):image=None
        if image:
            by_id[uid]=image;cards.setdefault(name,image)
        else:
            note='Unit card unavailable.'
        if note:notes[uid]=note
        infos=[index.get('unit_info',{}).get(k,{}) for k in keys]
        if infos:
            castes={i.get('caste') for i in infos}
            info[uid]=dict(artillery=all(i.get('artillery') is True for i in infos),unit_key=key,
                character=bool(infos) and all(i.get('caste') in ('lord','hero') for i in infos),
                caste=next(iter(castes)) if len(castes)==1 else None,
                culture=next(iter(cultures)) if len(cultures:={i.get('culture') for i in infos}-{None})==1 else None)
        ps=[prices['by_unit_key'][key]] if key in prices.get('by_unit_key',{}) else prices['names'].get(labels.get(name,name),[])
        if not ps and keys:ps=[prices['by_unit_key'][k] for k in keys if k in prices.get('by_unit_key',{})]
        unit_values[name]=ps
        values_by_id[uid]=ps
    names=set(index['stats'].values())|set(by_id.values())
    stats=index['stats']
    if not icons:
        question=stats['other'];names={question}
        stats={key:question for key in stats}
        cards={u['name']:question for u in units};by_id={u['id']:question for u in units}
    return dict(stats=stats,icons_enabled=bool(icons),units=cards,unit_cards=by_id,labels=labels,unit_notes=notes,unit_info=info,
        race_names=index_at(root/'race-names.json'),effect_texts=effect_texts_for(units,root),statline=index_at(root/'statline.json'),
        unit_values=unit_values,unit_values_by_id=values_by_id,value_source=prices['source'],value_source_sha256=prices['sha256'],
        images={n:('data:image/png;base64,'+base64.b64encode((root/'game'/n).read_bytes()).decode('ascii') if embed_images else image_prefix+quote(n,safe='/')) for n in names},
        provenance={n:library[n] for n in names})
