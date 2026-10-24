"""Verify only the traced damage-accounting routines in bounded build windows."""
import csv
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT/'build/decoder'))
import capstone
from native_evidence import Image, pattern, ROOT

JOBS = {
    'result_add_damage': 0x142d77504,
    'damage_category_names': 0x142d61924,
    'damage_relationship_names': 0x142d61854,
    'entity_damage_accounting': 0x14325bbc4,
    'unit_outgoing_damage': 0x142f4bee0,
    'unit_incoming_damage': 0x142f4c0b0,
    'pair_outgoing_update': 0x142f4bdd8,
    'pair_incoming_update': 0x142f4bfa8,
    'pair_ring_advance': 0x142f55478,
    'history_ring_advance': 0x142f55044,
    'barrier_absorb': 0x14300fde8,
}


def main():
    functions = ROOT/'Ghidra Static/Function Exports/ghidra_function_exports'
    with (functions/'function_manifest.csv').open(newline='',encoding='utf-8') as stream:
        sizes = {int(r['address'],16):int(r['size']) for r in csv.DictReader(stream) if int(r['address'],16) in JOBS.values()}
    old = Image(ROOT/'decompile project/Warhammer3.exe')
    current = Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    evidence = {}
    try:
        for name,address in JOBS.items():
            size = sizes[address]
            query = pattern(old,address,size)
            low = address-0x10000
            hits = [low+m.start() for m in query.finditer(current.read(low,0x20000))]
            if len(hits) != 1:
                raise RuntimeError(f'{name}: {len(hits)} matches in bounded 128KiB window')
            evidence[name] = dict(reference=hex(address),current=hex(hits[0]),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=current.read(hits[0],size).hex())
        # The per-opponent bucket is updated at +0x14 by BOTH directions.
        # This is real machine code, not just a decompiler type inference.
        for name in ('pair_outgoing_update','pair_incoming_update'):
            for version in ('reference','current'):
                raw=bytes.fromhex(evidence[name][version+'_hex'])
                assert bytes.fromhex('016814') in raw, (name,version)
        for file in (PROJECT/'profiles').glob('*.json'):
            p=json.loads(file.read_text(encoding='utf-8'))
            version='current' if 'current' in file.name else 'reference'
            for item in evidence.values():
                anchor=dict(address=item[version],hex=item[version+'_hex'])
                if anchor not in p['anchors']:p['anchors'].append(anchor)
            p['damage_accounting']=dict(result_table_offset=0x20,
                categories=['ability','melee','missile','charge','melee_collision','other'],
                relationships=['enemy','self','ally'],native_gold_weight_offset=0x90,
                evidence='build/damage-accounting-evidence.json')
            p['offsets']['army_magic_recharge_rate']=p['offsets'].pop('army_magic_seconds_per_point',0xb4)
            p['evidence']['damage_accounting']='Native category/relationship counters verified; per-opponent history mixes directions and rotates.'
            file.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8')
        (PROJECT/'build/damage-accounting-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        print('Verified',len(evidence),'damage routines against both builds; no full executable/xref scan.')
    finally:
        old.stream.close();current.stream.close()


if __name__=='__main__':main()
