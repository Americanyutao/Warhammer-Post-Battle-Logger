"""DB-linked character card paths from the game's version-4 portrait metadata."""
from collections import defaultdict
from pathlib import Path
import struct

def portrait_entries(path):
    data=Path(path).read_bytes();offset=0
    def read(size):
        nonlocal offset
        if size<0 or offset+size>len(data):raise ValueError('Truncated portrait settings.')
        value=data[offset:offset+size];offset+=size;return value
    def integer(fmt):return struct.unpack(fmt,read(struct.calcsize(fmt)))[0]
    def text():return read(integer('<H')).decode('utf-8')
    if integer('<I')!=4:raise ValueError('Unsupported portrait settings version.')
    count=integer('<I')
    if count>10000:raise ValueError('Invalid portrait entry count.')
    entries={}
    for _ in range(count):
        key=text();read(20);text();body=integer('<B')
        if body not in (0,1):raise ValueError('Invalid portrait camera flag.')
        if body:read(20);text()
        variants=integer('<I')
        if variants>1000 or key in entries:raise ValueError('Invalid portrait variants.')
        entries[key]=[(text(),[text() for _ in range(4)]) for _ in range(variants)]
    if offset!=len(data):raise ValueError('Trailing portrait settings data.')
    return entries

def character_cards(root,table,available):
    """Join associated-unit -> agent subtype -> art set -> diffuse -> units path."""
    root=Path(root);entries={}
    for path in sorted((root/'ui/portraits/units').glob('*.bin')):
        for key,rows in portrait_entries(path).items():entries.setdefault(key,[]).extend(rows)
    mains={r['unit']:r for r in table('db/main_units_tables/data__.tsv')}
    variants=defaultdict(set)
    for row in table('db/unit_variants_tables/data__.tsv'):variants[row['unit']].add(row['variant'])
    agents=defaultdict(list)
    for row in table('db/agent_subtypes_tables/data__.tsv'):
        key=row['associated_unit_override']
        if key:agents[key].append(row['key'])
    artsets=defaultdict(list);priority={}
    for row in table('db/campaign_character_art_sets_tables/data__.tsv'):
        if row['agent_subtype']:
            artsets[row['agent_subtype']].append(row['art_set_id'])
            priority[row['art_set_id']]=(bool(row['faction'] or row['culture'] or row['subculture']),row['art_set_id'])
    mounted=defaultdict(set)
    for row in table('db/units_custom_battle_mounts_tables/data__.tsv'):mounted[row['mounted_unit']].add(row['base_unit'])
    available={name.lower():name for name in available};result={}
    for key,main in mains.items():
        land=main['land_unit'];visuals=variants[key]|variants[land]
        associated=set(agents.get(key,[]))|set(agents.get(land,[]))
        for base in mounted[key]:associated.update(agents.get(base,[]))
        if not any(art in entries for subtype in associated for art in artsets[subtype]) and visuals:
            for base,subtypes in agents.items():
                base_land=mains.get(base,{}).get('land_unit','')
                if visuals&(variants[base]|variants[base_land]):associated.update(subtypes)
        rows=[]
        for subtype in sorted(associated):
            for art in sorted(artsets[subtype],key=lambda key:priority[key]):
                for variant,files in entries.get(art,[]):
                    path=files[0].replace('\\','/').lower().replace('/portholes/','/units/')
                    if path.startswith('ui/portraits/units/') and path in available:
                        rows.append(dict(image=available[path],agent_subtype=subtype,art_set=art,portrait_variant=variant))
        if rows:result[key]=rows
    return result
