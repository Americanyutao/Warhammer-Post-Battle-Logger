"""Read-only documentation audit; writes evidence only inside battle-logger.

Uses the actual normalized fixture to check that every collected field is covered.
No game attachment, injection, mod installation, executable scan or live Lua calls.
"""
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from collections import Counter

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[1]
DOC = P.parent / 'Local-files/documentation'
sys.path[:0] = [str(P/'src'), str(P/'tests')]
from fixtures import BattleFixture
from aggregate import STATES


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', value))).strip()


def contexts():
    source = (DOC/'ui/documentation.html').read_text(encoding='utf-8')
    starts = list(re.finditer(r'<a\s+id\s*=\s*"(Cco[^\"]+)"\s*><h3>', source))
    result = {}
    for i, match in enumerate(starts):
        chunk = source[match.end():starts[i+1].start() if i+1 < len(starts) else len(source)]
        rows = {}
        for row in re.findall(r'<tr>(.*?)</tr>', chunk, re.S):
            cells = [clean(c) for c in re.findall(r'<td>(.*?)</td>', row, re.S)]
            if len(cells) >= 4:
                rows[cells[0]] = dict(zip(('name','returns','arguments','description','tags','events'), cells))
        result[match[1]] = rows
    return result


CCO = contexts()
script_pages = {}


def evidence(ref):
    if ref.startswith('Cco'):
        context, method = ref.split('.', 1)
        assert method in CCO[context], ref
        return dict(reference=ref, source='ui/documentation.html', section=context, **CCO[context][method])
    page, method = ref.split(':', 1)
    if page not in script_pages:
        source = (DOC/f'script/battle/{page}.html').read_text(encoding='utf-8')
        anchors = list(re.finditer(r'(?:id|name)\s*=\s*[\"\'](function:[^\"\']+)', source))
        script_pages[page] = {m[1].rsplit(':', 1)[1]: clean(source[m.end():anchors[i+1].start()
                if i+1 < len(anchors) else len(source)]) for i, m in enumerate(anchors)}
    assert method in script_pages[page], ref
    return dict(reference=ref, source=f'script/battle/{page}.html', section=f'function:{page}:{method}',
                description=script_pages[page][method])


ROWS = []


def row(scope, keys, status, access, limitation, *refs):
    ROWS.append(dict(scope=scope, fields=keys.split(), status=status, access=access,
                     limitation=limitation, evidence=[evidence(r) for r in refs]))


row('unit', 'id', 'provider', 'Assign a battle-local id using Lua unique_ui_id and retained incarnation bookkeeping.',
    'Native address strings are implementation identifiers, not a required game stat. UID recycling/lifetime needs a summon/reinforcement test.', 'battle_unit:unique_ui_id')
row('unit', 'unit_key portrait_path', 'documented', 'CcoBattleUnit.UnitRecordContext / IconPath', 'Revision5 adds database and portrait identity; raw portrait source is normalized to the unit-card path. Runtime Lua comparison remains pending.', 'CcoBattleUnit.UnitRecordContext', 'CcoBattleUnit.IconPath')
row('unit', 'uid', 'documented', 'unit:unique_ui_id() / CcoBattleUnit.UniqueUiId',
    'Documented unique within the battle; retain identity through temporary missing observations.', 'battle_unit:unique_ui_id', 'CcoBattleUnit.UniqueUiId')
row('unit', 'name', 'documented', 'CcoBattleUnit.Name and CustomName',
    'Preserve custom-name precedence. Lua unit:name() is a script name, not necessarily the localized UI label.', 'CcoBattleUnit.Name', 'CcoBattleUnit.CustomName')
row('unit', 'army alliance side', 'documented', 'ArmyContext.UniqueID / AllianceIndex; compare against the local alliance.',
    'Use stable logical ids instead of memory addresses; normalize Lua versus CCO index conventions.', 'CcoBattleUnit.ArmyContext', 'CcoBattleArmy.UniqueID', 'CcoBattleArmy.AllianceIndex', 'battle:local_alliance')
row('unit', 'controlled', 'documented', 'CcoBattleUnit.IsUnderMyControl',
    'Test unit gifting and multiplayer shared control; player-owned and locally controlled are distinct.', 'CcoBattleUnit.IsUnderMyControl')
