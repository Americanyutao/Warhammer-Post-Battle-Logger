"""Bounded verification of nearby flat ammo/leadership and scripted healing."""
import csv
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'build/decoder'))
import capstone
from native_evidence import Image,pattern,ROOT


def main():
    jobs={'ammo_pool_initialization':0x14301a16c,'ammo_pool_scale':0x143014888,'ammo_fraction':0x14303bd30,'morale_percentage':0x141e83cf4,
        'morale_current_update':0x1430253fc,'script_heal_amount':0x142ed08bc,
        'script_set_health':0x142ed15b0}
    with (ROOT/'Ghidra Static/Function Exports/ghidra_function_exports/function_manifest.csv').open(encoding='utf-8',newline='') as f:
        sizes={int(r['address'],16):int(r['size']) for r in csv.DictReader(f) if int(r['address'],16) in (*jobs.values(),0x143034ca0)}
    old=Image(ROOT/'decompile project/Warhammer3.exe')
    new=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    evidence={}
    try:
        ins=old.instructions(0x143034ca0,sizes[0x143034ca0])
        i=next(i for i,a in enumerate(ins) if '0x3d90' in a.op_str)
        # This short writer block ties both ammo pools to the cached fractions.
        start=ins[i].address;end=next(a.address+a.size for a in ins[i:] if '0x6c8' in a.op_str)
        jobs['ammo_cache_writer']=start;sizes[start]=end-start
        for name,address in jobs.items():
            size=sizes[address];low=address-0x10000
            hits=[low+m.start() for m in pattern(old,address,size).finditer(new.read(low,0x20000))]
            if len(hits)!=1:raise RuntimeError(f'{name}: {len(hits)} bounded matches')
            evidence[name]=dict(reference=hex(address),current=hex(hits[0]),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=new.read(hits[0],size).hex())
        for file in (P/'profiles').glob('*.json'):
            p=json.loads(file.read_text());version='current' if 'current' in file.name else 'reference'
            for item in evidence.values():
                anchor=dict(address=item[version],hex=item[version+'_hex'])
                if anchor not in p['anchors']:p['anchors'].append(anchor)
            p['report_fields']=dict(primary_ammo_offset=0x3d90,secondary_ammo_offset=0x3da0,
                ammo_current_offset=0,ammo_start_offset=4,ammo_max_offset=8,morale_adapter_offset=0x160,leadership_offset=0x48,
                evidence='build/report-field-evidence.json')
            file.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8')
        (P/'build/report-field-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('Verified eight bounded routines/blocks on both builds; no broad scan.')
    finally:old.stream.close();new.stream.close()

if __name__=='__main__':main()
