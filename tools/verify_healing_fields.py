"""Verify the existing healing-budget trace in bounded executable windows."""
import csv
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT/'build/decoder'))
import capstone
from native_evidence import Image, pattern, ROOT


def main():
    jobs = {'budget_consume':0x143047e04, 'effect_healing':0x1430c8e98,
            'model_healing':0x1430ae3b4}
    with (ROOT/'Ghidra Static/Function Exports/ghidra_function_exports/function_manifest.csv').open(encoding='utf-8',newline='') as f:
        sizes={int(r['address'],16):int(r['size']) for r in csv.DictReader(f) if int(r['address'],16) in jobs.values()}
    old=Image(ROOT/'decompile project/Warhammer3.exe')
    new=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    evidence={}
    try:
        for name,address in jobs.items():
            size=sizes[address]; low=address-0x10000
            hits=[low+m.start() for m in pattern(old,address,size).finditer(new.read(low,0x20000))]
            if len(hits)!=1: raise RuntimeError(f'{name}: {len(hits)} bounded matches')
            evidence[name]=dict(reference=hex(address), current=hex(hits[0]),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=new.read(hits[0],size).hex())
        for file in (PROJECT/'profiles').glob('*.json'):
            p=json.loads(file.read_text(encoding='utf-8')); version='current' if 'current' in file.name else 'reference'
            for item in evidence.values():
                a=dict(address=item[version],hex=item[version+'_hex'])
                if a not in p['anchors']:p['anchors'].append(a)
            p['healing_budget']=dict(native_stats_offset=0x3d48,remaining_offset=0x264,flags_offset=0x268,
                evidence='build/healing-budget-evidence.json')
            file.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8')
        (PROJECT/'build/healing-budget-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        print('Verified three healing routines on both builds in bounded windows.')
    finally:old.stream.close();new.stream.close()


if __name__=='__main__':main()
