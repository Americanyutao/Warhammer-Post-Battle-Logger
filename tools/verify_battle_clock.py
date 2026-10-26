"""Verify the named UI countdown getter using bounded executable-file reads."""
import csv
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'tools'),str(P/'build/decoder')]
from native_evidence import Image,pattern,ROOT


def main():
    exports=ROOT/'Ghidra Static/Function Exports/ghidra_function_exports'
    registration=(exports/'functions/1402/14024bf30.c').read_text(encoding='utf-8')
    assert '"TimeRemainingString"' in registration and 'FUN_141e9d96c' in registration
    address=0x141e9d96c
    with (exports/'function_manifest.csv').open(encoding='utf-8',newline='') as stream:
        size=next(int(r['size']) for r in csv.DictReader(stream) if int(r['address'],16)==address)
    reference=Image(ROOT/'decompile project/Warhammer3.exe')
    current=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    try:
        start=address-65536
        hits=[start+m.start() for m in pattern(reference,address,size).finditer(current.read(start,131072))]
        if len(hits)!=1:raise ValueError('Battle UI clock getter is not a unique bounded match.')
        evidence=dict(reference=hex(address),current=hex(hits[0]),size=size,
            reference_hex=reference.read(address,size).hex(),current_hex=current.read(hits[0],size).hex())
        fields=dict(elapsed_offset=0xf8,settings_offset=0x98,limit_offset=0xf4,
            override_flag_offset=0x645e0,override_pointer_offset=0x645d0,override_limit_ms_offset=0x24,
            evidence='build/battle-clock-evidence.json')
        for file in (P/'profiles').glob('*.json'):
            profile=json.loads(file.read_text(encoding='utf-8'));version='current' if 'current' in file.name else 'reference'
            anchor=dict(address=evidence[version],hex=evidence[version+'_hex'])
            if anchor not in profile['anchors']:profile['anchors'].append(anchor)
            profile['battle_clock_fields']=fields
            file.write_bytes((json.dumps(profile,indent=2)+'\n').encode('utf-8'))
        evidence.update(fields=fields,semantics='CcoBattleRoot.TimeRemainingString subtracts roster+f8 elapsed seconds from the configured limit; unlimited battles display elapsed directly. Read the same elapsed field, never the pre-combat script-engine clock. Limit/remaining are optional and retain scenario override semantics.')
        (P/'build/battle-clock-evidence.json').write_bytes((json.dumps(evidence,indent=2)+'\n').encode('utf-8'))
    finally:reference.stream.close();current.stream.close()
    print('Verified the battle UI countdown getter and bound both profiles.')


if __name__=='__main__':main()
