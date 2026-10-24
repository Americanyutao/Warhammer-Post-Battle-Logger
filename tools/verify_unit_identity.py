"""Verify the adjacent CcoBattleUnit -> main-unit record -> context-id path."""
import csv
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'build/decoder'))
import capstone
from native_evidence import Image, pattern, ROOT


def main():
    jobs={'unit_record_context':0x141ea1754,'main_unit_context_id':0x141f05d40,
          'unit_icon_path':0x141e7e6fc,'unit_icon_path_source':0x141f044e8}
    source=ROOT/'Ghidra Static/Function Exports/ghidra_function_exports/functions'
    assert '"UnitRecordContext"' in (source/'1402/14024fb20.c').read_text()
    assert 'FUN_1405cad10' in (source/'1402/14024fb20.c').read_text()
    assert '+ 0x168' in (source/'141e/141ea1754.c').read_text()
    assert '+ 0x3e0' in (source/'141f/141f05d40.c').read_text()
    with (ROOT/'Ghidra Static/Function Exports/ghidra_function_exports/function_manifest.csv').open(encoding='utf-8',newline='') as f:
        sizes={int(r['address'],16):int(r['size']) for r in csv.DictReader(f) if int(r['address'],16) in jobs.values()}
    old=Image(ROOT/'decompile project/Warhammer3.exe')
    new=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    result={}
    try:
        for name,address in jobs.items():
            size=sizes[address];start=address-0x10000
            hits=[start+m.start() for m in pattern(old,address,size).finditer(new.read(start,0x20000))]
            if len(hits)!=1:raise RuntimeError(f'{name}: {len(hits)} matches in bounded window')
            result[name]=dict(reference=hex(address),current=hex(hits[0]),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=new.read(hits[0],size).hex())
        for file in (P/'profiles').glob('*.json'):
            p=json.loads(file.read_text());v='current' if 'current' in file.name else 'reference'
            for item in result.values():
                anchor=dict(address=item[v],hex=item[v+'_hex'])
                if anchor not in p['anchors']:p['anchors'].append(anchor)
            p['unit_identity']=dict(record_offset=0x168,key_offset=0x3e0,setup_offset=0x158,portrait_offset=0x4e8,
                evidence='build/unit-identity-evidence.json')
            file.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8')
        (P/'build/unit-identity-evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    finally:old.stream.close();new.stream.close()
    print('Verified four named identity/icon routines in bounded windows on both builds.')


if __name__=='__main__':main()