row('unit', 'alive', 'documented', 'CcoBattleUnit.IsAlive',
    'A missing unit or invalid target must not be converted to death.', 'CcoBattleUnit.IsAlive')
row('unit', 'cache_eligible', 'documented', 'CcoBattleUnit.IsVisible reads the same +0x6f4 flag used by the reader.',
    'This flag gates UI cache updates. Do not use it alone as opposite-alliance visibility. Existing saved registration 140238b90 and verified getter anchor establish the match.', 'CcoBattleUnit.IsVisible')
row('unit', 'cache_active', 'provider', 'No documented getter for the exact +0x6fb update gate was found.',
    'Collection-quality flag, not a player stat. A Lua provider needs explicit availability/freshness handling; IsAlive is not a proven substitute.')
row('unit', 'damage gold_damage kills', 'documented', 'BattleResultUnitContext.DamageDealt / DamageDealtCost / NumKills',
    'Live-unit result-context constructor 141e5fe28 points to the same UNIT+0x68 result data read externally; its installed match is already anchored. Runtime Lua query/lifetime still needs testing.',
    'CcoBattleUnit.BattleResultUnitContext', 'CcoBattleResultUnit.DamageDealt', 'CcoBattleResultUnit.DamageDealtCost', 'CcoBattleResultUnit.NumKills')
row('unit', 'damage_by_source', 'no_interface', 'No exposed equivalent found for native result+0x20 six-source × three-relationship counters.',
    'Covers ability, melee, missile, charge, melee_collision and other, each against enemy/self/ally. Recent-damage windows, effect definitions, kills and firing flags cannot reproduce these cumulative counters.')
row('unit', 'damage_sources_consistent', 'blocked_by_input', 'Sum/check the six enemy counters against damage, as now.',
    'Unavailable if the source table is unavailable; never mark a missing breakdown consistent.')
for keys, query in [
        ('health_percent','HealthPercent'), ('hp_cached','HealthValue'), ('hp_max_cached','HealthMax'),
        ('models','NumEntities'), ('models_initial','NumEntitiesInitial'), ('barrier_hp','BarrierHp'),
        ('barrier_max','BarrierMaxHp'), ('firing','IsFiringMissiles'), ('flying','IsFlying'),
        ('idle','IsIdle'), ('melee','IsInMelee'), ('routing','IsRouting'), ('running','IsRunning'),
        ('walking','IsWalking'), ('withdrawing','IsWithdrawing'), ('under_missile','IsUnderMissileAttack'),
        ('fatigue_state','FatigueState'), ('morale_state','MoraleState'), ('shattered','IsShattered'),
        ('spawned','IsSpawnedUnit'), ('hidden_raw','IsHidden'),
        ('primary_ammo_fraction','PrimaryAmmoPercent'), ('secondary_ammo_fraction','SecondaryAmmoPercent'),
        ('healing_ceiling_fraction_raw','MaxHealthPercentCanReplenish'), ('regen_base_raw','HealthReplenishRateBase')]:
    caveat = 'Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units.'
    if keys == 'healing_ceiling_fraction_raw':
        caveat = 'Exact legacy display value, including the multi-model clamp in 143034ca0. Does not expose the new unclamped native healing budget.'
    elif keys == 'regen_base_raw':
        caveat = 'Base replenishment-rate value only; it is not verified actual HP received per second.'
    elif keys in ('models','models_initial'):
        caveat += ' Prefer matching CCO entity counts; Lua soldier counts can differ in meaning for artillery/mounts/handlers.'
    row('unit', keys, 'documented', 'CcoBattleUnit.'+query, caveat, 'CcoBattleUnit.'+query)
row('unit', 'grounded', 'derived', 'not flying, preserving unknowns.', 'Same calculation as the external provider.', 'CcoBattleUnit.IsFlying')
row('unit', 'character_level has_character_rank', 'documented', 'CcoBattleUnit.CharacterRank / HasCharacterRank',
    'Revision6 reads the exact rank getters. A missing rank is not reconstructed; report valuation explicitly assumes level 1 when needed.', 'CcoBattleUnit.CharacterRank', 'CcoBattleUnit.HasCharacterRank')
