"""Bounded verification of the game's effect-rate display and sampled intensity."""
import csv
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(P/'tools'),str(P/'build/decoder')]
from native_evidence import Image,pattern,ROOT

JOBS=dict(effect_intensity=0x141e808b8,intensity_lookup=0x141e48d4c,
    damage_per_second=0x141edc220,battle_damage_scale=0x141c64ff0,
    intensified_integer_range=0x141ee81f4,intensified_float=0x141ee8514,
    effect_context_id=0x141e84cd4,effect_stat_list=0x141edcaa4,
    stat_effect_formatter=0x141f8f7c0,stat_intensity=0x14141a93c)


def main():
    exports=ROOT/'Ghidra Static/Function Exports/ghidra_function_exports'
    with (exports/'function_manifest.csv').open(encoding='utf-8',newline='') as stream:
        sizes={int(r['address'],16):int(r['size']) for r in csv.DictReader(stream) if int(r['address'],16) in JOBS.values()}
    ui=ROOT/'Local-files/ui/common ui/special_ability_tooltip.twui.xml'
    xml=ui.read_text(encoding='utf-8')
    assert 'IntensifiedRangeIntValueText(DamagePerSecond, &quot;%d-%d&quot;, 0.5)' in xml
    assert 'IntensifiedValueText(TotalHealPercent *100 / MaxNumericValue(Duration, 1.0)' in xml
    reference=Image(ROOT/'decompile project/Warhammer3.exe')
    current=Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    evidence={}
    try:
        jobs=dict(JOBS,total_heal=0x141eee34c)
        for name,address in jobs.items():
            size=sizes.get(address,0x66);start=address-65536
            hits=[start+m.start() for m in pattern(reference,address,size).finditer(current.read(start,131072))]
            if len(hits)!=1:raise ValueError(name+': non-unique bounded match')
            evidence[name]=dict(reference=hex(address),current=hex(hits[0]),size=size,
                reference_hex=reference.read(address,size).hex(),current_hex=current.read(hits[0],size).hex())
        for file in (P/'profiles').glob('*.json'):
            profile=json.loads(file.read_text(encoding='utf-8'));version='current' if 'current' in file.name else 'reference'
            for item in evidence.values():
                anchor=dict(address=item[version],hex=item[version+'_hex'])
                if anchor not in profile['anchors']:profile['anchors'].append(anchor)
            profile['effect_fields'].update(intensity_offset=0x44,instance_key_offset=0,start_time_offset=0x3c,
                settings_damage_scale_offset=0x100,rate_evidence='build/effect-rate-evidence.json')
            file.write_bytes((json.dumps(profile,indent=2)+'\n').encode('utf-8'))
        evidence['semantics']=dict(
            damage='DPS base = trunc(trunc(damage_amount * max(1,max_damaged_entities) / positive hp_change_frequency) * battle settings+100 float); intensity formatter truncates base*intensity, then shows trunc(upper*0.5)-upper.',
            healing='HealPercent is a max-HP fraction per hp_change_frequency. TotalHealPercent multiplies by floor(duration/frequency) for positive duration/frequency, otherwise returns HealPercent; UI shows total/max(duration,1) with intensity applied.',
            intensity='CcoBattleUnitEffect.Intensity finds the entry in UI unit+600 and reads float+44. Preserve each native entry, its key-pointer identity and per-tick intensity; do not sum same-name effects.',
            scale='141c64ff0 returns XMM0 float; in battle it reads roster+98 settings+100. Do not interpret the inaccurate decompiler integer return type as a unit-size enum.',
            stat_intensity='141edcaa4 ->141f8f7c0 ->14141a93c: additive modifier multiplied by intensity; multiplicative modifier (base-1)*intensity+1.',
            limits='These are configured UI effects, not measured damage/healing. Old captures lack intensity and damage-scale readings; show explicit base values.')
        (P/'build/effect-rate-evidence.json').write_bytes((json.dumps(evidence,indent=2)+'\n').encode('utf-8'))
    finally:reference.stream.close();current.stream.close()
    print('Verified eleven effect intensity/rate display routines on both builds.')


if __name__=='__main__':main()
