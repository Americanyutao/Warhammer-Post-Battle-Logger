"""Bounded read-only verification of persistent effect and ability list getters.

Only bounded file reads. Never calls game functions or changes game memory.
"""
import csv
import json
from pathlib import Path
import sys

P = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(P/'build/decoder'), str(P/'tools')]
from native_evidence import Image, pattern, ROOT

JOBS = {
    'active_effect_list': 0x141e5d470,
    'effect_polarity_state': 0x141e5d624,
    'battle_ability_list': 0x141e5fa04,
    'ability_lookup': 0x1430da4e8,
    'effect_name': 0x141e84100,
    'phase_key': 0x141c5b618,
    'effect_added_or_changed': 0x1430371d0,
    'effect_removed': 0x14303714c,
}


def main():
    exports = ROOT/'Ghidra Static/Function Exports/ghidra_function_exports'
    for registration, name, getter in (
            ('140210960', 'ActiveEffectList', '141e5d470'),
            ('140214040', 'BattleAbilityList', '141e5fa04')):
        source = (exports/'functions'/registration[:4]/(registration+'.c')).read_text(encoding='utf-8')
        assert '"'+name+'"' in source and 'FUN_'+getter in source
    with (exports/'function_manifest.csv').open(encoding='utf-8', newline='') as stream:
        sizes = {int(row['address'], 16): int(row['size']) for row in csv.DictReader(stream)
                 if int(row['address'], 16) in JOBS.values()}
    reference = Image(ROOT/'decompile project/Warhammer3.exe')
    installed = Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    result = dict(mode='static bounded reads only; no game attachment', functions={})
    try:
        for name, address in JOBS.items():
            size = sizes[address]
            start = address-0x10000
            matches = [start+m.start() for m in pattern(reference,address,size).finditer(installed.read(start,0x20000))]
            if len(matches) != 1:
                raise RuntimeError(f'{name}: {len(matches)} matches in bounded window')
            result['functions'][name] = dict(reference=hex(address), current=hex(matches[0]), size=size,
                reference_hex=reference.read(address,size).hex(), current_hex=installed.read(matches[0],size).hex())
    finally:
        reference.stream.close()
        installed.stream.close()
    fields = dict(count_offset=0x604, data_offset=0x608, stride=0x48,
        phase_offset=8, ability_offset=16, phase_key_offset=8, phase_polarity_offset=0x1c,
        phase_name_offset=0x68, ability_name_offset=0x168,
        evidence='build/effect-list-evidence.json')
    for file in (P/'profiles').glob('*.json'):
        profile=json.loads(file.read_text(encoding='utf-8'))
        version='current' if 'current' in file.name else 'reference'
        for item in result['functions'].values():
            anchor=dict(address=item[version],hex=item[version+'_hex'])
            if anchor not in profile['anchors']:profile['anchors'].append(anchor)
        profile['effect_fields']={**profile.get('effect_fields',{}),**fields}
        file.write_bytes((json.dumps(profile,indent=2)+'\n').encode('utf-8'))
    result['layout'] = fields
    result['limits'] = [
        'Event-maintained UI list: add/change callback1430371d0, remove callback14303714c receives UI unit+28; no unit-selection or camera gate in these callbacks.',
        'Add callback excludes phases with +b8 set: internal/UI-hidden phases are not promised. Passive effects are not filtered by the collector.',
        'Native Name: ability+168 localized UniString pointer, otherwise phase+68, otherwise entry[0] byte string. Phase context ID copies phase+8 byte string.',
        'Controlled live tests of off-camera effects, stacks and supported speed settings remain necessary.',
        'Record first/last observed presence and unknown gaps; missing reads must not mean effect removal.',
        'Remaining uses and cooldown changes describe sampled state, not necessarily successful casts.',
        'Current order/target polling cannot recover every repeated, cancelled or queued player command.',
    ]
    (P/'build/effect-list-evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Verified eight effect/ability routines and bound guarded effect fields on both builds.')


if __name__ == '__main__':
    main()
