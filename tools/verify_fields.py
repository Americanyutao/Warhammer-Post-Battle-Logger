"""Bounded port: named getters beside existing meter fields; no global scan."""
import json
import re
import struct
from pathlib import Path
from native_evidence import Image, ROOT, PROJECT

# Exact saved registration -> getter. Primitive getters have no relocations.
JOBS = {
    'health_percent': (0x1402299b0, 0x1408e1cf0, 12, 0x668, 'f'),
    'regen_base': (0x140229b40, 0x1408e1d00, 18, None, 'indirect'),
    'firing': (0x140230c50, 0x1408e1e10, 11, 0x6ff, '?'),
    'flying': (0x140230f70, 0x1408e1e20, 11, 0x712, '?'),
    'idle': (0x140231e00, 0x1408e1e60, 11, 0x700, '?'),
    'melee': (0x140232120, 0x1408e1e80, 11, 0x6fd, '?'),
    'routing': (0x140235220, 0x1408e20c0, 11, 0x715, '?'),
    'running': (0x1402353b0, 0x1408e20d0, 11, 0x703, '?'),
    'walking': (0x140238d50, 0x1408e2360, 11, 0x702, '?'),
    'withdrawing': (0x140239380, 0x1408e2370, 11, 0x708, '?'),
    'under_missile': (0x1402381d0, 0x1408e2340, 11, 0x6fc, '?'),
    'primary_ammo_fraction': (0x1402411f0, 0x1408e2450, 12, 0x6c4, 'f'),
    'secondary_ammo_fraction': (0x140243f30, 0x1408e24a0, 12, 0x6c8, 'f'),
    'fatigue_state': (0x140224b50, 0x1408e1ca0, 10, 0x6e4, 'I'),
    'morale_state': (0x14023bee0, 0x1408e23b0, 10, 0x6f0, 'I'),
    'models_initial': (0x14023c9a0, 0x1408e23c0, 10, 0x634, 'I'),
    'barrier_hp': (0x1402136e0, 0x1408e1970, 10, 0x690, 'I'),
    'barrier_max': (0x140213870, 0x1408e1990, 10, 0x694, 'I'),
    'spawned': (0x140236400, 0x1408e20f0, 18, None, 'indirect'),
    'models': (0x14023ccc0, 0x141e84904, 20, 0x664, 'I'),
    'shattered': (0x140235bf0, 0x141e820b0, 15, None, 'morale=7'),
}

def bounded(image, reference, query, radius=0x10000):
    start = reference - radius
    data = image.read(start, radius * 2)
    hits = [start + hit.start() for hit in query.finditer(data)]
    if len(hits) != 1:
        raise RuntimeError(f'{reference:x}: {len(hits)} matches in bounded window')
    return hits[0]

def main():
    old = Image(ROOT / 'decompile project/Warhammer3.exe')
    current = Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    evidence, anchors_old, anchors_new, fields = {}, [], [], {}
    fn = ROOT / 'Ghidra Static/Function Exports/ghidra_function_exports/functions'
    for key, (registration, address, size, offset, kind) in JOBS.items():
        source = (fn / f'{registration:x}'[:4] / f'{registration:x}.c').read_text()
        assert f'{address:x}' in source, key
        raw = old.read(address, 32)
        size = raw.index(b'\xc3') + 1
        raw = raw[:size]
        target = bounded(current, address, re.compile(re.escape(raw)))
        evidence[key] = dict(registration=hex(registration), reference=hex(address),
                             current=hex(target), hex=raw.hex(), offset=offset, kind=kind)
        anchors_old.append(dict(address=hex(address), hex=raw.hex()))
        anchors_new.append(dict(address=hex(target), hex=raw.hex()))
        if offset is not None:
            fields[key] = dict(offset=offset, kind=kind)
    # Health functions contain PC-relative calls: mask precisely those operands.
    for key, address, size, masks in [
        ('hp_cached_source', 0x14301baf4, 133, [(31, 4), (55, 4), (81, 4)]),
        ('hp_max_cached_source', 0x1430346dc, 77, [(31, 4), (55, 4)])]:
        raw = old.read(address, size)
        # Operands follow E8; reject an incorrect mask instead of silently widening.
        for pos, count in masks:
            assert raw[pos-1] == 0xe8, (key, pos, raw.hex())
        mask = {i for pos, count in masks for i in range(pos, pos+count)}
        query = re.compile(b''.join(b'.' if i in mask else re.escape(bytes([b]))
                                    for i, b in enumerate(raw)), re.DOTALL)
        target = bounded(current, address, query)
        evidence[key] = dict(reference=hex(address), current=hex(target), reference_hex=raw.hex(),
                             current_hex=current.read(target, size).hex(), masks=masks)
        anchors_old.append(dict(address=hex(address), hex=raw.hex()))
        anchors_new.append(dict(address=hex(target), hex=current.read(target, size).hex()))
    fields.update(hp_cached=dict(offset=0x6b0, kind='I'), hp_max_cached=dict(offset=0x6ac, kind='I'))
    for file in (PROJECT / 'profiles').glob('*.json'):
        profile = json.loads(file.read_text())
        safe = json.loads((ROOT / 'damage-meter/safe/profiles' / file.name).read_text())
        for anchor in safe['anchors']:
            if anchor not in profile['anchors']: profile['anchors'].append(anchor)
        profile['offsets'].update({k:v for k,v in safe['offsets'].items() if k not in profile['offsets']})
        profile['logger_fields'] = fields
        profile['anchors'] += anchors_new if 'current' in file.name else anchors_old
        profile['evidence']['logger'] = 'build/field-verification.json; ordinary battle cached HP; live semantics pending.'
        file.write_text(json.dumps(profile, indent=2)+'\n')
    (PROJECT / 'build/field-verification.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print('Verified',len(evidence),'bounded getter/source matches; profiles updated only in battle-logger.')

if __name__ == '__main__': main()