row('unit','fatigue_state_native','partial','CcoBattleUnit.FatigueState uses the UI cache of native averaged state.',
    'External reads native +3c10 next to points, avoiding UI cache lag. The state is a truncated mean of model states, not a tier derived from mean points.','CcoBattleUnit.FatigueState')
row('unit', 'fatigue_points', 'no_interface', 'No equivalent continuous-fatigue getter found for native +0x3c14.',
    'The native value is mean retained-model fatigue points. FatigueState and FatigueName are discrete states, not a points counter.', 'CcoBattleUnit.FatigueState', 'CcoBattleUnit.FatigueName')
for key, query in [('result_hp','NumHitPoints'),('result_initial_hp','NumHitPointsInitial'),('result_models','NumEntities'),('result_initial_models','NumEntitiesInitial')]:
    row('unit',key,'documented','CcoBattleResultUnit.'+query,'Native result counts; final HP sums current surviving model health. Require initialized final results.','CcoBattleResultUnit.'+query)
row('unit','result_exit_reason','no_interface','Native result +0xe4 classification.','No equivalent documented getter verified; leave ambiguous exits unresolved.')
row('unit', 'left_battlefield', 'documented', 'BattleResultUnitContext.DidLeaveBattlefield',
    'Same result+0xe2 getter. Observed true for destroyed Vampire Counts units too: it does not identify retreat rather than death. Reports use Dead / retreated.', 'CcoBattleUnit.BattleResultUnitContext', 'CcoBattleResultUnit.DidLeaveBattlefield')
row('unit', 'awaiting_order_after_rally_raw', 'partial', 'CcoBattleUnit.IsAwaitingOrderAfterRally',
    'External collector logs the underlying +0x725 state without the getter’s local-control display filter. The exposed getter therefore is not equivalent for every enemy unit.', 'CcoBattleUnit.IsAwaitingOrderAfterRally')
row('unit', 'xyz', 'documented', 'unit:position(), then battle_vector:get_x/get_y/get_z; alternatively CCO Position.',
    'Y is elevation; X/Z are ground coordinates. Keep flying altitude and all-army extrema. CCO Vector4-to-Lua conversion needs a test; battle_vector avoids that dependency.',
    'battle_unit:position', 'battle_vector:get_x', 'battle_vector:get_y', 'battle_vector:get_z', 'CcoBattleUnit.Position')
row('unit', 'out_of_opponents_vision', 'derived', 'Combine unit:is_hidden() and is_visible_to_alliance() for all opposing alliances.',
    'Same intended per-opponent LOS semantics; CCO IsVisible alone is local-player facing. Test all enemies, off-camera units and multiplayer.',
    'battle_unit:is_hidden', 'battle_unit:is_visible_to_alliance', 'battle:alliances')
row('unit', 'healing_budget_remaining_hp healing_budget_unlimited', 'no_interface',
    'No matching getter found for native stats+0x264 remaining budget or +0x268 unlimited flag.',
    'Do not substitute 75% of max HP, the clamped display ceiling, base regen or configured heal amounts. The fixed summon starting ceiling does not recover its current budget.')
row('unit', 'healing_budget_ceiling_hp healing_budget_remaining_fraction', 'blocked_by_input',
    'HP + native remaining budget; native remaining budget / maximum HP.',
    'Exact multi-model values depend on the unavailable native budget. Legacy single-entity display ceiling permits a limited estimate, without the unlimited-budget guard.')
row('unit', 'primary_ammo', 'partial', 'unit:ammo_left() documents a live ammunition count.',
    'Candidate for the primary pool; the docs do not identify pool or count units. Must compare to native pool+0 current across infantry/artillery/mixed-ammo units.', 'battle_unit:ammo_left')
row('unit','primary_ammo_start','partial','unit:starting_ammo() is the native initial pool candidate.',
    'External collector reads native primary pool +4, initialized alongside current/max. Compare Lua count units at runtime.','battle_unit:starting_ammo')
row('unit','secondary_ammo_start','no_interface','Native secondary initial pool +4.',
    'No verified secondary starting-count getter in the exposed interface.')
row('unit', 'primary_ammo_max', 'partial', 'unit:starting_ammo() documents starting ammunition.',
    'Starting ammunition is not proven identical to the current native pool maximum (+8), especially after modifiers or capacity changes.', 'battle_unit:starting_ammo')
