"""Targeted ability/effect/command audit against supplied CA docs and Lua source.

No game attachment, native hooks, mod installation or production-reader changes.
Named interfaces establish candidates; they do not establish live coverage.
"""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(P/'tools'))
from audit_mod_access import evidence, DOC


GROUPS = {
    'ability_state': (
        'CcoBattleUnit.BattleAbilityList', 'CcoBattleAbility.SetupAbilityContext',
        'CcoUnitAbility.RecordKey', 'CcoUnitAbility.Name', 'CcoUnitAbility.IsPassive',
        'CcoBattleAbility.RemainingUses', 'CcoBattleAbility.HasLimitedUses',
        'CcoBattleAbility.IsActive', 'CcoBattleAbility.CurrentState',
        'CcoBattleAbility.WindUpTimeRemainingSecs', 'CcoBattleAbility.RechargeTimeRemainingSecs',
        'CcoBattleAbility.CanCurrentlyPerform', 'CcoUnitAbility.HasSharedRechargeTimer'),
    'effect_timeline': (
        'CcoBattleUnit.ActiveEffectList', 'CcoBattleUnitEffect.Name',
        'CcoBattleUnitEffect.AbilityContext', 'CcoBattleUnitEffect.BattleAbilityContext',
        'CcoBattleUnitEffect.PhaseRecordContext', 'CcoBattleUnitEffect.StartTimeSeconds',
        'CcoBattleUnitEffect.TotalDurationSeconds', 'CcoBattleUnitEffect.TimeRemainingSeconds',
        'CcoBattleUnitEffect.Intensity', 'CcoBattleUnitEffect.IconPath',
        'CcoSpecialAbilityPhaseRecord.Key', 'CcoSpecialAbilityPhaseRecord.EffectType'),
    'commands': (
        'battle_manager:register_command_handler_callback',
        'battle_manager:unregister_command_handler_callback',
        'battle:register_command_handler', 'battle_unit:ordered_position',
        'battle_unit:current_target', 'CcoBattleUnit.IsSelected',
        'CcoBattleUnit.IsUnderMyControl', 'battle_army:is_player_controlled'),
    'provider_and_export': (
        'battle_unit:unique_ui_id', 'battle_manager:repeat_callback',
        'battle_manager:remove_callback', 'battle:time_elapsed_ms', 'global:ModLog'),
}


def main():
    verified = {group: [evidence(ref) for ref in refs] for group, refs in GROUPS.items()}
    library = P.parent/'Local-files/script/_lib'
    manager = (library/'lib_battle_manager.lua').read_text(encoding='utf-8')
    unit_lib = (library/'lib_battle_script_unit.lua').read_text(encoding='utf-8')
    prologue = (P.parent/'Local-files/script/battle/wh3_battle_prologue_values.lua').read_text(encoding='utf-8')
    loader = (library/'lib_mod_loader.lua').read_text(encoding='utf-8')
    checks = {
        'named_command_callbacks_add_to_shared_dispatcher': 'table.insert(self.command_handler_callback_list[command_name], callback_record)' in manager,
        'dispatcher_passes_context_without_actor_argument': 'commands_to_call[i](command_context)' in manager,
        'unit_uid_to_cco_used_by_vanilla_library': 'cco("CcoBattleUnit", self.unit:unique_ui_id())' in unit_lib,
        'cco_list_expression_used_by_vanilla_script': '"AbilityList.At("..i..").RecordKey"' in prologue,
        'normal_battle_mod_loader_path': '"/script/battle/mod/"' in loader,
    }
    assert all(checks.values()), checks
    command_candidates = {
        'Move': ['event name'],
        'Move Orientation Width': ['event name'],
        'Move Rotation Angle': ['event name'],
        'Attack Unit': ['event name', 'fast/running flag', 'target unit'],
        'Special Ability': ['event name', 'ability key'],
        'Halt': ['event name'],
        'Withdraw': ['event name', 'fast/running flag'],
        'Change Formation': ['event name', 'formation name'],
        'Change Melee': ['event name', 'enabled flag'],
        'Change Skirmish': ['event name', 'enabled flag'],
        'Fire At Will': ['event name'],
    }
    command_doc = (DOC/'script/battle/battle.html').read_text(encoding='utf-8')
    for name in command_candidates:
        assert name in command_doc, name
    result = dict(status='documentation and vanilla-source verified; no live mod test',
        verified_interfaces=verified, vanilla_source_checks=checks,
        documented_command_payloads=command_candidates,
        findings={
            'effects': 'Strong candidate for sampled per-unit timelines, including phase key, polarity, intensity and native timing. Runtime list coverage/clock/instance identity need testing.',
            'ability_uses': 'Limited-use consumption and active/casting/cooldown state are exposed. A command, charge decrease or cooldown transition alone does not prove a successful cast.',
            'commands': 'Named callbacks can record supported command notifications at event time. Actor identity, player-versus-script origin, destinations, queues, repeats and multiplayer coverage are unverified.',
            'architecture': 'Keep the existing read-only reader for current native fields. A normal Lua companion can supply additional supported snapshots/events through a tagged export, subject to runtime validation.',
            'bounds': 'Use simulation time and the existing 1Hz snapshot cadence. Preserve unknowns, sampling gaps and incomplete effect endpoints; do not infer casts, actors or effect sources without evidence.'})
    destination = P/'build/timeline-access-audit.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Verified {sum(map(len, GROUPS.values()))} named interfaces and {len(checks)} vanilla-source checks.')
    print('Ability/effect snapshots and command callbacks are promising; live coverage remains unverified.')


if __name__ == '__main__':
    main()
