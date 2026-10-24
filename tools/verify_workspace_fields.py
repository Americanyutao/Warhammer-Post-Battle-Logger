"""Bounded verification of adjacent fatigue, rank, departure and result fields."""
import csv
import json
from pathlib import Path
import sys

P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P/'build/decoder'))
import capstone
from native_evidence import Image, pattern, ROOT


def main():
    jobs = {
        'result_hp_writer': (0x1430149a4, None),
        'result_hp_sum': (0x1431013e0, None),
        'result_hp': (0x1408daba0, 32),
        'result_initial_hp': (0x1408dd870, 32),
        'result_models': (0x1408dd3e0, 32),
        'result_initial_models': (0x1408dd830, 32),
        'exit_reason_writer': (0x1430397d4, None),
        'character_rank': (0x1408e1a20, 18),
        'has_character_rank': (0x141e7d214, 23),
        'character_rank_type': (0x142e307d8, None),
        'fatigue_names': (0x141be6380, None),
        'fatigue_unit_average': (0x1430421a4, 0x15f),
        'fatigue_clamp': (0x1430859b0, None),
        'fatigue_tiers': (0x14166fd38, None),
        'fatigue_rules': (0x141507ef8, None),
        'awaiting_rally_order': (0x141e80c24, None),
        'unit_left_battlefield': (0x1408dd320, 12),
        'results_phase': (0x141e81d48, 32),
        'result_context': (0x141e930c4, None),
        'result_draw': (0x141c87194, 12),
        'result_local_winner': (0x141c87250, 14),
    }
    with (ROOT/'Ghidra Static/Function Exports/ghidra_function_exports/function_manifest.csv').open(encoding='utf-8', newline='') as f:
        sizes = {int(r['address'],16):int(r['size']) for r in csv.DictReader(f) if int(r['address'],16) in {a for a,_ in jobs.values()}}
    old = Image(ROOT/'decompile project/Warhammer3.exe')
    new = Image('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe')
    result = {}
    try:
        for name, (address, size) in jobs.items():
            size = size or sizes[address]
            start = address-0x10000
            hits = [start+m.start() for m in pattern(old,address,size).finditer(new.read(start,0x20000))]
            if len(hits) != 1: raise RuntimeError(f'{name}: {len(hits)} matches in bounded window')
            result[name] = dict(reference=hex(address),current=hex(hits[0]),size=size,
                reference_hex=old.read(address,size).hex(),current_hex=new.read(hits[0],size).hex())
        for file in (P/'profiles').glob('*.json'):
            p = json.loads(file.read_text())
            v = 'current' if 'current' in file.name else 'reference'
            for item in result.values():
                anchor = dict(address=item[v],hex=item[v+'_hex'])
                if anchor not in p['anchors']: p['anchors'].append(anchor)
            p['terminal_fields'] = dict(result_hp=0xb4,result_initial_hp=0xb0,result_models=0xa0,result_initial_models=0x9c,result_exit_reason=0xe4)
            p['workspace_fields'] = dict(setup_offset=0x158,character_rank_offset=0x518,
                character_rank_type_offset=0x51c,fatigue_offset=0x3c10,
                awaiting_rally_offset=0x725,left_battlefield_offset=0xe2,
                phase_offset=0xc8,result_offset=0xa0,result_winner_offset=4,
                local_alliances_offset=0x3a8,local_alliance_index_offset=0x3b4,
                evidence='build/workspace-fields-evidence.json')
            file.write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8')
        result['semantics'] = dict(fatigue='Native +3c14 is integer mean of entity +704 fatigue points; native +3c10 is mean of entity +708 tier. Six named native tiers 0..5. Maximum is the points ceiling, not a seventh engine tier.',
            rally='Raw UI +725 is set on routing exit. Log this underlying state, omitting the CCO local-control display filter; idle-after-rally additionally requires idle and excludes routing/shattered/withdrawing/dead.',
            outcome='Accept winner/draw only in verified results phase 8. ResultContext +8 is local_30, from roster +a0; roster +98 is context +10 and is not the winner object. Compare winner with the native local alliance index, not the one-based logger roster.',
            rules='First retained entity -> +58 -> +440 -> +8 -> +430 -> +20 -> +187c8; read-only initialized rule table, thresholds +830 +104*i, i=0..6. No initializer calls.')
        (P/'build/workspace-fields-evidence.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    finally:
        old.stream.close();new.stream.close()
    print('Verified 21 named routines in bounded windows on both builds.')


if __name__ == '__main__': main()