row('unit', 'secondary_ammo secondary_ammo_max', 'no_interface', 'SecondaryAmmoPercent exists, but no live secondary count/maximum getter was found.',
    'CcoUnitLandRecord.SecondaryAmmo is a database value, not the live pool capacity. Percent × guessed capacity is not an equivalent measurement.',
    'CcoBattleUnit.SecondaryAmmoPercent', 'CcoUnitLandRecord.SecondaryAmmo')
row('unit', 'leadership', 'partial', 'Candidates: UnitDetailsContext.StatContextFromKey(...).Value and MoralePercent.',
    'No direct signed-current-leadership getter was found. MoralePercent subtracts a threshold and normalizes to best morale; for unbreakable units it can return the best value instead of raw current. A stat-panel Value needs key/meaning/clamp verification. Campaign CurrentMorale and database Morale are not replacements.',
    'CcoBattleUnit.MoralePercent', 'CcoBattleUnit.UnitDetailsContext', 'CcoUnitDetails.StatContextFromKey', 'CcoUnitStat.Value', 'CcoUnitStat.DisplayedValue')

row('army', 'id alliance side', 'documented', 'CcoBattleArmy.UniqueID / AllianceIndex; compare to local alliance.',
    'Normalize identifiers; original addresses are unnecessary.', 'CcoBattleArmy.UniqueID', 'CcoBattleArmy.AllianceIndex', 'battle:local_alliance')
row('army', 'current reserve maximum', 'partial', 'ArmyContext.WindsOfMagicPoolContext.CurrentWind / ReserveWind / MaxWind',
    'Known getter machine code converts each stored float to an integer (cvttss2si). Suitable for whole-point charts, not equivalent fractional pools or +0.1/s generation analysis. Documentation leaves these return types Void.',
    'CcoBattleArmy.WindsOfMagicPoolContext', 'CcoBattleWindsOfMagicPool.CurrentWind', 'CcoBattleWindsOfMagicPool.ReserveWind', 'CcoBattleWindsOfMagicPool.MaxWind')
row('army', 'recharge recharge_seconds_per_point', 'documented', 'WindsOfMagicPoolContext.CurrentRechargePerSecond',
    'Despite its name, the verified getter computes 1 / native recharge rate: seconds per point. Zero/infinite/disabled cases must remain explicit.',
    'CcoBattleWindsOfMagicPool.CurrentRechargePerSecond', 'CcoBattleWindsOfMagicPool.IsEnabled')
row('army', 'recharge_per_second', 'partial', 'Invert the verified reciprocal getter for positive finite values.',
    'Reconstructed Winds/s, not a direct read of the native float; guard zero/infinite/disabled values and preserve provenance.', 'CcoBattleWindsOfMagicPool.CurrentRechargePerSecond')
row('sample', 'schema kind', 'provider', 'Emit the existing schema-1 sample envelope.', 'Provider metadata; no game access required.')
row('sample', 'sim_s', 'documented', 'battle:time_elapsed_ms() / 1000',
    'Documented model time, matching pause/speed semantics. Mod timers can use simulation cadence; current external polling uses wall cadence, so schedules may differ.',
    'battle:time_elapsed_ms', 'battle:register_repeating_timer')
row('sample', 'unreadable_units', 'provider', 'Count failed/absent Lua/CCO readings.', 'Provider-specific diagnostics; not a native gameplay counter.')
row('sample', 'battle_result', 'documented', 'CcoBattleRoot.IsResultsPhase / ResultContext.IsDraw / IsLocalPlayerWinner',
    'Winner/loser/draw is accepted only in results phase. Lua output must preserve the unknown outcome when capture stops earlier.', 'CcoBattleRoot.IsResultsPhase', 'CcoBattleRoot.ResultContext', 'CcoBattleResult.IsDraw', 'CcoBattleResult.IsLocalPlayerWinner')
row('sample', 'fatigue_rules', 'no_interface', 'No exposed getter found for the initialized runtime fatigue threshold table.',
    'Supplied _kv_fatigue_tables provides base thresholds, but a bundled static copy cannot promise the same values as a modified runtime rule table.')


