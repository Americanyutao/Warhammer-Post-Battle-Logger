"""Verify only the named unit-card getter chain, in bounded windows on both builds."""
import csv
import json
from pathlib import Path
import struct
import sys
P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'tools'),str(P/'build/decoder')]
from native_evidence import Image,pattern,ROOT

JOBS=dict(stat_mapping=(0x14014ef70,None),stat_context=(0x141c576e0,None),
    card_builder=(0x141c66420,None),stat_value=(0x1416724cc,None),
    integer_stat=(0x14148028c,None),
    card_adjustments=(0x141c4aa54,None),difficulty_display=(0x141c4b3bc,None),
    difficulty_scale=(0x141670ee8,None),fatigue_immune=(0x1414800a8,None),
    attribute_flag=(0x14146f860,None),fatigue_lookup=(0x1415cc2a0,47),
    database_context=(0x141d8447c,36),fatigue_table=(0x141533a8c,45),
    signed_round=(0x140531e54,31),float_round=(0x14141bbc4,39))


def main():
    exports=ROOT/'Ghidra Static/Function Exports/ghidra_function_exports'
    with (exports/'function_manifest.csv').open(encoding='utf-8',newline='') as f:
        sizes={int(r['address'],16):int(r['size']) for r in csv.DictReader(f) if int(r['address'],16) in {a for a,_ in JOBS.values()}}
    old=Image(ROOT/'decompile project/Warhammer3.exe')
    new=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    result={}
    try:
        for name,(address,size) in JOBS.items():
            size=size or sizes[address];start=address-65536
            hits=[start+m.start() for m in pattern(old,address,size).finditer(new.read(start,131072))]
            calls={'fatigue_lookup':0x141c4ae7a,'fatigue_table':0x141c4ae69,'float_round':0x141c4aeb6,'signed_round':0x141c4aec5}
            if len(hits)!=1 and name in calls:
                call=calls[name];assert old.instructions(call,5)[0].operands[0].imm==address
                current_call=int(result['card_adjustments']['current'],16)+call-0x141c4aa54
                target=new.instructions(current_call,5)[0].operands[0].imm
                assert pattern(old,address,size).fullmatch(new.read(target,size))
                hits=[target]
            if len(hits)!=1:raise RuntimeError(name+': '+str(len(hits))+' bounded matches')
            result[name]=dict(reference=hex(address),current=hex(hits[0]),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=new.read(hits[0],size).hex())
        # This folded getter moved outside its old neighbourhood. Follow its
        # named CCO registration and wrapper, never enlarge the executable scan.
        registration=0x1401b2bf0;size=397;offsets={}
        for i in old.instructions(registration,size):
            for o in i.operands:
                if o.type==3 and i.reg_name(o.mem.base)=='rip':
                    target=i.address+i.size+o.mem.disp
                    if old.read(target,15)==b'DisplayedValue\0':offsets['name']=i.address-registration
                    if target==0x141c4f1c8:offsets['wrapper']=i.address-registration
        candidates=[registration-65536+m.start() for m in pattern(old,registration,size).finditer(new.read(registration-65536,131072))]
        named=[]
        for candidate in candidates:
            i=new.instructions(candidate+offsets['name'],7)[0]
            if new.read(i.address+i.size+i.operands[1].mem.disp,15)==b'DisplayedValue\0':named.append(candidate)
        assert len(named)==1
        i=new.instructions(named[0]+offsets['wrapper'],7)[0]
        wrapper=i.address+i.size+i.operands[1].mem.disp
        target=new.instructions(wrapper+4,5)[0].operands[0].imm
        assert old.read(0x1415cbfe0,41)==new.read(target,41)
        result['display_clamp']=dict(reference=hex(0x1415cbfe0),current=hex(target),size=41,
            reference_hex=old.read(0x1415cbfe0,41).hex(),current_hex=new.read(target,41).hex(),
            current_named_registration=hex(named[0]),current_wrapper=hex(wrapper))
        for path in (P/'profiles').glob('*.json'):
            profile=json.loads(path.read_text(encoding='utf-8'));version='current' if 'current' in path.name else 'reference';im=new if version=='current' else old
            for r in result.values():
                anchor=dict(address=r[version],hex=r[version+'_hex'])
                if anchor not in profile['anchors']:profile['anchors'].append(anchor)
            instructions=im.instructions(int(result['database_context'][version],16),36)
            targets=[i.address+i.size+o.mem.disp for i in instructions for o in i.operands if o.type==3 and i.reg_name(o.mem.base)=='rip']
            assert len(targets)==2
            profile['globals'].update(statline_database_override=hex(targets[0]),statline_database_engine=hex(targets[1]))
            profile['statline_fields']=dict(current_offset=0x1b0,record_offset=0x168,stat_offset=0x68,stat_stride=12,
                stat_count=56,database_ready_offset=0x19d86,fatigue_table_offset=0x14078,
                evidence='build/statline-evidence.json')
            # Check the speed and rounding constants through their actual RIP targets.
            speed=int(result['stat_value'][version],16)+(0x1416728ed-0x1416724cc)
            i=im.instructions(speed,8)[0];target=i.address+i.size+i.operands[1].mem.disp
            assert struct.unpack('<f',im.read(target,4))[0]==10.
            profile['statline_fields']['speed_display_factor']=10.
            path.write_bytes((json.dumps(profile,indent=2)+'\n').encode('utf-8'))
        result['semantics']=dict(
            source='Current live unit attributes are UI unit+1b0, passed explicitly into the CcoUnitDetails card builder; no selection-dependent context lookup or game calls.',
            stats='Integer stat = max(round_half_away(base+add),round_half_away(minimum)); armour adds shield armour; defence adds shield defence; weapon strength sums base/AP. Speed follows record+500 entity/mount/engine speed, current scalar, and the verified display factor10.',
            adjustments='Card applies fatigue: round(current)*native fatigue multiplier unless the corresponding immunity flag suppresses a penalty; then the live army difficulty factor for charge/attack/defence/weapon strength. Unbreakable leadership is100. Display clamps use ui_unit_stats definitions.',
            retention='Store exact observed stat snapshots; paused timestamps replace, unknowns remain unknown, and known recording gaps do not create interpolated stats.')
        (P/'build/statline-evidence.json').write_bytes((json.dumps(result,indent=2)+'\n').encode('utf-8'))
    finally:old.stream.close();new.stream.close()
    print('Verified16 unit-card/stat display routines on both builds.')


if __name__=='__main__':main()
