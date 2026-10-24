"""Verify the already traced result-type getters and DB record layout."""
import csv
import json
from pathlib import Path
import sys

P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'tools'),str(P/'build/decoder')]
from native_evidence import Image, pattern, ROOT


def main():
    research=json.loads((P/'build/result-type-research.json').read_text(encoding='utf-8'))
    jobs=research['verified']
    extra={'record_constructor':0x1415754b8,'record_enum_from_key':0x1414b8170}
    with (ROOT/'Ghidra Static/Function Exports/ghidra_function_exports/function_manifest.csv').open(encoding='utf-8',newline='') as f:
        sizes={int(r['address'],16):int(r['size']) for r in csv.DictReader(f) if int(r['address'],16) in extra.values()}
    old=Image(ROOT/'decompile project/Warhammer3.exe')
    new=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    evidence={}
    try:
        jobs=dict(jobs)
        for name,address in extra.items():
            start=address-65536;size=sizes[address]
            hits=[start+m.start() for m in pattern(old,address,size).finditer(new.read(start,131072))]
            if len(hits)!=1:raise ValueError(name+' is not a unique bounded match.')
            jobs[name]=dict(reference=hex(address),current=hex(hits[0]),size=size)
        for name,job in jobs.items():
            address,current=int(job['reference'],16),int(job['current'],16);size=job['size']
            raw=new.read(current,size)
            if not pattern(old,address,size).fullmatch(raw):raise ValueError('Getter changed: '+name)
            evidence[name]=dict(reference=hex(address),current=hex(current),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=raw.hex())
        fields=dict(alliance_entries_offset=0x30,alliance_stride=0x60,type_offset=0x4c,
            record_offset=0x58,record_type_offset=0x18,evidence='build/result-type-evidence.json')
        for file in (P/'profiles').glob('*.json'):
            profile=json.loads(file.read_text(encoding='utf-8'))
            version='current' if 'current' in file.name else 'reference'
            for item in evidence.values():
                anchor=dict(address=item[version],hex=item[version+'_hex'])
                if anchor not in profile['anchors']:profile['anchors'].append(anchor)
            profile['result_type_fields']=fields
            file.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8')
        evidence['semantics']=dict(fields=fields,types=research['types'],
            validation='Results phase only; read local native alliance enum, require matching initialized DB record parsed enum at +18 and winner agreement. DB +10 is an interned key, not a flat byte string. Recheck entry, array pointer, result pointer and winner before accepting. Raw entry/record enums retained even when no qualified label can be confirmed.')
        (P/'build/result-type-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    finally:old.stream.close();new.stream.close()
    print('Verified seven result-type routines and bound both supported profiles.')


if __name__=='__main__':main()