DERIVED = [
    ('State durations, including grounded/hidden/routing/missile fire', 'available', 'Boolean state inputs + simulation time; same sampled overlap/gap caveats.'),
    ('First observed engagement (retired)', 'available', 'Inputs remain exposed, but the external logger no longer computes this statistic.'),
    ('Movement path, occupancy, elevation, shared map bounds', 'available', 'XYZ + clock; travel-distance totals retired. Retain extrema before history downsampling.'),
    ('Observed rallies and landings', 'available', 'Routing/flying transitions with current alive/shattered/withdrawal guards; still sampled.'),
    ('Idling time after rallies', 'partial', 'Idle plus awaiting-order state and routing/shattered/withdrawal/alive guards. Exposed CCO waiting getter has an additional local-control display filter.'),
    ('HP/barrier net falls and rises', 'available', 'Current values + consecutive timestamps; model gains/losses retired.'),
    ('Total damage, gold totals, DPS and damage tempo', 'available', 'Result-context totals + timestamps. Live query needs runtime validation.'),
    ('Firing-state versus other-state damage estimate', 'available', 'Total damage + firing state; does not recover native damage categories.'),
    ('Ability/melee/missile/charge/collision/other damage and percentages', 'blocked', 'Native source table has no known exposed equivalent.'),
    ('Friendly fire and self damage', 'blocked', 'Enemy/ally/self source-table columns have no known exposed equivalent.'),
    ('Calculated damage taken and healing received, all units', 'blocked', 'Full implementation depends on the unclamped healing budget. Legacy single entities permit only the existing restricted estimate.'),
    ('Summon damage before first observation', 'blocked', 'Assumed initial 1.75 ceiling is available, but current unclamped ceiling still needs the native budget.'),
    ('Flat ammo timelines', 'partial', 'Primary count candidate exists; current maximum and both secondary fields remain unverified/unavailable.'),
    ('Signed leadership timeline', 'partial', 'Requires verifying a signed raw stat-panel query; morale state/normalized percentage are already exposed.'),
    ('Winds versus reserves chart', 'partial', 'Whole-point pool chart available; fractional precision is lost through known CCO getters.'),
    ('Trade: gold damage / unit value', 'available', 'Gold numerator exposed; keep current manual/unambiguous static-price denominator. Exact actual purchase value remains unverified.'),
    ('Last observed status; HP/model counts; summon labels', 'available', 'Documented CCO flags/counts; missing units remain unknown.'),
]


