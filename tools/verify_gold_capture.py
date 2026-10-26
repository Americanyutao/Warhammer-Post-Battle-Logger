"""Verify a per-credit capture point from existing evidence; never attach or hook.

Reads only the already identified functions at known addresses in both binaries.
The example histories are synthetic proofs of the information lost by polling,
not measurements or a new enabled collector.
"""
import json
from pathlib import Path
import struct
import sys

P = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(P/'build/decoder'), str(P/'tools')]
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from native_evidence import Image, ROOT

SOURCES = ('direct', 'melee', 'missiles', 'melee', 'melee', 'other')
RELATIONS = ('enemy', 'self', 'ally')


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def credit_history(hits):
    """Small accounting proof using the verified per-hit arguments and weights."""
    hp = {r: {s: 0 for s in set(SOURCES)} for r in RELATIONS}
    gold = {r: {s: 0.0 for s in set(SOURCES)} for r in RELATIONS}
    native_enemy_gold = 0.0
    for source, relation, amount, victim_weight in hits:
        category, relationship = SOURCES[source], RELATIONS[relation]
        credited = f32(f32(amount) * f32(victim_weight))
        hp[relationship][category] += amount
        gold[relationship][category] += credited
        if relationship == 'enemy':
            native_enemy_gold = f32(native_enemy_gold + credited)
    return dict(polled=dict(hp=hp, enemy_gold=native_enemy_gold), per_credit_gold=gold)


def information_loss_examples():
    # Same two targets lose 100 HP each. Swap which source hits which target.
    left = credit_history([(0, 0, 100, 1), (1, 0, 100, 2)])
    right = credit_history([(0, 0, 100, 2), (1, 0, 100, 1)])
    assert left['polled'] == right['polled']
    assert left['per_credit_gold']['enemy'] != right['per_credit_gold']['enemy']
    # Same friendly HP/source credit, differently valued victims.
    friendly_left = credit_history([(2, 2, 100, 1)])
    friendly_right = credit_history([(2, 2, 100, 3)])
    assert friendly_left['polled'] == friendly_right['polled']
    assert friendly_left['per_credit_gold']['ally'] != friendly_right['per_credit_gold']['ally']
    # Friendly/self credits must not enter enemy totals; all melee types combine.
    mixed = credit_history([(1, 0, 100, 1), (3, 0, 50, 2), (4, 0, 25, 4),
                            (2, 2, 100, 3), (0, 1, 10, 5)])
    assert mixed['polled']['enemy_gold'] == 300
    assert mixed['per_credit_gold']['enemy']['melee'] == 300
    assert sum(mixed['per_credit_gold']['ally'].values()) == 300
    assert sum(mixed['per_credit_gold']['self'].values()) == 50
    return dict(enemy_source_ambiguity=[left, right],
                friendly_valuation_ambiguity=[friendly_left, friendly_right],
                separate_relationship_accounting=mixed)


def main():
    evidence = json.loads((P/'build/damage-accounting-evidence.json').read_text())
    decoder = Cs(CS_ARCH_X86, CS_MODE_64)
    files = dict(reference=ROOT/'decompile project/Warhammer3.exe',
                 current=Path('C:/Program Files (x86)/Steam/steamapps/common/Total War WARHAMMER III/Warhammer3.exe'))
    result = dict(mode='static read-only verification; no game attachment or instrumentation',
                  builds={}, synthetic_examples=information_loss_examples())
    for version, path in files.items():
        image = Image(path)
        try:
            for name in ('result_add_damage', 'entity_damage_accounting'):
                item = evidence[name]
                assert image.read(int(item[version], 16), item['size']).hex() == item[version+'_hex'], (version, name)
            caller, writer = evidence['entity_damage_accounting'], evidence['result_add_damage']
            instructions = list(decoder.disasm(bytes.fromhex(caller[version+'_hex']), int(caller[version], 16)))
            calls = [i for i, x in enumerate(instructions) if x.mnemonic == 'call' and x.op_str == writer[version]]
            assert len(calls) == 1
            index = calls[0]
            window = [f'{x.mnemonic} {x.op_str}' for x in instructions[index-12:index+1]]
            for required in ('mulss xmm6, dword ptr [rax + 0x90]', 'movaps xmm2, xmm6',
                             'mov edx, ebx', 'mov rcx, qword ptr [r13 + 0x68]',
                             'mov dword ptr [rsp + 0x20], esi',
                             'mov dword ptr [rsp + 0x28], r11d'):
                assert required in window, (version, required)
            result['builds'][version] = dict(credit_entry=writer[version],
                entity_credit_call=hex(instructions[index].address), instructions=window,
                entry_arguments=dict(result_object='RCX', applied_hp='EDX', gold_float='XMM2',
                                     simulation_time_bits='R9D', source='[RSP+0x28]', relationship='[RSP+0x30]'))
        finally:
            image.stream.close()
    result['finding'] = ('Gold, source and relationship coexist at the result-credit function entry, '
        'including ally/self gold. Stored ally/self gold and gold source totals are absent from this writer. '
        'A per-credit collector could accumulate them before the branch discards them. '
        'No native hook or live-capture bridge has been implemented or performance-tested.')
    destination = P/'build/gold-capture-feasibility.json'
    destination.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print('Both existing build bindings verified at known addresses; 3 synthetic accounting checks pass.')
    print('Per-credit capture is feasible in principle. Runtime collection remains unimplemented.')


if __name__ == '__main__':
    main()