def main():
    fixture = BattleFixture()
    frame = fixture.reader.normalized(fixture.sample())
    expected = dict(unit=set(frame['units'][0]), army=set(frame['armies'][0]), sample=set(frame)-{'units','armies'})
    for scope, keys in expected.items():
        listed = [key for r in ROWS if r['scope']==scope for key in r['fields']]
        assert len(listed)==len(set(listed)), (scope, 'duplicate entries')
        assert set(listed)==keys, (scope, 'missing', keys-set(listed), 'extra', set(listed)-keys)
    profile = json.loads((P/'profiles/wh3_current_build.json').read_text())
    assert set(profile['logger_fields']).issubset(expected['unit'])
    assert (set(STATES)-{'idle_after_rally','retreating_combined'}).issubset(expected['unit'])
    evidence_files = ['ui/documentation.html'] + [f'script/battle/{p}.html' for p in sorted(script_pages)]
    fingerprints = {p:hashlib.sha256((DOC/p).read_bytes()).hexdigest() for p in evidence_files}
    # Validate precision findings against existing installed-build instruction anchors;
    # no new executable/xref scan is needed.
    import struct
    pool_evidence = []
    for label, offset in [('current',0xac),('reserve',0xbc),('maximum',0xb0)]:
        needle = bytes.fromhex('f30f2c90') + struct.pack('<I', offset)
        matches = [a for a in profile['anchors'] if needle in bytes.fromhex(a['hex'])]
        assert len(matches)==1, (label, len(matches))
        pool_evidence.append(dict(field=label, address=matches[0]['address'], hex=matches[0]['hex'],
            meaning='cvttss2si edx, [rax+offset]: truncate stored float before returning UI value'))
    counts = {scope:dict(Counter(r['status'] for r in ROWS if r['scope']==scope for _ in r['fields'])) for scope in expected}
    report = dict(date='2026-10-23', runtime_tested=False,
        scope='Normal Workshop Lua + game UI context interfaces; no DLL, memory reader, driver or injection.',
        status_meaning=dict(documented='Named interface exists; not yet exercised by our mod in battle.',
            partial='Candidate access or precision/semantics differ; not an equivalent field yet.',
            no_interface='No matching exposed getter found in audited interfaces; not proof impossible.',
            blocked_by_input='Calculation depends on an unavailable input.',
            derived='Existing calculation can use documented inputs.', provider='Collector bookkeeping/quality field; replace with provider-specific equivalent.'),
        coverage={scope:len(keys) for scope,keys in expected.items()}, status_counts=counts,
        damage_source_children=[f'{c}.{r}' for c in profile['damage_accounting']['categories'] for r in profile['damage_accounting']['relationships']],
        source_sha256=fingerprints, existing_anchor_evidence=pool_evidence,
        fields=ROWS, derived=[dict(stat=a,status=b,reason=c) for a,b,c in DERIVED],
        diagnostics='performance.* (monotonic_s, process_cpu_s, cpu_one_core_percent, cpu_window_percent, cpu_window_s, working_set_mib, private_mib, read_ms, read_calls, bytes_read, rate), schema/header/footer/gaps and timestamps are provider diagnostics. A Lua mod cannot claim per-mod Windows CPU/RAM or ReadProcessMemory counts; use callback/query/export costs and errors instead.',
        output='global:ModLog is documented for battle and writes lua_mod_log.txt. This establishes a text export candidate, not our binary compressed/AES-GCM format. Verify release-build output, flushing, file limits and shutdown before promising automatic export. External conversion may compress/encrypt afterwards.',
        runtime_checks=['Resolve all units through Lua unique_ui_id and CCO without selecting them.',
            'Compare documented CCO totals to existing external reader during a battle and after death/removal.',
            'Check hidden/off-camera/enemy cache freshness, including opposite-alliance LOS.',
            'Check summons, reinforcements, gifted units, transformations and identity lifetime.',
            'Compare ammo_left/starting_ammo to native primary/secondary pool counters.',
            'Resolve morale stat-panel key and test negative leadership, unbreakable and crumble states.',
            'Compare fractional Winds and reciprocal rate with pause/fast-forward and zero-rate cases.',
            'Check export in release builds, large rosters, campaign/custom/replay/multiplayer; no gameplay-changing API calls.'])
    (P/'build/mod-access-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    lines = ['# Workshop data-access audit — 2026-10-23', '',
        'Investigated every field emitted by the current normalized collector, plus its derived statistics. No collector/report behavior changed. No mod was installed or run. “Documented” means a named game interface exists, not that our Lua implementation has passed an in-game test.', '',
        f'Coverage: {len(expected["unit"])} unit fields, {len(expected["army"])} army fields, {len(expected["sample"])} sample-envelope fields. The damage-source entry also covers all 18 source/relationship counters. The audit script checks complete coverage against the actual reader fixture and validates every cited interface in the supplied game documentation.', '',
        '## Conclusion', '',
        'A normal Workshop collector can plausibly preserve most basic tracking and total/gold damage. Full parity is not established: native damage-source/friendly/self counters, unclamped healing budget and its unlimited flag, flat secondary ammo, and exact signed leadership are the main gaps. Winds UI queries discard fractional precision. None requires kernel access; the difference is what the game exposes to Lua.', '',
        'The live CcoBattleUnit.BattleResultUnitContext builds a context around the same UNIT+0x68 result object used externally (saved 141e5fe28, already matched in the installed profile). This is stronger evidence for live damage/gold access than merely finding result-screen fields. Exact Lua lookup and object lifetime still need a battle test.', '',
        '## Every collected field', '',
        'Statuses: **documented** = named getter exists; **partial** = access or precision is incomplete; **no interface** = no equivalent found; **blocked by input** = dependent calculation; **derived** = calculable from exposed inputs; **provider** = collector bookkeeping.', '',
        '| Scope / fields | Status | Mod access | Qualification |', '|---|---|---|---|']
    for r in ROWS:
        cells = [r['scope']+': '+', '.join('`'+x+'`' for x in r['fields']), r['status'].replace('_',' '), r['access'], r['limitation']]
        lines.append('| '+' | '.join(c.replace('|','/') for c in cells)+' |')
    lines += ['', '## Consequences for report statistics', '', '| Statistic | Feasibility | Reason |', '|---|---|---|']
    lines += ['| '+' | '.join(c)+' |' for c in DERIVED]
    lines += ['', '## Important distinctions', '',
        '- `MaxHealthPercentCanReplenish` is the old UI ceiling. Writer 143034ca0 clamps it for multi-model units, so subtracting current HP does not recover the native budget. A hardcoded summon starting ceiling cannot repair the missing current ceiling.',
        '- `MoralePercent` (141e83cf4) subtracts a configured threshold before normalizing; unbreakable units can report their best morale instead of signed current leadership. Do not multiply it by database leadership and call it raw leadership.',
        '- `CurrentWind`, `ReserveWind` and `MaxWind` getter anchors use `cvttss2si`, truncating stored float pools to integers. `CurrentRechargePerSecond` returns a reciprocal (seconds/point); invert only positive finite values.',
        '- `DamageInflictedRecently` covers a recent window; summing overlapping samples double counts. Ability phase damage, vortex damage and weapon damage are configured amounts, not measured applied totals. None reconstructs friendly/self or native source attribution.',
        '- Soldier counts from Lua and CCO entity counts need comparison for handlers/mounts/artillery. Use matching CCO counters where available.',
        '- UI getters can share the existing cache-refresh limitations. “Lua can query it” does not establish that hidden/off-camera values are fresh.', '',
        '## Export and diagnostics', '', report['output'], '', report['diagnostics'], '',
        'A Workshop mod plus the existing external viewer remains a feasible design. Keep the neutral schema and explicit capability list. Do not advertise full-stat parity until the missing interfaces and runtime checks are resolved. A companion memory reader would still be external software, even if accompanied by a Workshop item.', '',
        '## Additional interfaces found (not currently collected)', '',
        '- Ability uses/cooldowns/readiness: `BattleAbilityList`, `CcoBattleAbility.RemainingUses`, `HasLimitedUses`, `RechargeTimeRemainingSecs`, `CanCurrentlyPerform`, `IsActive`. Unlimited activation transitions are sampled, not guaranteed complete cast counts.',
        '- Buff/debuff uptime: `ActiveEffectList`, effect start/duration/remaining time and phase record. Configured phase damage is not proof of actual HP damage.',
        '- Distinct crumble/unstable flags: Lua `is_crumbling` / `is_unstable`. Rally waiting is now collected externally; the exposed getter’s local-control display filter is documented in the table above.',
        '- Friendly kills: `CcoBattleResultUnit.NumKillsFriendlies`, distinct from friendly HP damage.',
        '- Commands: `battle:register_command_handler` exists, but actor/target attribution and repeated-order coverage need investigation; this is not yet verified per-unit orders/minute.', '',
        '## Required in-game verification', '']
    lines += [f'{i+1}. {v}' for i,v in enumerate(report['runtime_checks'])]
    lines += ['', '## Sources', '',
        '- Supplied game docs: `../Local-files/documentation/ui/documentation.html`; `../Local-files/documentation/script/battle/{battle,battle_unit,battle_vector,common,global}.html`.',
        '- Existing verified evidence: `build/field-verification.json`, `build/damage-accounting-evidence.json`, `build/healing-budget-evidence.json`, `build/report-field-evidence.json`, supported profiles and named saved Ghidra exports. No new executable/xref scan.',
        '- [CA scripting docs mirror: common context queries](https://chadvandy.github.io/tw_modding_resources/WH3/battle/common.html#function:common:get_context_value), [battle unit](https://chadvandy.github.io/tw_modding_resources/WH3/battle/battle_unit.html), [UI context definitions](https://chadvandy.github.io/tw_modding_resources/WH3/cco/documentation.html).',
        '- Exact field evidence, document fingerprints and coverage: `build/mod-access-audit.json`. Regenerate with `py -3 -B tools/audit_mod_access.py`.', '']
    (P/'MOD_ACCESS_AUDIT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(coverage=report['coverage'], statuses=counts, runtime_tested=False)))


if __name__ == '__main__':
    main()
